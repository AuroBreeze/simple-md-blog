# Implementing Redis in C++ : H
# Redis C++ 实现笔记（H篇）

## 前言
本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

本文章为续<<[Redis C++ 实现笔记（G篇）](https://blog.csdn.net/m0_58288142/article/details/151287378?fromshare=blogdetail&sharetype=blogdetail&sharerId=151287378&sharerefer=PC&sharesource=m0_58288142&sharefrom=from_link)>>所以本文章不再完整讲解全部代码，只讲解其不同的地方


## 主体思路

自上文建立了**客户端空闲超时**机制以处理链接资源的控制，本文将介绍如何实现`redis`的**键过期**机制。

`redis`作为**内存数据库**，在存储数据的时候会将数据放置到内存中(当然也可以将数据写入磁盘中，为保证访问速度，一般数据都会放在内存中)，但是我们的内存是**有限**的，而如何防止内存被占满，导致的卡顿等问题，`redis`会引入**键过期**机制，即**键**在**一定时间**后，会自动**删除**。

在原文中，作者使用**小顶堆**的数据结构来保存键的过期时间，使用**小顶堆**，可以有**O(1)**的时间复杂度来获取最小键的过期时间，并判断当前时间是否已经超过了最小键的过期时间，如果超过了，则将键删除，而插入数据是**O(logN)**的复杂度，删除数据是**O(log1)**的复杂度。

---

小顶堆的直观定义：

- 小顶堆是一种**完全二叉树**(用数组存储)。

> 完全二叉树：除了最后一层，其它各层的节点数都要达到最大（即都满），最后一层的节点必须从左往右依次排列，不能“右边有节点但左边空”。

- 规则：每个节点的值 都小于等于它的左右孩子。

类似以下图示：

```cpp
       1
     /   \
    3     5
   / \
  7   9
```

关于为什么要选择**小顶堆**来存储键的过期时间，而不是选择其他的数据结构(比如链表，AVL树，红黑树等)？

我们的这次处理的主要问题是：如何快速获取键的过期时间，以及如何判断当前时间是否已经超过了键的过期时间。

这样也就是说，要**快速**获取最近的要过期的键值，**小顶堆**的**O(1)**时间复杂度获取最小键的过期时间，而我们如果选择链表或者AVL树或者红黑树，则需要遍历链表或者AVL树或者红黑树，时间复杂度是**O(N)**(数组)或者**O(logN)**(AVL树或者红黑树)，如果我们还要进行，插入和删除操作，时间复杂度比**小顶堆**要高或一样高，选择**AVL树**的时候，还要考虑平衡，这样就会导致常数的开销大，等等。

---

我们知道，**小顶堆**的数据结构，是一个**完全二叉树**，那么，**完全二叉树**的存储结构可以是**数组**也可以是**树**，为什么要选择**数组**呢？

1. 完全二叉树的特点

* **完全二叉树** 的结构非常规整：

  * 节点位置是“从上到下，从左到右”依次排满的。
  * 这意味着：用下标就能算出父子关系，不需要存指针。

公式关系：

* 父节点下标：`i`
* 左子节点下标：`2*i`
* 右子节点下标：`2*i + 1`

---

2. 数组的优势
    1. 节省内存

    * 如果用指针实现树，每个节点要额外存 `left`、`right` 指针。
    * 数组存储完全不需要指针，空间更紧凑。

    2. 内存局部性好

    * 数组是连续存放的，遍历堆（上浮/下沉）时访问的是相邻内存块。
    * CPU 缓存命中率高，速度比指针跳转快很多。

    3. 操作简单

    * 插入、删除时只需要交换数组元素。
    * 不需要像 AVL、红黑树那样旋转、修改指针，逻辑更轻。

---

 3. 树指针存储的劣势

* 指针会造成 **内存碎片**，不如数组连续。
* 插入/删除时需要维护指针，比数组交换开销大。
* 不具备数组那种“下标算关系”的优势。

---

同时，本文将会增加两个命令：

1. `pexpire key milliseconds` ：设置 key 的过期时间，单位毫秒。
2. `pttl key` ：返回 key 的剩余过期时间，单位毫秒。

--- 

本文各结构体之间的关系，如下所示：
```cpp
g_data
├── fd2connmap : unordered_map
├── idle_list : DList
│      └── idle_node(Conn:DList) ---> idle_node(Conn:DList) --->  ......
├── heap : vector<HeapItem>
│            └── HeapItem ---> HeapItem ---> HeapItem ---> ......
│                    ├── val
│                    └── ref : ref指向Entry中的 heap_idx
└── db : HMap
    ├── newer : HTab   (正在使用)
    │   ├── tab[0] ──> HNode(Entry1) ──> HNode(Entry2) ──> ...
    │   │                                 │
    │   │                                 └── Entry
    │   │                                     ├── key  = "foo"
    │   │                                     ├── type = STR
    │   │                                     ├── str  = "hello"
    │   │                                     ├── heap_idx = -1
    │   │                                     └── zset = (unused if type=STR)
    │   │
    │   ├── tab[1] ──> HNode(Entry3) ──> ...
    │   │                     │
    │   │                     └── Entry
    │   │                         ├── key  = "myzset"
    │   │                         ├── type = ZSET
    │   │                         ├── str  = ""
    │   │                         ├── heap_idx = -1
    │   │                         └── zset : ZSet
    │   │                                ├── root (AVLNode*)
    │   │                                │       ┌── ZNode::tree(score=1.0, name="a")
    │   │                                │ root ─┼── ZNode::tree(score=2.0, name="b")
    │   │                                │       └── ZNode::tree(score=3.0, name="c")
    │   │                                │
    │   │                                └── hmap : HMap
    │   │                                     ├── newer : HTab
    │   │                                     │     ├── tab[hash("a")] ──> HNode(ZNode "a")
    │   │                                     │     ├── tab[hash("b")] ──> HNode(ZNode "b")
    │   │                                     │     └── tab[hash("c")] ──> HNode(ZNode "c")
    │   │                                     ├── older : HTab (迁移用)
    │   │                                     └── migrate : szie_t (迁移用)
    │   │
    │   ├── mask : size_t   (hash 索引掩码, 形如 2^k-1)
    │   └── size : size_t   (元素数量)
    │
    ├── older : HTab        (rehash 迁移时的旧表)
    │   ├── tab : HNode*[]
    │   ├── mask
    │   └── size
    │
    └── migrate_pos : size_t  (迁移进度)


struct HeapItem{
    uint64_t val = 0;
    size_t *ref = nullptr; // 指向Entry中的 heap_idx
};

struct Entry{
    struct HNode node; // hashtable node
    std::string key;
    // std::string val;

    // value
    uint32_t type = 0;
    std::string str;
    ZSet zset;

    // for TTL
    size_t heap_idx = -1; // array index to the heap item
};

```

## heap_pos()

```cpp
static size_t heap_parent(size_t i){
    return (i + 1) / 2 - 1;
}

static size_t heap_left(size_t i){
    return i * 2 + 1;
}

static size_t heap_right(size_t i){
    return i * 2 + 2;
}
```

位置的计算逻辑：

因为**小顶堆**是**完全二叉树**也就是我们上文讲的，我们可以使用图示来描述位置关系：

假设小顶堆中有以下数据：[1, 3, 5, 7, 9]

```cpp
        (1) i=0              max_num = 1
       /       \             
   (3) i=1     (5) i=2       max_num = 2
   /    \
(7) i=3 (9) i=4              max_num = 4

索引:   0   1   2   3   4
值:    [1,  3,  5,  7,  9]
```

这样可以更加直观的认识他们的位置关系：

想要从一个节点获取他的子节点，获取左子节点就是`pos = 2 * i + 1 `，右子节点就是`pos = 2 * i + 2`，那我们获取父节点，就是`pos = (i + 1) / 2 - 1`

> 关于为什么获取父节点是`pos = (i + 1) / 2 - 1` 而不是 `pos = (i - 1) / 2`?
> 首先我们知道的是，C/C++中的除法是向下取整的，所以不论是，当`i`为奇数时，`(i+1)/2`后多`1`(后面减一就平衡了)，还是当`i`为偶数时，`(i+1)/2 - 1`和`(i-1)/2`是相等的。
> 这两个算式的主要差别在计算根节点时的结果不同，也就是当`i = 0`时，`((i+1)/2 - 1) = -1`和`((i-1)/2) = 0`的计算结果不同。

## heap_up(), heap_down()

```cpp
static void heap_up(HeapItem* a, size_t pos){
    HeapItem t = a[pos];
    while(pos > 0 && a[heap_parent(pos)].val > t.val){
        // swap with the parent
        a[pos] = a[heap_parent(pos)];
        *a[pos].ref = pos;
        pos = heap_parent(pos);
    }
    a[pos] = t;
    *a[pos].ref = pos;
}

static void heap_down(HeapItem* a, size_t pos, size_t len){
    HeapItem t = a[pos];
    while(true){
        // find the smallest one among the parent and their kids
        size_t l = heap_left(pos);
        size_t r = heap_right(pos);
        size_t min_pos = pos;
        size_t min_val = t.val;
        if(l < len && a[l].val < min_val){
            min_pos = l;
            min_val = a[l].val;
        }
        if(r < len && a[r].val < min_val){
            min_pos = r;
        }
        if(min_pos == pos) break;
        // swap with the kids
        a[pos] = a[min_pos];
    }
    a[pos] = t;
    *a[pos].ref = pos;
}

void heap_update(HeapItem* a, size_t pos, size_t len){
    if(pos > 0 && a[heap_parent(pos)].val > a[pos].val){
        heap_up(a, pos);
    }
    else{
        heap_down(a, pos, len);
    }
}
```

**小顶堆**的维护，就是维护数组中数字的上升和下降关系，要维护数字小的在上面，下面的数字大。

`heap_up()`函数，就是从当前的节点开始，向上找那些比他大的节点，并将小的数字换到上面去。

这个函数的代码似乎不难理解，首先我们有一个中间节点`t`来存储我们当前要上移的节点，然后通过循环，从当前节点开始，向上找比当前节点小的节点，将这些节点(比当前节点大的节点)都交换到当前节点的位置去(也就是下移)，直到找到比当前节点小的节点或者到达根节点为止。

```cpp
struct Entry{
    struct HNode node; // hashtable node
    std::string key;
    // std::string val;

    // value
    uint32_t type = 0;
    std::string str;
    ZSet zset;

    // for TTL
    size_t heap_idx = -1; // array index to the heap item
};
```

其中我们的`HeapItem`结构体中的`ref`指向的是`Entry`结构体中的`heap_idx`字段，这个字段记录了当前节点在堆中的位置，当我们交换位置的时候，就需要修改这个字段的值。

`heap_down()`函数，就是从当前节点开始，将当前节点的数据下移(当前节点的数字比较大)，而我们在下移的时候，是需要比对左右节点的数字大小，因为我们换上来的数据**一定是小于左右节点的数据**，所以要选最小的。

我们在使用`heap_down()`函数的时候，还需要传入`size_t len`的参数(数组的大小)，会在`if`中使用，这是为什么？

因为，我们在计算**左右节点**的索引的时候，可能会超出数组的范围，所以，我们需要传入数组的长度，来判断是否超出了数组的范围。

其中还有一个需要注意的是，我们在`while`中，定义了一个每次都刷新的`size_t min_val = t.val`，同时只在左子节点的`if`判断中使用了`min_val = a[l].val`，这是为什么？

因为我们要移动的点是我们的当前的节点，我们要选择左右子节点最小的值，如果我们的左子节点小于当前的值(`a[l].val < t.val`)，那我们还需要判断是否小于右子节点，所以我们就要将左子节点的值赋给当前的节点，然后比对右子节点的值，这样就能找到**左右节点的最小值**。

`heap_update()`就是将`heap_up()`和`heap_down()`的代码结合了，就不再赘述了。

## clear()

```cpp
// destory the zset
void zset_clear(ZSet* zset){
    hm_clear(&zset->hmap);
    tree_dispose(zset->root);
    zset->root = nullptr;
}

static void entry_set_ttl(Entry* ent, int64_t ttl_ms);

static void entry_delete(Entry* ent){
    if(ent->type == T_ZSET){
        zset_clear(&ent->zset);
    }
    entry_set_ttl(ent, -1);
    delete ent;
}
```

我们所有的数据，包括键值对，AVL树的节点等等都是在`Entry`中保存的，所以我们在`entry_delete()`中将我们在**小顶堆**中的节点删除，并释放内存。

## heap_delete(), heap_upsert(), heap_insert()

```cpp
static void heap_delete(vector<HeapItem> &a, size_t pos){
    //swap the erased item with the last item
    a[pos] = a.back();
    a.pop_back();
    // update the swapped item
    if(pos < a.size()){
        heap_update(a.data(), pos, a.size());
    }
}
```

在**小顶堆**中，删除一个元素，需要将这个元素与最后一个元素交换，然后将最后一个元素下移下去就可以了。

```cpp
static void heap_upsert(vector<HeapItem> &a, size_t pos, HeapItem t){
    if( pos < a.size()){
        a[pos] = t; // update an existing item
    }
    else{
        pos = a.size();
        a.push_back(t); // insert a new item
    }
    heap_update(a.data(), pos, a.size());
}
```

**小顶堆**的更新函数，首先确定当前位置的元素是否已经存在，如果存在则更新，不存在则插入。

注意如果要更新的数据不再**小顶堆**中，当我们插入的时候，插入的位置一定是`pos = a.size()`的，首先是**完全二叉树**的性质，必须要从左子节点开始插入，其次，我们的数组是从`0`开始遍历的，而数组的大小是从`1`开始统计的，所以`pos = a.size()`的元素，一定是我们要插入的位置。

```cpp
// set or remove the TTL
static void entry_set_ttl(Entry* ent, int64_t ttl_ms){
    if(ttl_ms < 0 && ent->heap_idx != (size_t)-1){
        // setting a negtive TTL means removing the TTL
        heap_delete(g_data.heap, ent->heap_idx);
        ent->heap_idx = -1;
    }
    else if(ttl_ms >= 0){
        // add or update the heap data structure
        uint64_t expire_at = get_monotonic_msec() + (uint64_t)ttl_ms;
        HeapItem item = {expire_at, &ent->heap_idx};
        heap_upsert(g_data.heap, ent->heap_idx, item);
    }
}
```

在我们的设定中，`heap_idx`当为-1时，表示该键值对没有TTL，`heap_idx`当不为-1时，表示该键值对有TTL，且该键值对在堆中的索引为`heap_idx`，当我们使用`entry_set_ttl`传入`ttl_ms < 0`时，表示删除该键值对的TTL，同时将`heap_idx`设置为-1，表示该键值对没有TTL。

## pexpire, pttl

```cpp
// PEXPIRE key ttl_ms
static void do_expire(vector<string> &cmd, Ring_buf &buf){
    int64_t ttl_ms = 0;
    if(!str2int(cmd[2], ttl_ms)){
        return out_err(buf, ERR_BAD_ARG, "expect int64");
    }

    LookupKey key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((uint8_t*)key.key.data(), key.key.size());

    HNode* node = hm_lookup(&g_data.db, &key.node, &entry_eq);
    if(node){
        Entry *ent = container_of(node, Entry, node);
        entry_set_ttl(ent, ttl_ms);
    }
    return out_int(buf, node? 1:0);
}

// pttl key

static void do_ttl(vector<string> &cmd, Ring_buf &buf){
    LookupKey key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((uint8_t*)key.key.data(), key.key.size());

    HNode* node = hm_lookup(&g_data.db, &key.node, &entry_eq);
    if(!node){
        return out_int(buf, -2); // not found
    }

    Entry* ent = container_of(node, Entry, node);
    if(ent->heap_idx == (size_t)-1){
        return out_int(buf, -1); // no TTL
    }

    uint64_t expire_at = g_data.heap[ent->heap_idx].val;
    uint64_t now_ms = get_monotonic_msec();
    return out_int(buf, expire_at > now_ms ? (expire_at - now_ms) : 0);
}
```

我们在最上面的图示中，我们可以清楚的看到，我们所有的数据全部都挂载到`hash_table`中了，所以我们在查找**键值**的时候，就需要使用`hm_lookup()`来寻找**键值**。

其他的部分似乎并不需要太多解释，我们也不再多说。

## process_timers()

```cpp
static bool hnode_same(HNode* node, HNode* key){
    return node == key;
}

static void process_timers(){
    uint64_t now_ms = get_monotonic_msec();
    // debug_idle_list();
    
    /*
      Process expired connections
    */
    // debug_idle_list();

    // TTL timers using a heap
    const size_t k_max_works = 2000;
    size_t nworks = 0;
    const vector<HeapItem> &heap = g_data.heap;
    while(!heap.empty() && heap[0].val < now_ms){
        Entry* ent = container_of(heap[0].ref, Entry, heap_idx);
        HNode* node = hm_delete(&g_data.db, &ent->node, &hnode_same);
        assert(node == &ent->node);
        fprintf(stderr, "removing expired key: %s\n", ent->key.c_str());
        // delte the key
        entry_delete(ent);
        if(nworks++ >= k_max_works){
            // don't stall the server if too many keys are expiring at once
            break;
        }
    }
}
```

这个`process_timers()`是在`main`函数的`while`循环中，不断处理键的到期的操作。

> 我们要想到一个点，万一大量的键设定在同一时间到期，那样的话，在删除键的时候，会不会导致阻塞？
>
> 当然会的，所以我们还要设定每次删除的最多的键值`k_max_works`。

我们在循环中注意到`while`循环中只判断了`!heap.empty() && heap[0].val < now_ms`，因为我们用的是**小顶堆**，**[0]**的位置一定是马上要过期或已经过期的键值，我们会在循环中处理它并进行删除，这样就会`while`不断的循环下去，直到最小的键值没有过期。

在`while`中会先移除`hashtale`中挂载的节点，最后通过`entry_delete()`释放`Entry`

> 为什么要先移除`hashtable`中挂载的节点，最后再释放`Entry`呢？
> `Entry` 的生命周期是 由 **hashtable控制**的。只要 key 还在 hashtable 里，就意味着这个 key 还“存在”，客户端也有可能访问它。
> 同时，如果直接释放的话，如果这个节点后面还有其他键值的话，就无法访问到了，因为中间被我们直接释放后导致不通了(悬空指针)。

## end

这些就是代码修改的主体，其他的部分改动较小，我们就不再讲述了，鉴于代码放在这里实在太多，我给出我的github地址，大家可以去找`study/dev_6`的目录进行查看

github地址：[https://github.com/AuroBreeze/Implementing-Redis-in-C](https://github.com/AuroBreeze/Implementing-Redis-in-C)






