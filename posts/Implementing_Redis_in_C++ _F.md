# Implementing Redis in C++ : F
# Redis C++ 实现笔记（F篇）

## 前言

本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

本文章为续<<[Implementing Redis in C++ : E](https://blog.csdn.net/m0_58288142/article/details/150711600?fromshare=blogdetail&sharetype=blogdetail&sharerId=150711600&sharerefer=PC&sharesource=m0_58288142&sharefrom=from_link)>>所以本文章不再完整讲解全部代码，只讲解其不同的地方

## Redis-like命令

在原作者接下来的步骤中，原作者新增了`zadd`，`zrem`，`zscore`，`zquery`的命令，这些命令都是与`redis`的命令类似，我们简单的说一下这几个命令：

1. `zadd`：将一个元素加入到有序集合中，如果这个元素已经存在，则更新这个元素的分数。

使用方法：`zadd key score member`，如果数据不存在，添加成功后，返回 **(int) 1**，如果数据已经存在，则更新数据，返回 **(int) 0**

2. `zrem`：从有序集合中删除一个元素。

使用方法：`zrem key member`，删除成功后，返回 **(int) 1**，如果数据不存在，则返回 **(int) 0**

3. `zscore`：获取有序集合中指定成员的分数。

使用方法：`zscore key member`，返回 **(double) score**，如果数据不存在，则返回 **(nil)**

4. `zquery`：获取有序集合中 **>=(score, name)** 区间的成员。

使用方法：`zquery zset score name skip count`，返回 **(array)**，包含有序集合中 **>=(score, name)** 区间的成员。其中`skip`是跳过的数量，`count`是返回的成员数量。

## 主体思路

为了快速理解作者的代码的思路，我将定义的结构体之间的关系以以下图示描述：

```cpp
g_data
└── db : HMap
    ├── newer : HTab   (正在使用)
    │   ├── tab[0] ──> HNode(Entry1) ──> HNode(Entry2) ──> ...
    │   │                                 │
    │   │                                 └── Entry
    │   │                                     ├── key  = "foo"
    │   │                                     ├── type = STR
    │   │                                     ├── str  = "hello"
    │   │                                     └── zset = (unused if type=STR)
    │   │
    │   ├── tab[1] ──> HNode(Entry3) ──> ...
    │   │                     │
    │   │                     └── Entry
    │   │                         ├── key  = "myzset"
    │   │                         ├── type = ZSET
    │   │                         ├── str  = ""
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


g_data
 └── db : HMap

HMap (HashMap)
 ├── newer : HTab       ---> 正在使用的新表
 ├── older : HTab       ---> 迁移中的旧表
 └── migrate_pos : size_t  ---> 迁移进度

HTab (节点表)
 ├── tab  : HNode**     ---> 数组，每个元素是链表头指针
 │          tab[0] ---> HNode ---> HNode ---> ...
 │          tab[1] ---> HNode ---> ...
 │          ...
 ├── mask : size_t      ---> 用于计算索引 (hcode & mask)
 └── size : size_t      ---> 表中元素个数

HNode (链表节点)
 ├── next : HNode*     ---> 指向下一个 HNode
 └── hcode : uint64_t  ---> 哈希值

Entry (用户数据)
 ├── node: HNode  <--- 侵入式节点，链接到 HTab 的 tab[i] 链表
 ├── key: std::string <--- 用户原始数据的 键
 ├── type: uint32_t  <--- 数据类型
 ├── str: std::string <--- 用户原始数据的 值
 └── zset: ZSet  <--- 存放有序集合数据

ZSet (有序集合)
 ├── root: AVLNode*   ---> 根据(socre, name)进行排序的 AVL 树根节点
 └── hmap: HMap  ---> 根据 name 索引的哈希表

ZNode (有序集合节点)
 ├── tree: AVLNode
 ├── hmap: HNode
 ├── score: double
 ├── len: size_t
 └── name: char*

AVLNode (AVL 树节点)
├── parent: AVLNode*
├── left: AVLNode*
├── right: AVLNode*
├── height: uint32_t
└── cnt: uint32_t
```

在上面的整体思路中，我们拓展了`Entry`中存储数据的结构，让`Entry`中既可以存储`str`也可以存储`zset`，同时仍然保持使用`Entry`的**键**进行快速的查找，同时因为我们使用了`ZSet`，
`ZSet`中使用`AVL树`来存储`(score, name)`的数据，也使用`HMap`来索引`name`。

与之前的修改相比，现在的主要修改是使用`ZNode`中的`hmap`来接入`HMap`，并使用`ZNode`中的`tree`来接入`AVL树`。

因为在先前，我们已经实现了`AVL树`和`HMap`，而实现`Redis-like 命令`，就可以使用我们先去实现的这两个算法，来高效的查找数据。

所以接下来我们就要实现上面的命令和逻辑。

## ZSet{}, ZNode{}, znode_new()

```cpp
struct ZSet{
    AVLNode* root = nullptr; // index by (score, name)
    HMap hmap; // index by name
};

struct ZNode{
    AVLNode tree;
    HNode hmap;
    double score = 0;
    size_t len = 0;
    char name[0]; // flexible array
};

static ZNode* znode_new(const char* name, size_t len, double score){
    ZNode* node = (ZNode*)malloc(sizeof(ZNode)+len);
    assert(node);
    avl_init(&node->tree);
    node->hmap.next = nullptr;
    node->hmap.hcode = str_hash((uint8_t*)name, len);
    node->score = score;
    node->len = len;
    memcpy(&node->name[0], name, len);
    return node;
}
```

具体的`ZSet{}`与`ZNode{}`结构体的关系我们已经在上面的图示中说明了，这里不再赘述。

其中我们需要注意的是`ZNode{}`中的`name[0]`，这是定义了一个灵活数组，用来保存`name`，我们这样定义`struct`的方式，并不能使用`new`来创建结构体，因为`new`只会创建静态结构体，也就是不会计算我们后面增加的内容的大小，而`malloc()`可以创建动态结构体，可以灵活的分配内存大小。

因为我们的`name`是`char`类型，所以我们直接使用`sizeof(ZNode)+len`也是可以的。

要是换成其他的数据，记得要进行计算后面的大小。

## zadd()

`zadd()`命令，用于添加一个元素到`ZSet`中，示例：`zadd zset 1 name1`，也就是向`Entry`中存储键为`key = zset`的`AVLNode Entry::zset::root`的`AVL树`中插入一个`(score, name)`，同时，使用**哈希**插入到`Entry`中存储键为`key = zset`的`HTab Entry::zset::hmap::newer`中，将`name`作为`key`，`score`作为`value`。

所以，`zadd()`命令也就是分成了三个步骤：
1. 检查是否已经存在
2. 存在：更新
3. 不存在：插入


```cpp
bool zset_insert(ZSet* zset, const char* name, size_t len, double score){
    ZNode* node = zset_lookup(zset, name, len); // check the node exist
    if(node){
        zset_update(zset, node, score);
        return false; // update existing node
    }
    else{
        node = znode_new(name, len, score);
        hm_insert(&zset->hmap, &node->hmap);
        tree_insert(zset, node);
        return true;
    }
}
```

我们一步步解释其中的函数。

```cpp
// a helper structure for the hashtable lookup
struct HKey{
    HNode node;
    const char* name = nullptr;
    size_t len = 0;
};

static bool hcmp(HNode* node, HNode* key){
    ZNode* znode = container_of(node, ZNode, hmap);
    HKey* hkey = container_of(key, HKey, node);
    if(znode->len != hkey->len)
        return false;
    
    return 0 == memcmp(znode->name, hkey->name, znode->len);
}

// lookup by name
ZNode* zset_lookup(ZSet* zset, const char* name, size_t len){
    if(!zset->root)
        return nullptr;
    
    HKey key;
    key.node.hcode = str_hash((uint8_t*)name, len);
    key.name = name;
    key.len = len;
    HNode* found = hm_lookup(&zset->hmap, &key.node, &hcmp);
    return found ? container_of(found, ZNode, hmap) : nullptr ;
}
```

我们首先创建了一个`HKey`结构体，用来辅助查找。

为什么要新建一个`Hkey`结构体呢？

我们的`hm_lookup`函数需要`(HMap* hmap,HNode* key,bool (*eq)(HNode* , HNode*))`这四个参数，同时我们传入的函数指针`hcmp`还会使用`container_of`来获取到上级结构体，拿到上级结构体中的数据再次进行比对，最终确认我们要找的节点，在这同时我们不能单独的传入一个`char*`类型，我们就需要一个结构体来承担，存储`HNode*`和`char*`等的作用。

> 注意：`HKey`中的`HNode`代表的是`ZNode`中的`HNode`

当我们找到对应的节点后，我们就可以使用`container_of`来还原回上级结构体`ZNode`了，并返回。

```cpp
// compare by the (score, name) tuple
static bool zless(AVLNode* lhs, double score, const char* name, size_t len){
    ZNode* zl = container_of(lhs, ZNode, tree);
    if(zl->score != score){
        return zl->score < score;
    }

    int rv = memcmp(zl->name, name, min(zl->len, len));
    if (rv != 0) {
        return rv < 0;
    }
    return zl->len < len;
}

static bool zless(AVLNode* lhs, AVLNode* rhs){
    ZNode* zr = container_of(rhs, ZNode, tree);
    return zless(lhs, zr->score, zr->name, zr->len);
}

static void tree_insert(ZSet* zset, ZNode* node){
    AVLNode* parent = nullptr; // insert under this node
    AVLNode* *from = &zset->root; // the incoming pointer to the next node
    while(*from){ // tree search
        parent = *from;
        from =  zless(&node->tree, parent) ? &parent->left : &parent->right;
    }
    *from = &node->tree;  // attach to this node
    node->tree.parent = parent;
    zset->root = avl_fix(&node->tree);
}
```

因为我们要使用`AVL树`来存储`(score, name)`的信息，所以树在排序的时候也是，先比较`score`，然后比较`name`，然后进行存储，所以当我们在搜索**树**准备插入数据的时候，我们也需要使用`container_of`来获取上级结构体中的`(score, name)`数据，也就是我们写的`zless`函数。

而`tree_insert`函数，也是通过`while zless`找到插入的位置，然后进行插入。

```cpp
// update the score of an existing node
static void zset_update(ZSet* zset, ZNode* node, double score){
    if(node->score == score) 
        return; // no change
    zset->root = avl_del(&node->tree);
    avl_init(&node->tree);
    node->score = score;
    tree_insert(zset, node);
}
```

更新代码似乎不用多说，需要注意的是，修改`AVL树`中的数据，可能会破坏树的有序性，所以我们要先删除原来的数据，然后再插入新的数据。

> `avl_del`中删除后会调用`avl_fix`来修复树，不必担心树被破坏。

```cpp
static bool str2dbl(const std::string &s, double &out){
    char* endp = nullptr;
    out = strtod(s.c_str(), &endp);
    return endp == s.c_str() + s.size() && !isnan(out);
}

static bool str2int(const std::string &s, int64_t &out){
    char* endp = nullptr;
    out = strtoll(s.c_str(), &endp, 10);
    return endp == s.c_str() + s.size();
}

// zadd zset score name
static void do_zadd(std::vector<std::string> &cmd, Ring_buf &buf){
    double score = 0;
    if(!str2dbl(cmd[2], score)){
        return out_err(buf, ERR_BAD_ARG, "expect float");
    }

    // lookup the zset
    LookupKey key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((uint8_t*)key.key.data(), key.key.size());
    HNode* hnode = hm_lookup(&g_data.db, &key.node, &entry_eq);


    Entry* ent = nullptr;
    if(!hnode){
        // insert a new key
        ent = entry_new(T_ZSET);
        ent->key.swap(key.key);
        ent->node.hcode = key.node.hcode;
        hm_insert(&g_data.db, &ent->node);
    }
    else{
        ent = container_of(hnode, Entry, node);
        if(ent->type != T_ZSET){
            return out_err(buf, ERR_BAD_TYP, "expect zset");
        }
    }

    // add or update the tuple
    const std::string &name = cmd[3];
    bool added = zset_insert(&ent->zset, name.data(), name.size(), score);
    return out_int(buf, (int64_t)added);
}
```

因为我们接收到的网络数据是字符串，所以需要将字符串转换成对应的数据。

`str2dbl`和`str2int`中，首先都先定义了`char *end;`这是用来在使用`strtod`和`strtoll`时，存放解析结束的位置，如果遇到不能解析的符号，就停留在那里，否则，就指向字符串的末尾。

使用`strtod`和`strtoll`将字符串转换成对应的数据，`stroll`中的`10`就是按照十进制来转换的。

在判断 `endp == s.c_str() + s.size()` 时，其实就是在验证字符串是否被完全成功解析。  

- `s.c_str()` 会把 `std::string` 转换成 **C 风格字符串** `(const char*)`，返回一个指向首字符的指针。  
- `s.c_str() + s.size()` 指向的是字符串的末尾（即最后一个字符的下一个位置，通常是 `\0` 的位置）。  
- 如果 `endp` 没有指向这个末尾，就说明解析过程提前停止了，后面还有未能解析的内容，此时就认为解析失败。  
- 只有当 `endp` 恰好等于字符串末尾时，才说明整个字符串都被正确解析。  

举例说明：  
- 输入 `"123"` → `endp` 会指向字符串末尾，表示解析成功。  
- 输入 `"123abc"` → `endp` 会停在 `'a'` 处，说明 `"abc"` 不是合法数字，因此解析不完整。  


在我们的`do_add`中，我们仍然是使用了一个新的结构体来辅助查询，这个结构体的作用也和我们上面将的一样，`hm_lookup`需要`HNode`的参数，同时又需要上级的结构体中的内容来进行比对，也就是我们传入的`entry_eq`，所以需要我们新建一个`LookupKey`结构体。


## zrem()

```cpp
// delete by name
void zset_delete(ZSet* zset, ZNode* node){
    // remove from the hashtable
    HKey key;
    key.node.hcode = node->hmap.hcode;
    key.name = node->name;
    key.len = node->len;
    HNode* found = hm_delete(&zset->hmap, &key.node, &hcmp);
    assert(found);
    // remove from the AVL tree
    zset->root = avl_del(&node->tree);
    znode_del(node);
}
```

对于我们删除的函数`HNode* hm_delete(HMap* hmap,HNode* key,bool (*eq)(HNode* , HNode*))`，同样也是需要我们的`HKey`来辅助删除的，`hcmp`通过比对`node`上级结构体中的数据，来辅助查找对应的节点。


```cpp

static const ZSet k_empty_zset;

static ZSet* expect_zset(std::string &s){
    LookupKey key;
    key.key.swap(s);
    key.node.hcode = str_hash((uint8_t*)key.key.data(), key.key.size());
    HNode* hnode = hm_lookup(&g_data.db, &key.node, &entry_eq);
    if(!hnode){
        // a non-existent key is treated as an empty zset
        return (ZSet*)&k_empty_zset;
    }
    Entry* ent = container_of(hnode, Entry, node);
    return ent->type == T_ZSET ? &ent->zset : nullptr;
}

static void do_zrem(std::vector<std::string> &cmd, Ring_buf &buf){
    ZSet* zset = expect_zset(cmd[1]);
    if(!zset){
        return out_err(buf, ERR_BAD_TYP, "expect zset");
    }

    const std::string &name = cmd[2];
    ZNode* znode = zset_lookup(zset, name.data(), name.size());
    if(znode){
        zset_delete(zset, znode);
    }
    return out_int(buf, znode ? 1 : 0);
}
```

> `LookupKey`的使用与`HKey`类似，不过，`LookupKey`中的`HNode`代表(查找)的是`Entry`中的`HNode`

我们的`zrem`命令会先查找键，然后删除键中`ZSet`中的元素，而数据的**键**存储在`Entry`中，所以我们通过`expect_zset`来获取键对应的`ZSet`，然后通过`zset_delete`来删除键对应的元素。

在这其中，我们还定义了一个`static const ZSet k_zset_empty;`，用来作为，当`key`不存在时，返回的`ZSet`。

为什么我们要使用一个自己定义的空对象呢？

返回空对象 `k_empty_zset` 表**key 不存在时等同空集合**，并与 Redis 语义一致，让返回`nullptr`只有一种情况，即`key`存在但不是`ZSet`。

## zscore()

```cpp
static void do_zscore(std::vector<std::string> &cmd, Ring_buf &buf){
    ZSet* zset = expect_zset(cmd[1]);
    if(!zset){
        return out_err(buf, ERR_BAD_TYP, "expect zset");
    }

    const std::string &name = cmd[2];
    ZNode* znode = zset_lookup(zset, name.data(), name.size());
    return znode ? out_dbl(buf, znode->score) : out_nil(buf);
}
```

查找指定有序集(`ZSet`)中的成员(`name`)的分数(`score`)

这个似乎就不用多说了，先使用`expect_zset()`函数获取有序集，然后使用`zset_lookup()`函数查找成员，如果找到则返回分数，否则返回`nil`。

## zquery()

用来查找指定有序集(`ZSet`)中 **>=(score, name)**的成员
使用命令：`zquery zset score name offset limit` 
其中`offset`为查询的起始位置，`limit`为查询的个数

```cpp
// find the first (score, name) tuple that is >= key.
ZNode* zset_seekge(ZSet* zset, double score, const char* name, size_t len){
    AVLNode* found = nullptr;
    for(AVLNode* node = zset->root; node;){
        if(zless(node, score, name, len))
        {
            node = node->right;
        }
        else
        {
            found = node;
            node = node->left;
        }
    }
    return found ? container_of(found, ZNode, tree) : nullptr;
}
```

首先我们使用`zless`函数来判断当前节点的分数是否小于给定的分数。如果小于，则说明当前节点的分数小于给定的分数，那么我们就向右移动，同时记录当前大于 **(score, name)** 的节点，否则向左移动，直到找到第一个大于 **(score, name)** 的点。

```cpp
// offset into the succeeding or preceding node
ZNode* znode_offset(ZNode* node, int64_t offset){
    AVLNode* tnode = node ? avl_offset(&node->tree, offset) : nullptr;
    return tnode ? container_of(tnode, ZNode, tree) : nullptr;
}
```

这个代码就是通过`offset`找到，当前传入节点的**前驱**或**后继**

下面的代码是具体的实现

```cpp
AVLNode* avl_offset(AVLNode* node, int64_t offset){
  int64_t pos = 0; // the rank of difference from the starting node
  while(offset != pos){
    if(pos < offset && pos+avl_cnt(node->right) >= offset){
      // the target is inside the right subtree
      node = node->right;
      pos += avl_cnt(node->left) + 1;
    }
    else if(pos > offset && pos - avl_cnt(node->left) <= offset){
      // the target is inside the left subtree
      node = node->left;
      pos -= avl_cnt(node->right) + 1;
    }
    else{
      // go to the parent
      AVLNode* parent = node->parent;
      if(!parent){
        return nullptr;
      }
      if(parent->right == node){
        pos -= avl_cnt(node->left)+1;
      }
      else{
        pos += avl_cnt(node->right)+1;
      }
      node = parent;
    }
  }
  return node;
}
```

```cpp
         3
       /   \
      2     5
     /     /
    1     4
```
index:  0   1   2   3   4
value: [1] [2] [3] [4] [5]
                 P  -->  O
`offset`如果大于零，那就是要找当前节点的**右子树**的大小，如果**右子树**的大小不够，也就是说，`P`的移动，无法移动到我们要找的节点，所以我们要向上移动，增大我们要找的右子树的范围，让我们的`P`可以移动到对应的节点
`P`在向上移动的过程中，如果在移动前的节点是其父节点的右子树，那我们挪上去后，P要相应的减去左子树的大小，也就是向左移动
为什么要向左移动，假设我们在移动前节点的父节点上，想要移动到右子树，也就是更大的值的地方，我们的`P`是要向右移动的，而向右移动多少？那就是我们移动前的节点的左子树的大小(AVL中序遍历的输出是有序的，所以不必担心左子树的值比右子树的值大)
那么相应的，如果我们在移动前的节点是其父节点的左子树，那我们挪上去后，P要相应的加上右子树的大小，也就是向右移动


也正如上面我们所说的，我们要找到`pos == offset`的位置
当`pos < offset`时，也就是说，我们的`Offset`所指的位置，还在P所指位置的右侧，我们要向右移动，如果我们的右子树足够大`(avl_cnt)`，也就是说，P可以向右移动的距离足够大，那就可以直接移动到右子树中，查找对应的`offset`所指的位置
如果右子树不够大，那就只能向上移动，扩大我们可以移动的范围
同理，当`pos > offset`时，也就是说，我们的`Offset`所指的位置，还在`P`所指位置的左侧，我们要向左移动，如果我们的左子树足够大`(avl_cnt)`，也就是说，`P`可以向左移动的距离足够大，那就可以直接移动到左子树中，查找对应的`offset`所指的位置
如果左子树不够大，那就只能向上移动，扩大我们可以移动的范围

从节点 3 出发，offset = +2 (也就是要找 5 节点)
我们发现 3 的右子树的大小是 2 (5 节点和 4 节点)，也就是P所指的位置可以向右移动 2 个位置，刚好可以移动到 5 节点
那我们就进入右子树。

```cpp
// zquery zset score name offset limit 
static void do_zquery(std::vector<std::string> &cmd, Ring_buf &buf){
    // parse args
    double score = 0;
    if(!str2dbl(cmd[2], score)){
        return out_err(buf, ERR_BAD_ARG, "expect fp number");
    }

    const std::string &name = cmd[3];
    int64_t offset = 0, limit = 0;
    if(!str2int(cmd[4], offset) || !str2int(cmd[5],limit)){
        return out_err(buf, ERR_BAD_ARG, "expect int");
    }

    // get the zset
    ZSet* zset = expect_zset(cmd[1]);
    if(!zset){
        return out_err(buf, ERR_BAD_TYP, "expect zset");
    }

    // seek to the key
    if(limit <= 0){
        return out_arr(buf,0);
    }
    ZNode* znode = zset_seekge(zset, score, name.data(), name.size());
    znode = znode_offset(znode, offset);

    // output 
    size_t ctx = out_begin_arr(buf);
    int64_t n = 0;
    while(znode && n < limit){
        out_str(buf, znode->name, znode->len);
        out_dbl(buf, znode->score);
        znode = znode_offset(znode, 1);
        n += 2;
    }
    out_end_arr(buf, ctx, (uint32_t)n);

}
```

我们将上面的代码进行结合，先获取输入的`score`和`name`，再通过`except_zset`获取到对应的有序表(`ZSet`)，然后通过`zset_seekge`寻找到第一个大于`(score, name)`的`ZNode`，然后通过`znode_offset`计算跳过的个数，最后进行输出。

## end

这些就是代码修改的主体，其他的部分改动较小，我们就不再讲述了，鉴于代码放在这里实在太多，我给出我的github地址，大家可以去找`study/dev_4`的目录进行查看

github地址：[https://github.com/AuroBreeze/Implementing-Redis-in-C](https://github.com/AuroBreeze/Implementing-Redis-in-C)

