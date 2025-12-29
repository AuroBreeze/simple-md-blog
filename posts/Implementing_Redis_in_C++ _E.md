# Implementing Redis in C++ : E(AVL树详解)

## 前言

本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

本文章为续<<[Implementing Redis in C++ : D](https://blog.csdn.net/m0_58288142/article/details/150616831?fromshare=blogdetail&sharetype=blogdetail&sharerId=150616831&sharerefer=PC&sharesource=m0_58288142&sharefrom=from_link)>>所以本文章不再完整讲解全部代码，只讲解其不同的地方

## AVL树

在下面的一个章节中，原作者并没有继续修改`server`和`client`，而是讲了一部分关于`redis`中的`SkepList`，为了实现`SkepList`类似的功能，我们将实现一个跟更为通用的简单的`AVL树`。

为什么要选择`AVL树`，在所有的排序数据结构中`AVL树`, `红黑树`和`B树`在查询，修改，迭代的能力上都是相等的，我们选择一个能够较好处理**最坏情况**且比较容易实现的`AVL树`。

AVL树的优点：

1. 严格平衡
- AVL 树是 **高度平衡的二叉搜索树**。  
- 任意节点的左右子树高度差 **不超过 1**。  
- 树的高度始终保持在 `O(logN)`，避免退化成链表。
2. 查找效率高
- 由于严格平衡，**查找操作复杂度稳定为 `O(logN)`**。  
- 相比红黑树，AVL 树查找效率通常更好（树更矮更“瘦”）。 
3. 性能稳定
- 查找性能不依赖于数据插入顺序。  
- 即使在最坏情况下，树高也最多为 `1.44 * log2(N)`。  
- 在查找密集型场景（读多写少）中，AVL 树表现优越。  
4. 有序性强
- 中序遍历能直接得到一个 **有序序列**。  
- 适合实现范围查询、排序操作等场景。  

下面我们将具体讲解树和**AVL树**

## 树形数据结构

树是一种用于表示数据结构的数据结构，它由节点组成，每个节点都有若干个子节点，子节点的父节点为该节点。树一般有根节点、叶子节点和内部节点。

如下图所示：

```cpp
        A
       / \
      B   C
     / \   \
    D   E   F
       /
      G
```

树型数据结构有很多的关键词：

1. **节点**：树中的最小单位，每个节点都有数据域和指针域。也就是我们上图中的A、B、C、D、E、F、G都是节点。
2. **根节点(Root)**：树中的第一个节点，也就是我们上图中的A。
3. **父节点(parent)和子节点(child)**：父节点是某个节点的直接父节点，子节点是某个节点的直接子节点。比如我们上图中的A是B的父节点，B是A的子节点。
4. **兄弟节点(sibling)**：同一个父节点的节点，比如我们上图中的B和C都是A的兄弟节点。
5. **叶子节点(leaf)**：没有子节点的节点，比如我们上图中的D和F都是叶子节点。
6. **层号(level)**：节点的层数，根节点的层号为1，根节点的子节点的层号为2，以此类推。比如我们上图中的A的层号为1，B的层号为2，C的层号为2，D的层号为3，E的层号为3，F的层号为3。
7. **路径**：
  - 从一个节点到另一个节点所经过的节点序列
  - 路径长度 = 经过的边数(节点数-1)
8. **高度**：
  - 树的高度：从该节点到最远叶子节点的**最长路径长度**。比如我们上图，树的高度为3。
  - 节点的高度：从该节点到最远叶子节点的**最长路径长度**。比如我们上图，节点A的高度为3，节点B的高度为2，节点C的高度为1，节点D的高度为0，节点E的高度为1，节点F的高度为0。
9. **深度**：
  - 树深度：从根节点到叶子节点的**最长路径长度**。比如我们上图，树深度为3。
  - 节点深度：从根节点到该节点的**最长路径长度**。比如我们上图，节点A的深度为0，节点B的深度为1，节点C的深度为1，节点D的深度为2，节点E的深度为2，节点F的深度为2。
10. **子树**：任意一个节点和它的所有后代节点，可以看作一棵子树。
11. **度**：节点的度数，即节点的子节点数。比如我们上图，节点A的度数为2，节点B的度数为2，节点C的度数为1，节点D的度数为0，节点E的度数为1，节点F的度数为0。
12. **二叉树**：每个节点度 ≤ 2 的树，子节点区分为 左子节点 和 右子节点。

### 不平衡二叉树

```cpp
    A
     \
      B
       \
        C
         \
          D
```
在树中插入键的时候，会搜索到达某一还有空子节点的节点，并将新节点放到它的空子节点指针中，而我们插入的顺序会直接影响到树的平衡性。

> Q:为什么会影响树的平衡性？
> A:我们要使用的是平衡二叉树，平衡二叉树的插入规则要与调整一起使用，在不调整树结构的情况下，只按照插入规则进行插入，会导致树结构不平衡(退化)。

假如说我们的插入规则(也就是AVL树插入规则)：
- 如果比当前节点小，就插入左子树。
- 如果比当前节点大，就插入右子树。

首先比较根节点的值，如果比根节点小，就插入左子树，如果比根节点大，就插入右子树。

再比较左子树的子节点，如果比子节点的值小，就子节点的左子树，如果比子节点的值大，就子节点的右子树。

假设我们的插入顺序是：2, 5, 6, 8, 9

那我们得到的结果就是

```cpp
    2
     \
      5
       \
        6
         \
          8
           \
            9
```

我们的树结构直接退化成链表，也就是最坏的情况，搜索复杂度为O(N)。

相同的数据，我们插入的顺序改为：5, 8, 2, 6, 9

```cpp
       5
     /  \
    2    8
        / \
       6   9
```

这样树的结构就变的平衡了。



### 调整二叉树

在使用AVL树时，当任意节点的两个子树的高度差超过1时，就需要进行调整。AVL使用旋转来调整树结构，分为左旋和右旋两种(保证有序性，不改变树的中序遍历的输出)。

> AVL树核心平衡条件：任意一个节点的左右子树高度差 ≤ 1

这是原文的示例图(这个树结构本来就是平衡的，不需要调整，此处的图为演示主要作用)：

```cpp
  B                                D
┌─┴───┐      rotate-left       ┌───┴─┐
a ┆   D     ─────────────►     B   ┆ e
┆ ┆ ┌─┴─┐   ◄─────────────   ┌─┴─┐ ┆ ┆
┆ ┆ c ┆ e    rotate-right    a ┆ c ┆ ┆
┆ ┆ ┆ ┆ ┆                    ┆ ┆ ┆ ┆ ┆
a B c D e                    a B c D e
```

> 谨记：**左子树 < 根节点 < 右子树**

**左旋cpp**:
```cpp
Node *rot_left(Node *node) { // 假设出入B节点
    Node *new_node = node->right;   // D 节点
    Node *inner = new_node->left; // c 节点
    node->right = inner;    // 将B 节点的右子树指向c节点  B(根节点) < c(右子节点)
    new_node->left = node;  // D 节点的左子树指向B节点 B(左子节点) < D(根节点) < e(右子节点)
    return new_node;
}
```

**右旋cpp**:
```cpp
Node *rot_right(Node *node) { // 假设出入D节点

    Node *new_node = node->left;   // B 节点
    Node *inner = new_node->right; // c 节点
    node->left = inner; // D 节点的左子树指向c节点
    new_node->right = node;  // B 节点的右子树指向D节点
    return new_node;
}
```

> 我们要处理的就是**根节点的右子节点的左子节点(左旋)**和**根节点的左子节点的右子节点(右旋)**，这两个，还有**根节点**和**根节点的右子节点**，记住这四个就可以了，下面我们具体再分析为什么。

我们知道，`AVL`是有序的，那么`AVL`的有序是什么意思？就是中序遍历的结果是升序的。

> Q: 什么是中序遍历？
> A: 中序遍历是先访问左子树，然后访问根节点，最后访问右子树。

中序遍历伪代码：
```cpp
// 假设定义的树节点结构
struct Node {
    int val;
    Node* left;
    Node* right;
};

// 中序遍历函数
void inorder(Node* root) {
    if (root == nullptr) return;   // 空节点直接返回

    inorder(root->left);           // 1. 访问左子树
    visit(root->val);              // 2. 访问根节点
    inorder(root->right);          // 3. 访问右子树
}
```

在上图中，我们设定插入时就是有序的，左右两例经过旋转后的中序输出的结果都是没有变的，都是**a B c D e**有序的。

在理解左旋和右旋时，我们可以将左旋理解为**逆时针旋转**，右旋为**顺时针旋转**。在上图中，左旋，D取代B，B取代A，A取代C，C取代E，E取代D，右旋同理，就能很快的理解左旋和右旋。

这样我们再更深入的了解一下，旋转(重点讲解**左旋**)。

首先为了保证AVL树的有序性，在插入节点的时候要保证**左子树 < 根节点 < 右子树**，所以，在我们上图的示例中，他们的大小顺序就是**a < B < c < D < e**，在上图中，左旋前的节点是**B**，我们左旋为什么要选择**D**点而不是**C**点呢？

```cpp
  B                                c
┌─┴───┐      rotate-left       ┌───┴─┐
a ┆   D     ─────────────►     B   ┆ D
┆ ┆ ┌─┴─┐    ─────────────   ┌─┴   ┆ ┴─┐
┆ ┆ c ┆ e                    a ┆   ┆ ┆ e
┆ ┆ ┆ ┆ ┆                    ┆ ┆   ┆ ┆ ┆
a B c D e                    a B   c d e
```

虽然上面的图例看着，中序遍历输出的顺序并没有变化，但是这里是有问题的，上面我们强调了要保证**左子树 < 根节点 < 右子树**，在我们**B子节点**处，B子节点的右子节点能插什么数据？**什么都不能！！！**，因为大于a小于B(b)的节点只有c，**意思也就是，这里就永远空着一个空位了！**，这合理吗？这绝对不合理。

> 我们传入的根节点的**右子节点的左子节点**，就在整个顺序中，正处于大于根节点的位置，同时小于**自己的根节点**，这样就可以放置在传入的根节点的右子节节点的位置。

> 这也就告诉我们为什么要处理**根节点的右子节点的左子节点**和**根节点的左子节点的右子节点**，这两个节点。

所以我们才会选择**D节点**，并将小于D的右子节点c转移到B子节点下，这个过程你也可以看成**重心**的转移，那边重就将那边往相反的方向移动一个节点，右旋同理。

接下来我们看需要我们旋转的全部的四种情况:

> 谨记：**左子树 < 根节点 < 右子树**

1. **LL(左子树的左子树高)**：  **基础类型**  **一次旋转成型**

```cpp
    C (失衡)  h = 2
   /
  B           h = 1
 / 
A             h = 0
```

左子树的左子树高，又因为**左子树 < 根节点 < 右子树**，所以这里的中序遍历的输出顺序就是** A < B < C**，所以只需要将**B**旋转(**右旋**)到根节点，A在左，C在右即可。



2. **RR(右子树的右子树高)**：  **基础类型**  **一次旋转成型**

```cpp
  A
   \
    B
     \
      C
```

右子树的右子树高，又因为**左子树 < 根节点 < 右子树**，所以这里的中序遍历的输出顺序就是**A < B < C**，所以只需要将**B**旋转(**左旋**)到根节点，A在左，C在右即可。

3. **LR(左子树的右子树高)**：**基于LL类型**  **两次旋转成型**

```cpp
    A
   /
  C
   \
    B
```

左子树的右子树高，又因为**左子树 < 根节点 < 右子树**，所以这里的中序遍历的输出顺序就是** C < B < A**。

我们先将**C子节点**旋转(**左旋**)，这样旋转后，要是进行中序遍历的话，就不是我们上面的输出顺序了，因为我们单独进行的对**C节点**的旋转，A并没有处理，我们这样处理是为了后面再次旋转回正确的顺序和平衡树做铺垫。

```cpp
    A
   /
  B
 /
C
```

然后，将**A**旋转(**右旋**)(同**LL**的旋转方式)。

4. **RL(右子树的左子树高)**：  **基于RR类型**  **两次旋转成型**

```cpp
  A
   \
    B
   /
  C
```

左子树的右子树高，又因为**左子树 < 根节点 < 右子树**，所以这里的中序遍历的输出顺序就是** A < C < B**。

我们先将**B子节点**旋转(**右旋**)

```cpp
  A
   \
    C
     \
      B
```
然，再对**A**进行旋转(**左旋**)(同**RR**的旋转方式)


如果还是不太清除的话，我们可以继续看下面这张图

```cpp
  B                                D
┌─┴───┐      rotate-left       ┌───┴─┐
a ┆   D     ─────────────►     B   ┆ e
┆ ┆ ┌─┴─┐   ◄─────────────   ┌─┴─┐ ┆ ┆
┆ ┆ c ┆ e    rotate-right    a ┆ c ┆ ┆
┆ ┆ ┆ ┆ ┆                    ┆ ┆ ┆ ┆ ┆
a B c D e                    a B c D e
```

自行删除某些节点，来进行旋转，测试。



### 代码实现(avl.h完整 avl.cpp旋转)


```cpp
// 完整 avl.h
struct AVLNode{
    AVLNode* parent = nullptr;
    AVLNode* left = nullptr;
    AVLNode* right = nullptr;
    uint32_t height = 0; //subtree height
    uint32_t cnt = 0; // subtree size
};

inline void avl_init(AVLNode* node){
    node->left = nullptr;
    node->right = nullptr;
    node->parent = nullptr;
    node->height = 1;
    node->cnt = 1;
}

//helps
inline uint32_t avl_height(AVLNode* node){
    return node ? node->height : 0;
}

inline uint32_t avl_cnt(AVLNode* node){
    return node ? node->cnt : 0;
}

//API
AVLNode* avl_fix(AVLNode* node);
AVLNode* avl_del(AVLNode* node);
```

```cpp
static uint32_t max(uint32_t lhs, uint32_t rhs) {
  return lhs < rhs ? rhs : lhs;
}

static void avl_update(AVLNode *node) {
  node->height =
      1 + max(avl_height(node->left), avl_height(node->right)); 
  node->cnt = 1 + avl_cnt(node->left) + avl_cnt(node->right);
}
```

相信这里两处的代码很清晰，就不多赘述了。

> 要注意的是，avl_update 函数，要及时的更新节点的信息，在旋转完或插入删除节点的时候，要及时调用，更新信息

```cpp
  B                                D
┌─┴───┐      rotate-left       ┌───┴─┐
a ┆   D     ─────────────►     B   ┆ e
┆ ┆ ┌─┴─┐   ◄─────────────   ┌─┴─┐ ┆ ┆
┆ ┆ c ┆ e    rotate-right    a ┆ c ┆ ┆
┆ ┆ ┆ ┆ ┆                    ┆ ┆ ┆ ┆ ┆
a B c D e                    a B c D e
```

```cpp
static AVLNode *rot_left(AVLNode *node) {
  AVLNode *parent = node->parent;  // null
  AVLNode *new_node = node->right; // D
  AVLNode *inner = new_node->left; // C

  // node <-> inner
  node->right = inner; // D change to C
  if (inner) {
    inner->parent = node; // B become C's parent
  }
  // parent <- new_node
  new_node->parent = parent; // null become D's parent
  // new_node <-> node
  new_node->left = node;   // D change to B
  node->parent = new_node; // D become B's parent
  // auxiliary data
  avl_update(node);
  avl_update(new_node);
  return new_node;
}

static AVLNode *rot_right(AVLNode *node) {
  AVLNode *parent = node->parent;
  AVLNode *new_node = node->left;
  AVLNode *inner = new_node->right;

  node->left = inner;
  if (inner) {
    inner->parent = node;
  }
  new_node->parent = parent;
  new_node->right = node;
  node->parent = new_node;

  avl_update(node);
  avl_update(new_node);

  return new_node;
}
```
我们还是以上面的图为例，假设我们的`rot_left`传入的参数是`B`点，就按照我们之前讲的，处理**三个点**，**根节点：B**，**根节点右子树：D**，**根节点的右子节点的左子节点：c**。

注释解释的也很清楚了，本质的东西我们上面讲了，我们就不再多说了。

### 代码实现(avl.cpp平衡树)

```cpp
// the left substree is taller by 2
static AVLNode *avl_fix_left(AVLNode *node) {
  if (avl_height(node->left->left) < avl_height(node->left->right)) {
    node->left = rot_left(node->left);
  }
  return rot_right(node);
}

static AVLNode *avl_fix_right(AVLNode *node) {
  if (avl_height(node->right->right) < avl_height(node->right->left)) {
    node->right = rot_right(node->right);
  }
  return rot_left(node);
}

AVLNode *avl_fix(AVLNode *node) {
  while (true) {
    AVLNode **from = &node; // save the fixed subtree here
    AVLNode *parent = node->parent;
    if (parent) {
      from = parent->left == node ? &parent->left : &parent->right;
    }

    // auxiliary data
    avl_update(node);
    // fix the height difference of 2
    uint32_t l = avl_height(node->left);
    uint32_t r = avl_height(node->right);

    if (l == r + 2) {
      *from = avl_fix_left(node);
    } else if (l + 2 == r) {
      *from = avl_fix_right(node);
    }

    // root node, stop
    if (!parent) {
      return *from;
    }

    node = parent;
  }
}
```

我们上面也说了，`AVL`插入或删除的时候，会出现`LL`、`RR`、`LR`、`RL`四种情况，但是`LR`基于`LL`，`RL`基于`RR`，所以，我们使用`avl_fix_left`和`avl_fix_right`来处理`LL LR`和`RR RL`。

假设我们当前的树结构

```cpp
    A                      // 这一层不平衡
   /
  B
   \
    C
```

我们在`avl_fix_left`和`avl_fix_right`中，也看到了`if (avl_height(node->left->left) < avl_height(node->left->right))`和`if (avl_height(node->right->left) > avl_height(node->right->right))`，这就是判断节点是否为`LR 旋转`和`RL 旋转`的判断条件。按上图，要注意的是，我们往`avl_fix_left`传入的是`A`点，所以，**node->right**就是`B`点，也符合我们上面说的，在`B`点先进行左旋，再进行右旋。

而在我们的`avl_fix`中，我们从下到上进行遍历，如果发现节点的高度差大于2，就调用`avl_fix_left`或`avl_fix_right`来进行旋转，直到根节点。

在`avl_fix`中`from`存储当前`node`节点的信息，`parent`则指向当前节点的符节点(在最后将信息全部给node，进行循环)，而其中`from = parent->left == node ? &parent->left : &parent->right;`的`from`成为**父节点里指向当前子树的那个指针**,也就是说，from再指向的地址就会改变父节点中`left`或`right`指向的地址。

假设你旋转了 N 这个子树，比如：下面是图示例：

```cpp
    P
   /
  N
 / \
... ...
```

旋转后`N`换成了`M`(比如`N`的右孩子上升了)。

那么你需要做的就是：

```cpp
*from = M;   // 修改 P->left = M;
```

这样，`P`的左孩子就指向了`M`节点，父节点`P`的指针就能正确指向新的子节点。

### 代码实现(删除节点)

```cpp
static AVLNode* avl_del_easy(AVLNode* node){
  assert(!node->left || !node->right); // at most one child
  AVLNode *child = node->left ? node->left : node->right;
  AVLNode* parent = node->parent;
  //update the child's parent pointer
  if(child){
    child->parent = parent;
  }
  // attach the child to the gendparent
  if(!parent){
    return child; // removing the root node
  }
  AVLNode* *from = parent->left == node ? &parent->left : &parent->right;
  *from = child;
  //rebalance the update tree
  return avl_fix(parent);    
}
```

当我们要删除的节点最多只有一个子节点的时候，将要删除的节点的子节点的`parent`指向要删除的节点的`parent`节点，并使用`AVLNode* *from = parent->left == node ? &parent->left : &parent->right;`让我们将要删除的节点的子节点的挂载到父节点的父节点的`left`或`right`上。

```cpp
if(child){
  child->parent = parent;
}
```

把`child`的`parent`改成`node`的`paren`

```cpp
AVLNode** from = parent->left == node ? &parent->left : &parent->right;
*from = child;
```

如果`node`是`parent->left`，就更新`parent->left = child`

如果`node`是`parent->right`，就更新`parent->right = child`

```cpp
return avl_fix(parent);
```

删除一个节点可能让`AVL树`失衡，所以从`parent`开始往上回溯，逐层修复。

```cpp
//detach a node and returns the new root of the tree
AVLNode* avl_del(AVLNode* node){
  // the easy case of 0 or 1 child 
  if(!node->left || !node->right){
    return avl_del_easy(node);
  }
  // find the successor
  AVLNode* victim = node->right;
  while(victim->left){
    victim = victim->left;
  }
  // detach the successor
  AVLNode* root = avl_del_easy(victim);
  // swap with the successor
  // fix the pointers to make the child parent's pointer point to the successor
  *victim = *node; // left, right, parent
  // this approach changes the memory, leading to the need to fix the child's pointer

  if(victim->left){
    victim->left->parent = victim;
  }
  if(victim->right){
    victim->right->parent = victim;
  }
  // attach the successor to the parent. or update the root pointer
  AVLNode* *from = &root;
  AVLNode* parent = node->parent;
  if(parent){
    from = parent->left == node ? &parent->left : &parent->right;
  }
  *from = victim;
  return root;
}
```

假设我们的树结构是这样的

```cpp
        5
       / \
      3   8
         / \
        6   9
```

他的中序输出顺序就是`3 5 6 8 9`

假设要删除的点是**5**

那我们要做的就是把中序输出的**5**的后面的数字提到前面来，放到树中。

所以我们要找比**5**大(在右子树中)，但是是仅比**5**大，比其他的要小(在右子树的左子树中)，也就是`while(victim->left){victim = victim->left;}`，找到仅大于**5**的点，也就是**6**，我们要把**6**在树中删掉，并顶替掉**5**的位置。

我们直接使用`avl_del_easy`将**6**从树中切离，使用`*victim = *node;`将**5**的信息复制到**6**上(也就是把**5**的指针的内容`left`，`right`d等信息复制到**6**上)，将**6**替换掉**5**的位置，最后我们修正父子关系，使`6->left->parent = 6`(修正**3**的父亲)，`6->right->parent = 6`(修正**8**的父亲)

最后，我们返回根节点，也就是`avl_fix(parent)`，修正**6**的高度，使其平衡。

### end 

至此，我们的`AVL`树就实现了，具体的实例代码和测试代码，我都放在下面了。

具体的测试代码就不再详细解释，大家可以自行参考。

## code

```cpp
//avl.h

#include <stdint.h>
struct AVLNode{
    AVLNode* parent = nullptr;
    AVLNode* left = nullptr;
    AVLNode* right = nullptr;
    uint32_t height = 0; //subtree height
    uint32_t cnt = 0; // subtree size
};

inline void avl_init(AVLNode* node){
    node->left = nullptr;
    node->right = nullptr;
    node->parent = nullptr;
    node->height = 1;
    node->cnt = 1;
}

//helps
inline uint32_t avl_height(AVLNode* node){
    return node ? node->height : 0;
}

inline uint32_t avl_cnt(AVLNode* node){
    return node ? node->cnt : 0;
}

//API
AVLNode* avl_fix(AVLNode* node);
AVLNode* avl_del(AVLNode* node);
```

```cpp
//avl.cpp

#include "avl.h"
#include <cassert>
#include <stdint.h>

static uint32_t max(uint32_t lhs, uint32_t rhs) {
  return lhs < rhs ? rhs : lhs;
}

static void avl_update(AVLNode *node) {
  node->height =
      1 + max(avl_height(node->left), avl_height(node->right));
  node->cnt = 1 + avl_cnt(node->left) + avl_cnt(node->right);
}

//   B                                D
// ┌─┴───┐      rotate-left       ┌───┴─┐
// a ┆   D     ─────────────►     B   ┆ e
// ┆ ┆ ┌─┴─┐   ◄─────────────   ┌─┴─┐ ┆ ┆
// ┆ ┆ c ┆ e    rotate-right    a ┆ c ┆ ┆
// ┆ ┆ ┆ ┆ ┆                    ┆ ┆ ┆ ┆ ┆
// a B c D e                    a B c D e

static AVLNode *rot_left(AVLNode *node) {
  AVLNode *parent = node->parent;  // null
  AVLNode *new_node = node->right; // D
  AVLNode *inner = new_node->left; // C

  // node <-> inner
  node->right = inner; // D change to C
  if (inner) {
    inner->parent = node; // B become C's parent
  }
  // parent <- new_node
  new_node->parent = parent; // null become D's parent
  // new_node <-> node
  new_node->left = node;   // D change to B
  node->parent = new_node; // D become B's parent
  // auxiliary data
  avl_update(node);
  avl_update(new_node);
  return new_node;
}

static AVLNode *rot_right(AVLNode *node) {
  AVLNode *parent = node->parent;
  AVLNode *new_node = node->left;
  AVLNode *inner = new_node->right;

  node->left = inner;
  if (inner) {
    inner->parent = node;
  }
  new_node->parent = parent;
  new_node->right = node;
  node->parent = new_node;

  avl_update(node);
  avl_update(new_node);

  return new_node;
}

// the left substree is taller by 2
static AVLNode *avl_fix_left(AVLNode *node) {
  if (avl_height(node->left->left) < avl_height(node->left->right)) {
    node->left = rot_left(node->left);
  }
  return rot_right(node);
}

static AVLNode *avl_fix_right(AVLNode *node) {
  if (avl_height(node->right->right) < avl_height(node->right->left)) {
    node->right = rot_right(node->right);
  }
  return rot_left(node);
}

AVLNode *avl_fix(AVLNode *node) {
  while (true) {
    AVLNode **from = &node; // save the fixed subtree here
    AVLNode *parent = node->parent;
    if (parent) {
      from = parent->left == node ? &parent->left : &parent->right;
    }

    // auxiliary data
    avl_update(node);
    // fix the height difference of 2
    uint32_t l = avl_height(node->left);
    uint32_t r = avl_height(node->right);

    if (l == r + 2) {
      *from = avl_fix_left(node);
    } else if (l + 2 == r) {
      *from = avl_fix_right(node);
    }

    // root node, stop
    if (!parent) {
      return *from;
    }

    node = parent;
  }
}

static AVLNode* avl_del_easy(AVLNode* node){
  assert(!node->left || !node->right); // at most one child
  AVLNode *child = node->left ? node->left : node->right;
  AVLNode* parent = node->parent;
  //update the child's parent pointer
  if(child){
    child->parent = parent;
  }
  // attach the child to the gendparent
  if(!parent){
    return child; // removing the root node
  }
  AVLNode* *from = parent->left == node ? &parent->left : &parent->right;
  *from = child;
  //rebalance the update tree
  return avl_fix(parent);    
}

//detach a node and returns the new root of the tree
AVLNode* avl_del(AVLNode* node){
  // the easy case of 0 or 1 child 
  if(!node->left || !node->right){
    return avl_del_easy(node);
  }
  // find the successor
  AVLNode* victim = node->right;
  while(victim->left){
    victim = victim->left;
  }
  // detach the successor
  AVLNode* root = avl_del_easy(victim);
  // swap with the successor
  // fix the pointers to make the child parent's pointer point to the successor
  *victim = *node; // left, right, parent
  // this approach changes the memory, leading to the need to fix the child's pointer

  if(victim->left){
    victim->left->parent = victim;
  }
  if(victim->right){
    victim->right->parent = victim;
  }
  // attach the successor to the parent. or update the root pointer
  AVLNode* *from = &root;
  AVLNode* parent = node->parent;
  if(parent){
    from = parent->left == node ? &parent->left : &parent->right;
  }
  *from = victim;
  return root;
}
```

```cpp
//test_avl.cpp

#include <cassert>
#include <iostream>
#include <set>
#include "avl.h"

#define container_of(ptr, type, member)({ \
    const typeof( ((type*)0)->member)* __mptr = (ptr);\
    (type*)( (char*)__mptr - offsetof(type, member));})

struct Data {
    AVLNode node;
    uint32_t val = 0;
};

struct Container {
    AVLNode *root = nullptr;
};

static void add(Container &c, uint32_t val) {
    Data *data = new Data();    // allocate the data
    avl_init(&data->node);
    data->val = val;

    AVLNode *cur = nullptr;        // current node
    AVLNode **from = &c.root;   // the incoming pointer to the next node
    while (*from) {             // tree search
        cur = *from;
        uint32_t node_val = container_of(cur, Data, node)->val;
        from = (val < node_val) ? &cur->left : &cur->right;
    }
    *from = &data->node;        // attach the new node
    data->node.parent = cur;
    c.root = avl_fix(&data->node);
}

static bool del(Container &c, uint32_t val) {
    AVLNode *cur = c.root;
    while (cur) {
        uint32_t node_val = container_of(cur, Data, node)->val;
        if (val == node_val) {
            break;
        }
        cur = val < node_val ? cur->left : cur->right;
    }
    if (!cur) {
        return false;
    }

    c.root = avl_del(cur);
    delete container_of(cur, Data, node);
    return true;
}

static void avl_verify(AVLNode *parent, AVLNode *node) {
    if (!node) {
        return;
    }

    assert(node->parent == parent);
    avl_verify(node, node->left);
    avl_verify(node, node->right);

    assert(node->cnt == 1 + avl_cnt(node->left) + avl_cnt(node->right));

    uint32_t l = avl_height(node->left);
    uint32_t r = avl_height(node->right);
    assert(l == r || l + 1 == r || l == r + 1);
    assert(node->height == 1 + std::max(l, r));

    uint32_t val = container_of(node, Data, node)->val;
    if (node->left) {
        assert(node->left->parent == node);
        assert(container_of(node->left, Data, node)->val <= val);
    }
    if (node->right) {
        assert(node->right->parent == node);
        assert(container_of(node->right, Data, node)->val >= val);
    }
}

static void extract(AVLNode *node, std::multiset<uint32_t> &extracted) {
    if (!node) {
        return;
    }
    extract(node->left, extracted);
    extracted.insert(container_of(node, Data, node)->val);
    extract(node->right, extracted);
}

static void container_verify(
    Container &c, const std::multiset<uint32_t> &ref)
{
    avl_verify(nullptr, c.root);
    assert(avl_cnt(c.root) == ref.size());
    std::multiset<uint32_t> extracted;
    extract(c.root, extracted);
    assert(extracted == ref);
}

static void dispose(Container &c) {
    while (c.root) {
        AVLNode *node = c.root;
        c.root = avl_del(c.root);
        delete container_of(node, Data, node);
    }
}

static void test_insert(uint32_t sz) {
    for (uint32_t val = 0; val < sz; ++val) {
        Container c;
        std::multiset<uint32_t> ref;
        for (uint32_t i = 0; i < sz; ++i) {
            if (i == val) {
                continue;
            }
            add(c, i);
            ref.insert(i);
        }
        container_verify(c, ref);

        add(c, val);
        ref.insert(val);
        container_verify(c, ref);
        dispose(c);
    }
}

static void test_insert_dup(uint32_t sz) {
    for (uint32_t val = 0; val < sz; ++val) {
        Container c;
        std::multiset<uint32_t> ref;
        for (uint32_t i = 0; i < sz; ++i) {
            add(c, i);
            ref.insert(i);
        }
        container_verify(c, ref);

        add(c, val);
        ref.insert(val);
        container_verify(c, ref);
        dispose(c);
    }
}

static void test_remove(uint32_t sz) {
    for (uint32_t val = 0; val < sz; ++val) {
        Container c;
        std::multiset<uint32_t> ref;
        for (uint32_t i = 0; i < sz; ++i) {
            add(c, i);
            ref.insert(i);
        }
        container_verify(c, ref);

        assert(del(c, val));
        ref.erase(val);
        container_verify(c, ref);
        dispose(c);
    }
}

int main() {
    Container c;

    // some quick tests
    container_verify(c, {});
    add(c, 123);
    container_verify(c, {123});
    assert(!del(c, 124));
    assert(del(c, 123));
    container_verify(c, {});

    // sequential insertion
    std::multiset<uint32_t> ref;
    for (uint32_t i = 0; i < 100; i += 3) {
        add(c, i);
        ref.insert(i);
        container_verify(c, ref);
    }

    // random insertion
    for (uint32_t i = 0; i < 100; i++) {
        uint32_t val = (uint32_t)rand() % 1000;
        add(c, val);
        ref.insert(val);
        container_verify(c, ref);
    }

    // random deletion
    for (uint32_t i = 0; i < 100; i++) {
        uint32_t val = (uint32_t)rand() % 1000;
        auto it = ref.find(val);
        if (it == ref.end()) {
            assert(!del(c, val));
        } else {
            assert(del(c, val));
            ref.erase(it);
        }
        container_verify(c, ref);
    }

    // insertion/deletion at various positions
    for (uint32_t i = 0; i < 100; ++i) {
        test_insert(i);
        test_insert_dup(i);
        test_remove(i);
    }

    dispose(c);
    return 0;
}
```