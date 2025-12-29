# Implementing Redis in C++ : F
# Redis C++ 实现笔记（G篇）

## 前言

本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

本文章为续<<[Redis C++ 实现笔记（F篇）](https://blog.csdn.net/m0_58288142/article/details/151196170?fromshare=blogdetail&sharetype=blogdetail&sharerId=151196170&sharerefer=PC&sharesource=m0_58288142&sharefrom=from_link)>>所以本文章不再完整讲解全部代码，只讲解其不同的地方

## 超时

作为`redis-like`的项目，我们直到，`redis`是有超时机制**键过期机制**和**客户端空闲超时**的，其中在这里实现的是**客户端空闲超时**

在我们，之前的项目中，我们使用`int rv = WSAPoll(poll_args.data(), (ULONG)poll_args.size(), -1);`来一直等待连接的监听，但是这样就会有一个问题，如果这个客户端长时间的不进行连接的话，会占用我们的系统资源，当连接源很多时，就会造成系统资源不足，所以，我们就需要哦设计一个超时机制来，设置一个超时时间，当超过这个时间，就关闭这个连接。

## 主体思路

在原作者的文章中，原作者使用的是**双端队列**来保存连接，同时在**双端队列**中使用**哨兵节点**，用哨兵节点的`next`指针指向**最久未活跃的连接**，用`prev`指针指向**最活跃的连接**，这样，我们就可以通过查找到我们我们即将超时的节点，并将其删除。

对于计时的选择，我们选择使用`monotonic_clock`来获取时间，这是一个单调时钟，能够保证时间的单调递增，它是统计自系统启动，并以毫秒为单位返回一个64位无符号整数。我们为什么不选择`system_clock`？这是因为，如果我们回调计算机的时间，会影响这个时间的判断，具体不再讲述，需细致了解的阅读者可以自行了解。

为方便快速理解本文章，给出双端队列的以下图示，方便快速理解本文章：

```cpp
   [idle_list] next → ConnA → ConnB → ConnC → next [idle_list]
   [idle_list] prev ← ConnA ← ConnB ← ConnC ← prev [idle_list]

   其中ConnA是最久未活跃的连接，ConnC是最活跃的连接

   idle_list <-> A <-> B <-> C <-> idle_list
                 next------->
                 <---------prev
```

---

> # 为什么使用哨兵节点？
>
> 哨兵节点（sentinel node）并不是必须的，但它能让双端队列的操作更简洁统一。
>
> **1. 判空操作**
>
> * 不带哨兵节点：需要判断 `head == nullptr` 或 `tail == nullptr`。
> * 带哨兵节点：只需判断 `sentinel->next == sentinel`。
>
> **2. 插入/删除操作**
>
> * 不带哨兵节点：插入/删除时要区分队头、队尾和中间节点，代码繁琐。
> * 带哨兵节点：所有情况逻辑统一，只需更新相邻节点的 `prev` 和 `next`。
>
> **3. 快速找到队头/队尾**
>
> * 不带哨兵节点：需要维护两个指针 `head` 和 `tail`。
> * 带哨兵节点：
>
>   * 队头：`sentinel->next`
>   * 队尾：`sentinel->prev`
>
> **总结**
>
> * 判空更简单：`sentinel->next == sentinel`。
> * 插入/删除更统一：不必区分头/尾/中间。
> * 访问队头/队尾更方便：通过 `sentinel->next/prev` 即可。


```cpp
这是在整体上，双端队列的作用

g_data
├── fd2connmap : unordered_map
├── idle_list : DList
      └── idle_node(Conn:DList) ---> idle_node(Conn:DList) --->  ......
└── db : HMap

static struct {
    HMap db;

    // fd -> conn
    unordered_map<SOCKET, Conn*> fd2conn_map;
    // timers for idle connections
    DList idle_list;
} g_data;

struct Conn {
    /*
      other fields    
    */
    // timer
    uint64_t last_active_msec = 0;
    DList idle_node;
};
```

## list.h

```cpp
#pragma once

#include <cstddef>

struct DList{
    DList* prev = nullptr;
    DList* next = nullptr;
};

inline void dlist_init(DList* node){
    node->prev = node->next = node;
}

inline bool dlist_empty(DList* node){
    return node->next == node;
}

inline void dlist_detach(DList* node){
    DList* prev = node->prev;
    DList* next = node->next;    
    prev->next = next;
    next->prev = prev;
}

// insert node to the list before target
inline void dlist_insert_before(DList* target, DList* rookie){
    DList* prev = target->prev;
    prev->next = rookie;
    rookie->next = target;
    rookie->prev = prev;
    target->prev = rookie;
}
```

我们使用`dlist_init()`来初始化哨兵节点，让他的所有指针都指向自己，这样同时也代表了这个双端队列为空。

`dlist_detach()`用来删除一个节点，我们可以看以下的图示(删除B节点)：

```cpp
删除前：
+-----------+     +-----------+     +-----------+     +-----------+     +-----------+
| idle_list |<--->|   ConnA   |<--->|   ConnB   |<--->|   ConnC   |<--->| idle_list |
+-----------+     +-----------+     +-----------+     +-----------+     +-----------+

指针关系：
 ConnA.next ----> ConnB
 ConnB.prev ----> ConnA
 ConnB.next ----> ConnC
 ConnC.prev ----> ConnB


删除过程（dlist_detach）：
 ConnB.prev ----> ConnA
 ConnB.next ----> ConnC

 1) prev->next = next
    ConnA.next -----------┐
                          v
                        ConnC

 2) next->prev = prev
    ConnC.prev -----------┐
                          v
                        ConnA


删除后：
+-----------+     +-----------+     +-----------+     +-----------+
| idle_list |<--->|   ConnA   |<--->|   ConnC   |<--->| idle_list |
+-----------+     +-----------+     +-----------+     +-----------+

指针关系：
 ConnA.next ----> ConnC
 ConnC.prev ----> ConnA
```

删除的功能似乎不必多说，只需要将要被影响的两个节点找出来，然后修改这两个节点的指针关系就可以完成删除了。

`dlist_insert_before()`用来插入一个节点，我们可以看以下的图示(插入X节点，在A，B节点中间)：

```cpp
插入前：
+-----------+     +-----------+     +-----------+     +-----------+
| idle_list |<--->|   ConnA   |<--->|   ConnB   |<--->|   ConnC   |
+-----------+     +-----------+     +-----------+     +-----------+

指针关系：
 ConnA.next ----> ConnB
 ConnB.prev ----> ConnA
 ConnB.next ----> ConnC
 ConnC.prev ----> ConnB


插入过程（dlist_insert_before(target=ConnB, rookie=ConnX)）：
 prev = ConnB.prev  (即 ConnA)

 1) prev->next = rookie
    ConnA.next -----------┐
                          v
                        ConnX

 2) rookie->next = target
    ConnX.next -----------┐
                          v
                        ConnB

 3) rookie->prev = prev
    ConnX.prev -----------┐
                          v
                        ConnA

 4) target->prev = rookie
    ConnB.prev -----------┐
                          v
                        ConnX


插入后：
+-----------+     +-----------+     +-----------+     +-----------+     +-----------+
| idle_list |<--->|   ConnA   |<--->|   ConnX   |<--->|   ConnB   |<--->|   ConnC   |
+-----------+     +-----------+     +-----------+     +-----------+     +-----------+

指针关系：
 ConnA.next ----> ConnX
 ConnX.prev ----> ConnA
 ConnX.next ----> ConnB
 ConnB.prev ----> ConnX
 ConnB.next ----> ConnC
 ConnC.prev ----> ConnB
```

如果，不理解的话，可以自己画图并标记节点的值，来进行理解

总之，只需要记住:

```cpp
   idle_list <-> A <-> B <-> C <-> idle_list
                 next------->
                 <---------prev
```

## main
```cpp
int main() {
    // initialization
    dlist_init(&g_data.idle_list);

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

    // unordered_map<SOCKET, Conn*> fd2conn_map;
    vector<WSAPOLLFD> poll_args;

while (true) {
    poll_args.clear();

    // 监听 socket
    WSAPOLLFD pfd_listen{};
    pfd_listen.fd = fd;
    pfd_listen.events = POLLIN;  // 只监听读事件
    poll_args.push_back(pfd_listen);

    // 连接 socket
    for (auto &kv : g_data.fd2conn_map) {
        SOCKET cfd = kv.first;
        Conn* conn = kv.second;
        if (!conn) continue;

        WSAPOLLFD pfd{};
        pfd.fd = cfd;
        pfd.events = 0;
        if (conn->want_read)  pfd.events |= POLLIN;
        if (conn->want_write) pfd.events |= POLLOUT;

        poll_args.push_back(pfd);
    }

    // 计算 timeout，确保 >= -1
    int32_t timeout_ms = next_timer_ms();

    int rv = WSAPoll(poll_args.data(), (ULONG)poll_args.size(), timeout_ms);
    if (rv == SOCKET_ERROR) {
        int err = WSAGetLastError();
        fprintf(stderr, "[%d] WSAPoll() failed\n", err);
        exit(1);
    }

    // 处理监听 socket
    if (poll_args[0].revents & POLLIN) {
        Conn* conn = handle_accept(fd);

    }

    // 处理连接 sockets
    for (size_t i = 1; i < poll_args.size(); ++i) {
        uint32_t ready = poll_args[i].revents;
        if (ready == 0) continue;

        Conn* conn = g_data.fd2conn_map[poll_args[i].fd];
        if (!conn) continue;

        // 更新时间，维护 idle_list
        conn->last_active_msec = get_monotonic_msec();
        dlist_detach(&conn->idle_node);
        dlist_insert_before(&g_data.idle_list, &conn->idle_node);

        if (ready & POLLIN)  handle_read(conn);
        if (ready & POLLOUT) handle_write(conn);

        if ((ready & POLLERR) || conn->want_close) {
            conn_destroy(conn);
        }
    }

    process_timers();
}
    closesocket(fd);
    WSACleanup();
    return 0;
}

```

相比之前我们的`main`函数，我们在这里的修改主要是，最开始的时候初始化`DList`(双端队列)，还有因为将我们的`fd2conn_map`转移到了`g_data`函数中，所以我们改成遍历`g_data.fd2conn_map`。

我们大致的主体逻辑并没有改变。

在`while`仍然保持第一个连接是监听端口，让后将我们所以的在`fd2conn_map`的连接转为`WSAPollFD`，并添加到`poll_args`中通过`WSAPoll`进行监听，因为我们增加了`timeout_ms`参数，其中`next_timer_ms()`函数中，会提取`Dlist`中的哨兵节点`next`指向的连接(最久未活跃的连接)，并计算最久未活跃的连接剩余的时间简介，并进行返回，放置到`WSAPoll`的参数中，我们的`handle_accept`(修改了部分代码)在监听到连接后，会将新连接加入到`DList`中，之后就是将活跃的连接进行更新，最后使用`process_timers`进行删除那些超时的连接。

> 需要注意的是，`WSAPoll`的参数`timeout_ms`为-1时，表示一直等待，直到有事件发生，但是`timeout_ms`的参数不能小于`-1`否则会报错。

## monotonic

```cpp
#include <time.h>
#define CLOCK_MONOTONIC  1
typedef int clockid_t;

struct timespec {
  time_t  tv_sec;	/* Seconds */
  long    tv_nsec;	/* Nanoseconds */
};

static uint64_t get_monotonic_msec(){
    struct timespec tv = {0,0};
    clock_gettime(CLOCK_MONOTONIC, &tv);
    return uint64_t(tv.tv_sec) * 1000 + tv.tv_nsec / 1000 / 1000;
}

static int32_t next_timer_ms(){
    if(dlist_empty(&g_data.idle_list)){
        return -1; // no timers, no timeouts
    }

    uint64_t now_ms = get_monotonic_msec();
    Conn* conn = container_of(g_data.idle_list.next, Conn, idle_node);
    uint64_t next_ms = conn->last_active_msec + k_idle_timeout_ms;
    if(next_ms <= now_ms){
        return 0; // miss?
    }
    return (int32_t)(next_ms - now_ms);
}

static void process_timers(){
    uint64_t now_ms = get_monotonic_msec();
    // debug_idle_list();
    
    while(!dlist_empty(&g_data.idle_list)){
        Conn* conn = container_of(g_data.idle_list.next, Conn, idle_node);
        uint64_t next_ms = conn->last_active_msec + k_idle_timeout_ms;
        if(next_ms >= now_ms){
            break;
        }
        fprintf(stderr, "removing idle connection: %d\n", conn->fd);
        conn_destroy(conn);
    }
    // debug_idle_list();
}
```

这些代码并不难理解，我们也不再赘述了。

## end

这些就是代码修改的主体，其他的部分改动较小，我们就不再讲述了，鉴于代码放在这里实在太多，我给出我的github地址，大家可以去找`study/dev_5`的目录进行查看

github地址：[https://github.com/AuroBreeze/Implementing-Redis-in-C](https://github.com/AuroBreeze/Implementing-Redis-in-C)






