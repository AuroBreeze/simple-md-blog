# Implementing Redis in C++ : C

## 前言

本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

本文章为续<<[Implementing Redis in C++ : B](https://blog.csdn.net/m0_58288142/article/details/150531872?fromshare=blogdetail&sharetype=blogdetail&sharerId=150531872&sharerefer=PC&sharesource=m0_58288142&sharefrom=from_link)>>所以本文章不再完整讲解全部代码，只讲解其不同的地方

## 完成优化后的代码

- 自定义哈希表实现，替代std::map
- 渐进式rehash机制，避免性能抖动
- FNV哈希算法，提供更好的分布性
- 内存管理优化，减少内存碎片
- Finished 1000 clients, success = 1000, time = 2.73649s

## hashtable

### 主体思路

本文章在延续上文的非阻塞性能提升的网络连接的代码上，修改键值对存储从`map`修改为**自定义的`HMap`**。

大家或许都知道**哈希表**的功能，哈希表拥有O(1)的时间复杂度，在网络连接中，进行键值对存储时，哈希表会比`map`性能高很多。

原文作者，为优化存储性能，将`map`修改为**自定义的`HMap`**，并使用**自定义的`HMap`**进行键值对存储。

> 你或许可能会问，为什么不使用`STL`中的<unordered_map>或者<unordered_set> ?
> 原文作者提到了**侵入式**和**非侵入式**的数据结构，而我们通常使用的`STL`库中的数据结构，是**非侵入式**的，这种**非侵入式**的数据机构通常会有**额外**的内存分配**开销**，当然优点就是，泛用性强。
> 而对于**侵入式**的数据结构会减少**额外**的开销，但是**缺点**就是，泛用性弱，自己需要修改指针等细节。

区分**侵入式**和**非侵入式**的数据结构可能就需要读者自己具体了解了。

对于本文的**侵入式**的链式哈希表，特点就是，容器中内置**节点**，需我们自己维护节点。

我们要实现的也就是`hashtable`的那几个功能，**增**(set) **删**(del) **改**(set) **查**(get)，也就是前几章我们实现的`servers`的功能，同时我们还要注意`hashtable`的**扩容**的问题，在本文处理**扩容**时，选择同时管理两个`hashtable`，具体我们后面在讨论。

在本文中，使用的是链式的`hashtable`，所以我们也会用到**链表**。

本文还有一个关键的思路，有关**侵入式**的链式哈希表，链式哈希表的节点中即包含链表的节点，也包含被hash的数据。原文作者提到，当我们在拿到链式hash的节点的时候，我们怎么样才能再返回父级的结构体，从父级的结构体中获取消息的原始数据？**通过结构体里某个成员的地址，反推出整个结构体对象的地址**,将指向节点的指针减去指针指向对象的偏移量，强转成对应的结构体，我们就可以使用父级的结构体来获取消息了。


为快速理解本文，我将其有关**侵入式**链式哈希表的各个结构体的关系放置在下面，当对某一个结构体或者某个函数的功能不清晰时，可以查看下图，提升理解。

```cpp
g_data
 └── db (HMap)
      ├── newer (HTab)
      │     ├── tab: HNode*[]
      │     │      ├─> HNode (from Entry1) ──> HNode (from Entry2) ──> ...
      │     │      └─> HNode (from Entry3) ──> ...
      │     ├── mask
      │     └── size
      │
      ├── older (HTab)
      │     ├── tab: HNode*[]
      │     ├── mask
      │     └── size
      │
      └── migrate_pos

g_data
 └── db : HMap

HMap
 ├── newer : HTab       ──> 正在使用的新表
 ├── older : HTab       ──> 迁移中的旧表
 └── migrate_pos : size_t  ──> 迁移进度

HTab
 ├── tab  : HNode**     ──> 数组，每个元素是链表头指针
 │          tab[0] ──> HNode ──> HNode ──> ...
 │          tab[1] ──> HNode ──> ...
 │          ...
 ├── mask : size_t      ──> 用于计算索引 (hcode & mask)
 └── size : size_t      ──> 表中元素个数

HNode
 ├── next : HNode*     ──> 指向下一个 HNode
 └── hcode : uint64_t  ──> 哈希值

Entry (用户数据)
 ├── node (HNode)  <── 侵入式节点，链接到 HTab 的 tab[i] 链表
 ├── key: std::string <—— 用户原始数据的 键
 └── val: std::string <—— 用户原始数据的 值
```

### HNode{}, HTable{}

```cpp
struct HNode{
    HNode* next;
    uint64_t hcode = 0;
};

struct HTab{
    HNode* *tab = nullptr;
    size_t mask = 0;
    size_t size = 0;
};
```

`HNode`结构体表示一个节点,同时存储**被`hash`的内容**

`HTable`结构体表示一个哈希表，在这个结构体中我们使用了**指向指针的指针**，这个指针的指针，指向的就是一个**链表**的头结点。

这两个结构体的关系：

`HNode`作为一个节点，是需要往`HTab`这个表中添加的，所以当新的数据被**哈希**放入`hcode`后，`HNode`中的`next`就会指向`HTab`中`tab[pos]`(pos:位置)所指向的数据，这之后，`tab[pos]`指向刚刚的`HNode`，形成**链**,所以越**后**来的数据，在链表中就越考**前**

我们可以通过下图来描述这两个个结构体：

```cpp
HTab
+------------------+
| tab ------------+-------> tab[ 0 ] --> (HNode*) --> [hcode=42] -> [hcode=99] -> nullptr
| mask = 3        |          tab[ 1 ] --> (HNode*) --> [hcode=123] -> nullptr
| size = 3        |          tab[ 2 ] --> (HNode*) --> nullptr
+------------------+          tab[ 3 ] --> (HNode*) --> [hcode=77] -> nullptr
```

除了这两个结构体的关系外，`HTab`结构体还维护了一个`size`成员变量，用于记录哈希表中的元素个数，还有一个`mask`用来计算哈希，这个我们后面讲解。

### h_insert()

```cpp
static void h_insert(HTab* htab,HNode* node){
    size_t pos = node->hcode & htab->mask;
    HNode* next = htab->tab[pos];
    node->next = next;
    htab->tab[pos] = node;
    htab->size++;
}
```

函数功能：将节点插入到哈希表中。(所以需要两个参数，想要插入的哈希表和节点)

这里的代码的思路我们上面已经讲过了，大家看一下思考一下就可以跳过了，我们主要来说一下`mask`这个参数，`mask`参数是为了计算我们的哈希表的索引。

在上面我们已经说过了`hcode`是被`hash`后的内容,我们通常来说计算哈希表的索引是使用**pose = hcode % capacity**，但是**CPU**处理**模运算**的效率比**位运算**慢，所以我们这次考虑了**位运算**来优化这个过程。

我们通过使 **`mask`是(2的幂次方-1)** 来使用`&`进行位运算 **(取低n位全1)**，获取到哈希的索引，假如我们要计算**37 & 7(2^3-1) = 5**

> 关于为什么`mask`必须是(2的幂次方-1)，假设2^3 = 8，那么转化为二进制就是：1000，mask = 7,，转化为二进制后：0111，只有这样才能取**低n位全1**

```
37 = 100101
 7 = 000111

100101
000111
------
000101   (二进制) = 5 (十进制)
```

这样我们就完成了索引的计算的优化了。

### h_init() 

```cpp
static void h_init(HTab* htab, size_t n){ // n must be power of 2
    assert(n > 0 && ((n-1) & n) == 0); // n must be power of 2
    htab->tab = (HNode* *)calloc(n,sizeof(HNode* ));
    htab->mask = n-1;
    htab->size = 0;
}
```

这个函数用于初始化哈希表。

在这个初始化函数中，我们使用了`callco`进行内存的分配(没有使用`malloc`)，为什么？

使用`calloc`会分配**内存 + 清零**(把每个字节都设成 0)，而使用`malloc`只会分配内存，不会清零，里面会有未定义的垃圾值，一旦后续逻辑认为它是有效指针并解引用，就会**段错误(Segfault)**。

> 有意思的是，使用`calloc`和使用`malloc`都是在第一次访问该内存的时候才会分配对应的内存。同时`calloc`可能会有优于`malloc`的写入，这可能需要更深入的知识，目前我的知识尚浅不知。

### h_lookup(), h_detach()

```cpp
static HNode* *h_lookup(HTab* htab, HNode* key, bool (*eq)(HNode* , HNode*)){
    if(!htab->tab) return nullptr;
    size_t pos = key->hcode & htab->mask;
    HNode* *from = &htab->tab[pos];
    for(HNode* cur;(cur = *from) != nullptr;from = &cur->next){
        if(cur->hcode == key->hcode && eq(cur,key)) return from;
    }
    return nullptr;
}

//remove a node from chain
static HNode* h_detach(HTab* htab, HNode* *from){
    HNode* node = *from;
    *from = node->next;
    htab->size--;
    return node;
}
```

从对应的`HTab`表中查找`HNode`中的哈希内容(key)，形参中的`HNode* key`的意思就是要找专门找`key`，而形参中的`bool (*eq)(HNode*, HNode*)`,翻译成人话:`eq`是一个函数指针，指向一个函数，这个函数接受两个`HNode*`参数，返回一个`bool`值。

我们计算好哈希表的索引后，就去找对应索引的链表，然后遍历这个链表，找相应的内容，其中我们使用了**指向指针的指针**(我们函数的返回也是使用的这个)，使用这个指向指针的指针，在函数中的`from`的作用，类似是**读取二维数组**。

如果你仔细看`h_lookup`里的循环，你就会发现有意思的地方，在`for`循环中我们定义了一个指针变量`cur`，这个变量的初始值是`from`指针(也就是指向的链表的指针)，然后我们每次循环都会将`from`指向的节点赋给`cur`(也就是**from = &cur->next**,而**cur变成了nextnode**)，这样的移动就会使得**from**始终指向的是**cur**的父节点，直到循环结束。

为什么要这样设定？这是为了方便删除节点，可以看这个图示

```cpp
HTab
 └── tab[pos] ──► HNodeA ──► HNodeB ──► HNodeC
                   │
                   └── *from
from ──► &HNodeA->next
cur  ──► HNodeB
```

删除节点，我们只需要将`from`指向的节点的`next`指针指向`cur`的`next`指针，这样`from`就指向了`cur`的下一个节点，也就是`HNodeC`。

`h_detach`函数的功能就是删除节点，将`from`指向的节点从链表中删除，并返回该节点，具体细节我们就不再讲解了。


### HMap{}, hm_lookup(), hm_insert(), hm_delete()
```cpp
struct HMap
{
    HTab newer;
    HTab older;
    size_t migrate_pos = 0;
};


HNode* hm_lookup(HMap* hmap,HNode* key,bool (*eq)(HNode* , HNode*)){
    hm_help_rehashing(hmap);
    HNode* *from = h_lookup(&hmap->newer,key,eq); 
    if(!from){
        from = h_lookup(&hmap->older,key,eq);
    }
    return from ? *from : nullptr;
}

const size_t k_max_load_factor = 8;

void hm_insert(HMap* hmap,HNode* node){
    if(!hmap->newer.tab){
        h_init(&hmap->newer,4);
    }

    h_insert(&hmap->newer,node);

    if(!hmap->older.tab){ // check if we need to rehash
        size_t shreshold = (hmap->newer.mask + 1) * k_max_load_factor;
        if(hmap->newer.size >= shreshold){ 
            hm_trigger_rehashing(hmap);
        }
    }

    hm_help_rehashing(hmap); // migrate some nodes
}

HNode* hm_delete(HMap* hmap,HNode* key,bool (*eq)(HNode* , HNode*)){
    hm_help_rehashing(hmap);
    if(HNode* *from = h_lookup(&hmap->newer,key,eq)){
        return h_detach(&hmap->newer,from);
    }
    if(HNode* *from = h_lookup(&hmap->older,key,eq)){
        return h_detach(&hmap->older,from);
    }
    return nullptr;

}
```

我们前面处理了哈希表的**增加、查找、删除**的功能，这里我们就将他们集合起来，因为我们的哈希表也需要有**扩容**的操作，所以这里的操作就是维护两个哈希表。

> 具体的扩容及`hm_help_rehashing`和`hm_trigger_rehashing`，我们后面再具体讲解。
> 简单讲：`hm_trigger_rehashing` 就是判断是否需要扩容，`hm_help_rehashing`就是将一部分的数据从旧哈希表移动到新哈希表。
> 数据的移动是一部分一部分的移，所以就需要我们在各个操作中都加入移动的指令`hm_help_rehashing`

使用两个哈希表后，我们上文将的函数`h_insert`和`h_detach`等等函数，就需要同时操作两表了。

他们的逻辑也大都相同，都是先操作新表，再操作旧表(这也就要求我们一开始，我们存放数据的时候都放在新表中，也就是`hm_insert`中的**if(!hmap->newer.tab) h_init(&hmap->newer,4);**)。

具体的细节我们也就不再讲述了。

### hm_help_rehashing()

```cpp
const size_t k_rehashing_work = 128; // costant work

static void hm_help_rehashing(HMap* hmap){
    size_t nwork = 0;
    while(nwork < k_rehashing_work && hmap->older.size > 0){
        HNode* *from = &hmap->older.tab[hmap->migrate_pos];
        if(!*from){
            hmap->migrate_pos++;
            continue;
        }
        h_insert(&hmap->newer, h_detach(&hmap->older, from));
        nwork++;

        if(hmap->older.size == 0 && hmap->older.tab){
            free(hmap->older.tab);
            hmap->older = HTab{};
        }
    }
}
```

我们通过使用`HMap`中的`migrate_pos`属性来记录迁移的位置，相应的我们要注意，`from`指针指向的是索引位置的第一个`node`，每次插入都是将**链**中的一个节点迁到新表中，最后完成迁移。

具体的图示：

```cpp
older.tab[i] ──► A ──► B ──► C

第一次 迁移：
node = h_detach(&older, &older.tab[i]);

结果：
  node = A
  older.tab[pos] ──► B ──► C
```

这里还需要注意的就是`if`中的**hmap->older.tab**，`tab`是一个`HNode**`，是一个指针，虽然数据都被迁移走了，但是指针本身还在，所以`hmap->older.tab`还是有值的，这个时候，我们就将指针`free`，并将旧表重置。

为什么要考虑每次只移动一部分呢？

假设我们将所有数据一次性搬迁

- 系统需要长时间的连续计算(可能是 ms~s 级别卡顿)
- 在这段时间里，哈希表无法响应请求，系统会“卡住”；
- 在数据库/缓存场景(比如 Redis)中，这种停顿是致命的。

### hm_trigger_rehashing()

```cpp
static void hm_trigger_rehashing(HMap* hmap){
    assert(hmap->older.tab == nullptr);
    //(newer,older) <-- (new_table,newer)
    hmap->older = hmap->newer; // in the first time, the all data store in newer,we need to move to older first then rehashing newer
    h_init(&hmap->newer,(hmap->newer.mask+1)*2); // ensure the new table size is enough and the mask is power of 2
    hmap->migrate_pos = 0;
}
```

这个函数的功能就是触发扩容，使用`hmap->older = hmap->newer;`将数据信息**浅拷贝**到`older`中，然后初始化`newer`，并设置`migrate_pos`为0。

## server

至此，我们的`hashtable`需要实现的函数已经全部实现完毕，接下来就是将这些函数集成到`server`中。

`server`中我们也只进行讲解那些改动大的地方，未改动或改动小的地方不再讲解。

### g_data{}, Entry{}

```cpp
static struct {
    HMap db;
}g_data;

struct Entry{
    struct HNode node; // hashtable node
    std::string key;
    std::string val;
};
```
这里的结构体，可以对应开头我们的图示进行查看，方便理解。

`Entry`中的`node`作为**侵入式**的节点，而`key`和`val`则是用户存储的**键**和**值**。

### str_hash()

```cpp
static uint64_t str_hash(const uint8_t* data, size_t len){
    uint32_t h = 0x811c9dc5;
    for(size_t i=0; i<len; i++){
        h = (h+data[i]) * 0x01000193;
    }
    return h;
}
```
`str_hash()`函数，是一个简单的字符串哈希函数，使用**FNV-1a**算法。

有关具体的hash算法，就需要大家自行去了解了。

### entry_eq()

```cpp
#define container_of(ptr,T,member) \
    ((T*)( (char*)ptr - offsetof(T,member) ))

static bool entry_eq(HNode* lhs, HNode* rhs){
    struct Entry* le = container_of(lhs,struct Entry, node);
    struct Entry* re = container_of(rhs,struct Entry, node);
    return le->key == re->key;
}
```

这里的`entry_eq()`函数，是一个比较函数，用于比较两个节点的**父级结构体**是否相等，也就是我们上面说的`bool (*eq)(HNode* , HNode*)`，在我们的`hm_lookup()`的查找中，我们要确保我们查找到正确的节点。

> `hash`可能会有**哈希冲突**，当哈希冲突的时候，我们就需要比较节点的原始的数据，从而找到正确的值。

`container_of`是一个宏，用于将一个指针转换为一个结构体的指针，也就是我们开头的思路，指针减偏移量，强转得到父级的结构体，得到父级的机构体后我们就可以**直接访问**父级结构体的成员变量了。

> container_of = “已知结构体成员指针 + 成员在结构体偏移量 → 算出结构体起始地址”。

```sql
Entry @0x1000
+-------+------------+------+
| id    | name       | node |
+-------+------------+------+
0x1000  0x1004       0x1014
```

- ptr = &entry->node = 0x1014
- offsetof(Entry, node) = 0x1014 - 0x1000 = 0x14
- (char*)ptr - offsetof(Entry, node) = 0x1014 - 0x14 = 0x1000
- (Entry*)0x1000 = entry ✅

### do_get(), do_set(), do_del()

```cpp
static const std::string* do_get(std::vector<std::string> &cmd, Ring_buf &buf){
    Entry key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((const uint8_t*) key.key.data(), key.key.size());
    //hashtable lookup
    HNode* node = hm_lookup(&g_data.db,&key.node,&entry_eq);
    if(!node){
        buf.status = RES_NX;
        return nullptr;
    }
    const std::string* val = &container_of(node,Entry,node)->val;
    return val;
}

static void do_set(std::vector<std::string> &cmd){
    Entry key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((const uint8_t*)key.key.data(),key.key.size());

    HNode *node = hm_lookup(&g_data.db,&key.node,&entry_eq);
    if(node){
        container_of(node,Entry,node)->val.swap(cmd[2]);
    }else{
        Entry *ent = new Entry();
        ent->key.swap(key.key);
        ent->node.hcode = key.node.hcode;
        ent->val.swap(cmd[2]);
        hm_insert(&g_data.db,&ent->node);
    }
}

static void do_del(std::vector<std::string> &cmd) {
    // a dummy `Entry` just for the lookup
    Entry key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((uint8_t *)key.key.data(), key.key.size());
    // hashtable delete
    HNode *node = hm_delete(&g_data.db, &key.node, &entry_eq);
    if (node) { // deallocate the pair
        delete container_of(node, Entry, node);
    }
}
```

因为我们通过环形缓冲区优化后，代码与原文作者并不完全一致(改动并不多)。

这里的代码似乎也不需要太多讲解。

需要注意的是，在整个思路中`Entry`是存放原始数据和**节点**的地方，真正存放`hash`的地方是`Entry::node`中的`hcode`，同时通过`&`运算计算计算出`hcode`的哈希索引的位置并放入，具体看开头的图示，更能快速理解。

## end

具体的`client`代码没有改动，就不再给出，可以看前面的文章获取。

此项目的[github地址](https://github.com/AuroBreeze/Implementing-Redis-in-C)


```cpp
// hashtable.h
#pragma once
#include <cstddef>   // for size_t
#include <cstdint>   // for uint64_t

struct HNode{
    HNode *next;
    uint64_t hcode = 0;
};

struct HTab{
    HNode* *tab = nullptr;
    size_t mask = 0;
    size_t size = 0;
};

struct HMap
{
    HTab newer;
    HTab older;
    size_t migrate_pos = 0;
};

HNode *hm_lookup(HMap* hmap,HNode* key,bool (*eq)(HNode* , HNode*));
void hm_insert(HMap* hmap,HNode* node);
HNode *hm_delete(HMap* hmap,HNode* key,bool (*eq)(HNode* , HNode*));
void hm_clear(HMap* hmap);
size_t hm_size(HMap* hmap);
```

```cpp
//hashtable.cpp
#include "hashtable.h"
#include <cassert>
#include <cstdlib>
#include <cstddef>   // for size_t
#include <cstdint>   // for uint64_t

static void h_init(HTab* htab, size_t n){ // n must be power of 2
    assert(n > 0 && ((n-1) & n) == 0);
    htab->tab = (HNode* *)calloc(n,sizeof(HNode* ));
    htab->mask = n-1;
    htab->size = 0;
}

static void h_insert(HTab* htab,HNode* node){
    size_t pos = node->hcode & htab->mask;
    HNode* next = htab->tab[pos];
    node->next = next;
    htab->tab[pos] = node;
    htab->size++;
}

static HNode* *h_lookup(HTab* htab, HNode* key, bool (*eq)(HNode* , HNode*)){
    if(!htab->tab) return nullptr;
    size_t pos = key->hcode & htab->mask;
    HNode* *from = &htab->tab[pos];
    for(HNode* cur;(cur = *from) != nullptr;from = &cur->next){
        if(cur->hcode == key->hcode && eq(cur,key)) return from;
    }
    return nullptr;
}


//remove a node from chain
static HNode* h_detach(HTab* htab, HNode* *from){
    HNode* node = *from;
    *from = node->next;
    htab->size--;
    return node;
}

const size_t k_rehashing_work = 128; // costant work

static void hm_help_rehashing(HMap* hmap){
    size_t nwork = 0;
    while(nwork < k_rehashing_work && hmap->older.size > 0){
        HNode* *from = &hmap->older.tab[hmap->migrate_pos];
        if(!*from){
            hmap->migrate_pos++;
            continue;
        }
        h_insert(&hmap->newer, h_detach(&hmap->older, from));
        nwork++;

        if(hmap->older.size == 0 && hmap->older.tab){ // C 风格数组不会有“空数组就是 false”这种说法
            free(hmap->older.tab);
            hmap->older = HTab{};
        }
    }
}

static void hm_trigger_rehashing(HMap* hmap){
    assert(hmap->older.tab == nullptr);
    //(newer,older) <-- (new_table,newer)
    hmap->older = hmap->newer; // in the first time, the all data store in newer,we need to move to older first then rehashing newer
    h_init(&hmap->newer,(hmap->newer.mask+1)*2); // ensure the new table size is enough and the mask is power of 2
    hmap->migrate_pos = 0;

}

HNode* hm_lookup(HMap* hmap,HNode* key,bool (*eq)(HNode* , HNode*)){
    hm_help_rehashing(hmap);
    HNode* *from = h_lookup(&hmap->newer,key,eq); 
    if(!from){
        from = h_lookup(&hmap->older,key,eq);
    }
    return from ? *from : nullptr;
}

const size_t k_max_load_factor = 8;

void hm_insert(HMap* hmap,HNode* node){
    if(!hmap->newer.tab){
        h_init(&hmap->newer,4);
    }

    h_insert(&hmap->newer,node);

    if(!hmap->older.tab){ // check if we need to rehash
        size_t shreshold = (hmap->newer.mask + 1) * k_max_load_factor;
        if(hmap->newer.size >= shreshold){ 
            hm_trigger_rehashing(hmap);
        }
    }

    hm_help_rehashing(hmap); // migrate some nodes
}

HNode* hm_delete(HMap* hmap,HNode* key,bool (*eq)(HNode* , HNode*)){
    hm_help_rehashing(hmap);
    if(HNode* *from = h_lookup(&hmap->newer,key,eq)){
        return h_detach(&hmap->newer,from);
    }
    if(HNode* *from = h_lookup(&hmap->older,key,eq)){
        return h_detach(&hmap->older,from);
    }
    return nullptr;

}

void hm_clear(HMap* hmap){
    free(hmap->newer.tab);
    free(hmap->older.tab);
    *hmap = HMap{};
}

size_t hm_size(HMap* hmap){
    return hmap->newer.size + hmap->older.size;
}
```

```cpp
//server.cpp
#define _WIN32_WINNT 0x0600
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <iostream>
#include <map>
#include <string>
#include <vector>
#include <unordered_map>

#include "hashtable.h"
#pragma comment(lib, "ws2_32.lib")

#define container_of(ptr,T,member) \
    ((T*)( (char*)ptr - offsetof(T,member) ))
    
using namespace std;



struct Ring_buf{
    std::vector<uint8_t> buf;
    size_t head;
    size_t tail;
    size_t cap;
    size_t status;

    Ring_buf():buf(256),head(0),tail(0),cap(256){
    }

    size_t size() const{
        return (cap + tail - head) % cap;
    }
    size_t free_cap() const{
        return cap - size() -1 ;
    }

    bool full() const{
        return (tail + 1) % cap == head;
    }

    bool empty() const{
        return head == tail;
    }
};

static void make_response(const string &resp, Ring_buf &out);
static void msg(const char *fmt) {
    fprintf(stderr, "%s\n",fmt);
}

static void die(const char *msg) {
    int err = WSAGetLastError();
    fprintf(stderr, "[%d] %s\n", err, msg);
    WSACleanup();
    exit(1);
}

static void hex_dump(const uint8_t* p, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        printf("%02X", p[i]);
        if ((i + 1) % 16 == 0) printf("\n");
        else printf(" ");
    }
    if (n % 16) printf("\n");
}

// 设置 socket 为非阻塞
static void fd_set_nb(SOCKET fd){
    u_long mode = 1;
    if (ioctlsocket(fd, FIONBIO, &mode) != 0) {
        die("ioctlsocket FIONBIO failed");
    }
}

const size_t k_max_msg = 32 << 20;

struct Conn {
    SOCKET fd;
    bool want_read = true;
    bool want_write = false;
    bool want_close = false;
    // vector<uint8_t> incoming;
    // vector<uint8_t> outgoing;
    Ring_buf incoming;
    Ring_buf outgoing;
};

static bool buf_append(Ring_buf &buf, const uint8_t *data, size_t n){
    if (n > buf.free_cap()) return false; // not enough space
    size_t min = std::min(n,buf.cap - buf.tail);
    memcpy(&buf.buf[buf.tail], data, min);
    memcpy(&buf.buf[0], data + min, n - min);
    buf.tail = (buf.tail + n) % buf.cap;
    return true;
}

static void buf_consume(Ring_buf &buf, size_t n){
    buf.head = (buf.head + n) % buf.cap;
}

static Conn* handle_accept(SOCKET listen_fd) {
    sockaddr_in client_addr{};
    int addrlen = sizeof(client_addr);
    SOCKET connfd = accept(listen_fd, (sockaddr*)&client_addr, &addrlen);
    if (connfd == INVALID_SOCKET) {
        int err = WSAGetLastError();
        if(err != WSAEWOULDBLOCK) 
            fprintf(stderr, "accept() error: %d\n", err);
        return nullptr;
    }

    uint32_t ip = ntohl(client_addr.sin_addr.s_addr);
    fprintf(stderr,
        "new client from %u.%u.%u.%u:%u\n",
        (ip >> 24) & 255,
        (ip >> 16) & 255,
        (ip >> 8) & 255,
        ip & 255,
        ntohs(client_addr.sin_port)
    );

    fd_set_nb(connfd);

    Conn* conn = new Conn();
    conn->fd = connfd;
    conn->want_read = true;
    return conn;
}

const size_t k_max_args = 200 * 1000;

static bool read_u32(const uint8_t* &cur, const uint8_t* end, uint32_t &out){
    if(cur + 4 > end){ // not enough data for the first length
        return false;
    }
    memcpy(&out, cur , 4);
    cur += 4;
    return true;
}

static bool read_str(const uint8_t* &cur, const uint8_t* end, size_t n,std::string &out){
    if(cur + n > end) return false; // not enough data for the string
    out.assign(cur,cur + n);
    cur += n;
    return true;
}


// +-----+------+-----+------+-----+------+-----+-----+------+
// | len | nstr | len | str1 | len | str2 | ... | len | strn |
// +-----+------+-----+------+-----+------+-----+-----+------+

static int32_t parse_req(const uint8_t* data, size_t size,std::vector<std::string> &out){
    const uint8_t* end = data+size;

    uint32_t nstr = 0;
    if(!read_u32(data,end,nstr)) return -1;
    if(nstr > k_max_args) return -1;

    while(out.size() < nstr){
        uint32_t len = 0;
        if(!read_u32(data,end,len)) return -1;

        out.push_back(std::string());
        if(!read_str(data,end,len,out.back())) return -1;
    }

    if(data != end) return -1;
    return 0;
}

enum{
    RES_OK = 0,
    RES_ERR = 1, // error
    RES_NX = 2 , // key not found
};

// +--------+---------+
// | status | data... |
// +--------+---------+

struct Response{
    uint32_t status;
    std::vector<uint8_t> data;
};

static struct {
    HMap db;
}g_data;

struct Entry{
    struct HNode node; // hashtable node
    std::string key;
    std::string val;
};

static bool entry_eq(HNode* lhs, HNode* rhs){
    struct Entry* le = container_of(lhs,struct Entry, node);
    struct Entry* re = container_of(rhs,struct Entry, node);
    return le->key == re->key;
}
// static std::map<std::string,std::string> g_data;


// FNV hash
static uint64_t str_hash(const uint8_t* data, size_t len){
    uint32_t h = 0x811c9dc5;
    for(size_t i=0; i<len; i++){
        h = (h+data[i]) * 0x01000193;
    }
    return h;
}

static const std::string* do_get(std::vector<std::string> &cmd, Ring_buf &buf){
    Entry key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((const uint8_t*) key.key.data(), key.key.size());
    //hashtable lookup
    HNode* node = hm_lookup(&g_data.db,&key.node,&entry_eq);
    if(!node){
        buf.status = RES_NX;
        return nullptr;
    }
    const std::string* val = &container_of(node,Entry,node)->val;
    return val;
}

static void do_set(std::vector<std::string> &cmd){
    Entry key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((const uint8_t*)key.key.data(),key.key.size());

    HNode *node = hm_lookup(&g_data.db,&key.node,&entry_eq);
    if(node){
        container_of(node,Entry,node)->val.swap(cmd[2]);
    }else{
        Entry *ent = new Entry();
        ent->key.swap(key.key);
        ent->node.hcode = key.node.hcode;
        ent->val.swap(cmd[2]);
        hm_insert(&g_data.db,&ent->node);
    }
}

static void do_del(std::vector<std::string> &cmd) {
    // a dummy `Entry` just for the lookup
    Entry key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((uint8_t *)key.key.data(), key.key.size());
    // hashtable delete
    HNode *node = hm_delete(&g_data.db, &key.node, &entry_eq);
    if (node) { // deallocate the pair
        delete container_of(node, Entry, node);
    }
}


static string do_request(std::vector<std::string> &cmd,Ring_buf &buf){
    if(cmd.size() == 2 && cmd[0] == "get"){
        const std::string* s = do_get(cmd,buf);
        if(s == nullptr) return "nil";
        return s->data();
    }else if(cmd.size() == 3 && cmd[0] == "set"){
        do_set(cmd);

    }else if(cmd.size() == 2 && cmd[0] == "del"){
        do_del(cmd);
    }else{
        buf.status = RES_ERR;
        
    }
    return "Done";
};

static void make_response(const string &resp, Ring_buf &out){
    uint32_t resp_len = 4 + (uint32_t)resp.size();
    buf_append(out,(const uint8_t*)&resp_len,4);
    buf_append(out,(const uint8_t*)&out.status,4);
    buf_append(out,(const uint8_t*)resp.data(),resp.size());
}


static bool try_one_requests(Conn* conn){
    if(conn->incoming.size() < 4) return false;
    uint32_t len = 0;

    { // 头部可能被环形分割成两个部分
    size_t  head = conn->incoming.head;
    size_t first = std::min<size_t>(conn->incoming.cap-head,4);
    uint8_t hdr[4];
    memcpy(hdr,&conn->incoming.buf[head],first);
    if(first < 4){
        memcpy(&hdr[first],&conn->incoming.buf[0],4-first);
    }
    memcpy(&len,hdr,4);
    }


    if(len > k_max_msg){
        msg("message too long");
        conn->want_close = true;
        return false;
    }

    if(4 + len > conn->incoming.size()) return false;

    std::vector<uint8_t> request(len);
    size_t start = (conn->incoming.head + 4)%conn->incoming.cap;
    size_t first = std::min<size_t>(len,conn->incoming.cap - start);
    memcpy(request.data(),&conn->incoming.buf[start],first);
    if(first < len){
        memcpy(request.data() + first,&conn->incoming.buf[0],len - first);
    }

    printf("client request: len: %u \n", len);
    //hex_dump(request.data(),len);

    std::vector<std::string> cmd;
    if(parse_req(request.data(), len, cmd)<0){
        msg("parse_req failed");
        conn->want_close = true;
        return false;
    }

    // Response resp;
    std::string s = do_request(cmd,conn->outgoing);
    if(!s.empty()){
        make_response(s,conn->outgoing);
    }else{
        std::string s = "Done!";
        make_response(s,conn->outgoing);
    }
    // make_response(resp,conn->outgoing);
    buf_consume(conn->incoming,4+len);

    return true;
}

static void send_all(Conn* conn,Ring_buf &buf){
    size_t n = buf.size();
    size_t min = std::min(n,buf.cap - buf.head);
    int rv = send(conn->fd, (const char*)&buf.buf[buf.head],min,0);
    if(rv == SOCKET_ERROR){
        int err = WSAGetLastError();
        if(err == WSAEWOULDBLOCK) return;
        msg("send() error");
        conn->want_close = true;
        return;
    }
    if(rv > 0) buf_consume(buf, (size_t)rv);
}

static void handle_write(Conn* conn){
    if(conn->outgoing.empty()) return;

    send_all(conn, conn->outgoing);
    // buf_consume(conn->outgoing, rv);
    if(conn->outgoing.empty()){
        conn->want_read = true;
        conn->want_write = false;
    }
}

static void handle_read(Conn* conn){
    uint8_t buf[64*1024];
    int rv = recv(conn->fd, (char*)buf, sizeof(buf), 0);
    if(rv == 0){
        msg("connection closed by client");
        conn->want_close = true;
        return;
    }
    if(rv == SOCKET_ERROR){
        int err = WSAGetLastError();
        if(err == WSAEWOULDBLOCK) return;
        msg("recv() error");
        conn->want_close = true;
        return;
    }

    buf_append(conn->incoming, buf, rv);
    while(try_one_requests(conn)){}
    if(!conn->outgoing.empty()){
        conn->want_write = true;
        conn->want_read = false;
        handle_write(conn);
    }
}

int main() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2,2), &wsaData) != 0){
        cerr << "WSAStartup failed" << endl;
        return 1;
    }

    SOCKET fd = socket(AF_INET, SOCK_STREAM, 0);
    if(fd == INVALID_SOCKET) die("socket() failed");

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(6379);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    int opt = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));

    if(bind(fd, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR)
        die("bind() failed");

    if(listen(fd, SOMAXCONN) == SOCKET_ERROR)
        die("listen() failed");

    fd_set_nb(fd);
    cout << "Server listening on port 6379..." << endl;

    unordered_map<SOCKET, Conn*> fd2conn_map;
    vector<WSAPOLLFD> poll_args;

    while(true){
        poll_args.clear();

        // 监听 socket
        WSAPOLLFD pfd{};
        pfd.fd = fd;
        pfd.events = POLLIN;
        poll_args.push_back(pfd);

        // 所有客户端
        for(auto& kv : fd2conn_map){
            Conn* conn = kv.second;
            WSAPOLLFD p{};
            p.fd = conn->fd;
            p.events = 0;
            if(conn->want_read) p.events |= POLLIN;
            if(conn->want_write) p.events |= POLLOUT;
            poll_args.push_back(p);
        }

        int rv = WSAPoll(poll_args.data(), (ULONG)poll_args.size(), -1);
        if(rv == SOCKET_ERROR){
            int err = WSAGetLastError();
            if(err == WSAEINTR) continue;
            die("WSAPoll() failed");
        }

        // 新连接
        if(poll_args[0].revents & POLLIN){
            if(Conn* conn = handle_accept(fd)){
                fd2conn_map[conn->fd] = conn;
            }
        }

        // 客户端读写
        vector<SOCKET> to_close;
        for(size_t i=1; i<poll_args.size(); ++i){
            WSAPOLLFD &p = poll_args[i];
            Conn* conn = fd2conn_map[p.fd];
            if(!conn) continue;

            if(p.revents & POLLIN) handle_read(conn);
            if(p.revents & POLLOUT) handle_write(conn);
            if((p.revents & POLLERR) || conn->want_close) to_close.push_back(conn->fd);
        }

        for(SOCKET cfd : to_close){
            closesocket(cfd);
            delete fd2conn_map[cfd];
            fd2conn_map.erase(cfd);
        }
    }

    closesocket(fd);
    WSACleanup();
    return 0;
}
```






















