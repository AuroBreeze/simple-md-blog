# Implementing Redis in C++ : A

## 前言

本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

## socket(servers)

### windows使用socket前置
因为`windoows`与`linux`平台的不同，想要在`windows`平台下实现`socket`，需要引入`winsock2.h`头文件，并调用`WSAStartup()`函数，初始化`socket`环境。

> 需要注意的是，`WSAstartup()`是必须调用的，否则`socket`将无法使用。同时也需要注意，在程序结束后需要调用`WSACleanup()`函数，清理`socket`环境，释放`Winsock`所占的资源。

```cpp
WSADATA wsaData;
if(WSAStartup(MAKEWORD(2,2), &wsaData) != 0){
    std::cerr << "WSAStartup() failed" << std::endl;
    return 1;
}
```

如果我们在**windows**下运行，但是不使用上述代码，`socket`将无法运行，所有 socket 调用都会失败，返回 SOCKET_ERROR。

但是在**linux**下运行，则不需要上述代码。

### start

#### socket()
```cpp
SOCKET socket = socket(AF_INET, SOCK_STREAM, 0);
if(socket == INVALID_SOCKET){
    die("socket() failed"); // die() 函数 后续进行编写，其功能为输出错误信息并正常退出程序
}
```

`socket`函数返回一个套接字描述符`SOCKET`，如果创建失败，则返回 **INVALID_SOCKET**。

这个套接字描述符`SOCKET`是一个无符号整数类型，我们以后会用它来发送数据，接收数据，关闭套接字等等。~~(typedef UINT SOCKET;)~~

`AF_INET`表示使用IPV4协议，除此之外，还有`AF_INET6`，`AF_UNIX`，`AF_UNSPEC`等等。
`SOCK_STREAM`表示使用TCP协议，除此之外，还有`SOCK_DGRAM`，`SOCK_RAW`等等。
`0`表示使用默认协议，这个参数也可以使用`IPPROTO_TCP`，`IPPROTO_UDP`等等。

#### sockaddr{},htons(),htonl()
```cpp
sockaddr_in addr{}; // 创建一个sockaddr_in结构体变量,主要作用为存储套接字地址信息
addr.sin_family = AF_INET; // 设置套接字类型为IPv4
addr.sin_port = htons(6379); // 设置端口号
addr.sin_addr.s_addr = htonl(INADDR_ANY); // 设置IP地址为任意
```

```cpp
struct sockaddr {
	u_short	sa_family;
	char	sa_data[14];
};

struct sockaddr_in {
	short	sin_family;
	u_short	sin_port;
	struct in_addr	sin_addr;
	char	sin_zero[8];
};
```

`sockaddr_in`结构体变量`addr`中，`sin_family`字段表示协议类型，`sin_port`字段表示端口号，`sin_addr`字段表示IP地址。

而其中的`sin_zero[8]`的主要作用为**填充**，稍后进行讲解`sockaddr`和`sockaddr_in`结构体的关系。


使用的`htons()`和`htonl()`函数，分别将主机字节序转换为网络字节序，将网络字节序转换为主机字节序，因为不同CPU架构可能使用不同字节序（大端序/小端序），而网络协议统一规定使用大端序（Network Byte Order），而`htons()`专门用来转换**16位**短整型数据(port端口号)，`htonl()`用来转换**32位**长整型数据(IPV4地址)，当然也有相应的反向函数`ntohl()`、`ntohs()`。



#### setsockopt()
```cpp
    int opt = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt)); // 设置端口复用
```

这里代码的主要作用是设置端口复用，即多个进程可以绑定同一个端口。
其中`setsockopt`函数的参数含义如下：
1. `fd`：socket文件描述符
2. `SOL_SOCKET`：协议层 
3. `SO_REUSEADDR`：端口复用
4. `(const char*)&opt`：端口复用选项
5. `sizeof(opt)`：端口复用选项的大小

#### bind(),listen()

```cpp
    if(bind(fd, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR)
        die("bind() failed");

    if(listen(fd, SOMAXCONN) == SOCKET_ERROR)
        die("listen() failed");
```

绑定相应的端口和监听，在`bind()`这里，我们选择了使用`(sockaddr*)&addr)`强转`sockaddr_in addr{};`，在这里为什么可行呢？

我们上面已经将`sockaddr`和`sockaddr_in`展示了，`sockaddr`是一个通用的套接字地址结构，而`sockaddr_in`是一个具体的IPv4套接字地址结构。

`sockaddr`是一个**16字节**的结构体，由**2字节**的`u_short`无符号短整型和**14字节**的`char`类型组成。

`sockaddr_in`在保留完整的信息的同时(仅使用**8字节**),将少的**8字节**进行填充，在内存布局中兼容`sockaddr`结构体，前面几个字节（`sa_family`）在 `sockaddr_in` 中对应 `sin_family`，后面 `sa_data/sin_port+sin_addr` 对应实际地址信息，所以可以安全的将`sockaddr_in`结构体转换成`sockaddr`结构体。

> 这时候你可能想问，难道剩下的需要填充的那8个字节是无用的吗？为什么要多这8个字节？

> 只需要记住系统根据 `sa_family/sin6_family` 判断协议,内核根据这个**字段**解析剩余内存，所以当`sin_family`为AF_INET时，内核就只解析前8个字节，后面的8个字节会忽略掉。

```cpp
struct sockaddr_in6 { 
    u_short       sin6_family;   // 2字节
    u_short       sin6_port;     // 2字节
    u_long        sin6_flowinfo; // 4字节
    struct in6_addr sin6_addr;   // 16字节
    u_long        sin6_scope_id; // 4字节
};

struct sockaddr_un { 
    sa_family_t sun_family;       // 2字节
    char        sun_path[108];    // 文件路径
};
```

这些是其他的结构体，这些结构体就明显**大于**16字节了，所以他们就不需要填充，但是你可能又会有新的疑问，通用的结构体填充字节数是16字节，那么这些结构体明显比16字节大，那要怎么**强转**？

首先要理解`强转`这个概念，**强转**本身只是告诉编译器，**把这个指针当作`sockaddr*`来处理**，真正的读取结构体的内存的多少的还是有`bind()`函数来决定，也就是`sizeof(sockaddr_in)`或者`sizeof(sockaddr_in6)`。

`bind()`函数的第三个参数`int namelen`,这个参数就是对应的结构体的大小，即使我们的结构体的内存大于**16字节**，但是`bind()`函数会检查这个参数，并按照你传入的长度读取完整结构体

> 其中`sockaddr`中的`char sa_data[14]`并不会影响读取结构体的长度，这里的`sa_data[14]`可以理解为接口的占位，对于`IPV4,IPV6,UNIX socket`具体协议都会保证与`sa_data[14]`对齐,多出来的字节就是**额外字段**。

`listen()`函数就比较简单了，就两个参数，第一个参数是`socket`，第二个参数是`backlog`，`backlog`表示允许的挂起连接数，如果超过这个数，那么新的连接将被拒绝。

#### msg(),die()

```cpp
static void msg(const char *fmt) {
    fprintf(stderr, "%s\n",fmt);
}

static void die(const char *msg) {
    int err = WSAGetLastError();
    fprintf(stderr, "[%d] %s\n", err, msg);
    WSACleanup();
    exit(1);
}
```

`msg()`函数用于打印错误信息，`die()`函数用于打印错误信息并退出程序。

`WSAGetLastError()`函数用于获取最后一次错误码，`WSACleanup()`函数用于清理Winsock环境。

#### fd_set_nb()

设置非阻塞模式

```cpp
// 设置 socket 为非阻塞
static void fd_set_nb(SOCKET fd){
    u_long mode = 1;
    if (ioctlsocket(fd, FIONBIO, &mode) != 0) {
        die("ioctlsocket FIONBIO failed");
    }
}
```

`ioctlsocket()`函数用于设置socket为非阻塞模式，参数`mode`为1表示非阻塞模式，为0表示阻塞模式。

而对于`FIONBIO`,是一个**命令宏**，告诉`ioctlsocket()`要把套接字改成 **非阻塞模式 (non-blocking)**,除了此命令外还有`FIONREAD`用来获取套接字可读字节数，`FIONWRITE`用来获取套接字可写字节数......

`ioctlsocket()`函数返回值`0`表示成功，否则返回`SOCKET_ERROR`(也就是-1)，错误码可以通过`WSAGetLastError()`获取。

#### Conn()

对于以后我们的连接，我们先创建一个`Conn`结构体，用于保存连接信息。

```cpp
struct Conn {
    SOCKET fd;
    bool want_read = true;
    bool want_write = false;
    bool want_close = false;
    vector<uint8_t> incoming;
    vector<uint8_t> outgoing;
};
```

`Conn`结构体中保存了连接的套接字，以及是否需要读取和写入的数据，以及是否需要关闭连接，以及接收到的数据，以及发送的数据。

`Conn`结构体的`want_read`和`want_write`变量用于表示当前连接是否需要读取和写入数据，`want_close`变量用于表示当前连接是否需要关闭。

`incoming`变量用于保存接收到的数据，`outgoing`变量用于保存发送的数据。

而在创建`vector`中我们选择了`uint8_t`作为数据类型，是因为`uint8_t`是一个**8位无符号整型**(正好**一字节**)，而在网络传输中，一般都是**字节**为单位进行传输，而要是选择了`uint32_t`或者`int`等作为数据类型，首先，因为网络传输都是使用字节传输，**32位整数**也会在传输中拆分为4个字节传输，假如你单独只想存一个`A`(ASCII = 0x41,但你需要存成 0x00000041)这样就会浪费许多的空间，除此之外，我们还没有办法直接使用`winodws`下的`recv()`的功能，同时也会有字节序的问题。

所以`uint8_t`是最小的存储单元，也是最适合的存储单元，适合网络发送的字节流数据，也不会有一些字节序，对齐，内存浪费的问题。

#### buf_append(),buf_consume()

```cpp
static void buf_append(vector<uint8_t> &buf, const uint8_t *data, size_t n){
    buf.insert(buf.end(), data, data + n);
}

static void buf_consume(vector<uint8_t> &buf, size_t n){
    buf.erase(buf.begin(), buf.begin() + n);
}
```

这段代码就比较简单了，就是把数据追加到buf中，或者把buf中的数据消费掉。

当然这其中需要理解的`erase()`也是不难的，`erase()`函数会将指定范围的元素删除，然后将剩余的元素重新排列，也就是将范围后面的数据全面覆盖到前面，同时，`vector`的`size()`减少，但是将数据前移后，`vector`的末尾的内存并不会释放，也就是`capacity()`不变。

#### handle_accept()

```cpp
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
```

在与客户端进行连接的时候，也需要一个结构体来保存连接信息。在这里我们继续使用`sockaddr_in`结构体即可。

使用`accept`函数来接受客户端的连接，并返回一个文件描述符。

而在使用`accept()`中，他的第三个参数也是传入一个**大小**，我们传入的是`sizeof(sockaddr_in)`，好像和`bind()`中的`sizeof(sockaddr_in)`一样,但是作用与`bind()`不同，在`bind()`中的`addrlen`参数是告诉内核，**我要绑定的地址结构有多大**，而在`accept()`中，`addrlen`是双向的，调用前，**告诉内核我的缓冲区能装多少**，调用后，**内核告诉你实际写了多少**

> 注意的是，`bind()`中的`addrlen`参数最好是与`sizeof(sockaddr_in)`一致，这样才能保证socket能正常连接，而`accept()`中的`addrlen`参数可以不一致，但是不能小于`sizeof(sockaddr_in)`，具体可以自己测试一下

之后进行打印连接的IP及端口，这里使用了`nthos`和`ntohl`，这是我们之前说的反向函数，用来转换从网络字节序到主机字节序。

在网络传输中，传入的`IP`是一个**32位的16进制整数**，比如说**192.168.1.100**，会被转换成**0xC0A80164**作为`IP`传入。所以在输出`IP`的时候，我们通过**移位**和**按位或**得到对应的`IP`，比如说`(ip >> 24) & 255`,那么`IP`就变成了`0x000000C0 & 0xFF`,所以就等于`192`,其他同理。

#### try_one_request()

```cpp

const size_t k_max_msg = 32 << 20;
static bool try_one_requests(Conn* conn){
    if(conn->incoming.size() < 4) return false;
    uint32_t len = 0;
    memcpy(&len, conn->incoming.data(), 4);

    if(len > k_max_msg){
        msg("message too long");
        conn->want_close = true;
        return false;
    }

    if(4 + len > conn->incoming.size()) return false;
    const uint8_t* request = &conn->incoming[4];
    printf("client request: len: %u data: %.*s\n", len, (int)len, request);

    buf_append(conn->outgoing, (uint8_t*)&len, 4);
    buf_append(conn->outgoing, request, len);

    buf_consume(conn->incoming, 4 + len);
    return true;
}
```

在本章的设计理念中，发送的消息，前四个字节表示消息的长度，因此，接收消息时，首先读取四个字节，然后根据长度读取消息。


我们通过`memcpy()`将读取到的数据复制到`len`中。`memcpy()`的三个参数分别是：目标地址(`&len`)，源地址(`conn->incoming.data()`)，复制的长度(`4`)。

#### handle_write()

```cpp
static void handle_write(Conn* conn){
    if(conn->outgoing.empty()) return;

    int rv = send(conn->fd, (const char*)conn->outgoing.data(), (int)conn->outgoing.size(), 0);
    if(rv == SOCKET_ERROR){
        int err = WSAGetLastError();
        if(err == WSAEWOULDBLOCK) return;
        msg("send() error");
        conn->want_close = true;
        return;
    }

    buf_consume(conn->outgoing, rv);
    if(conn->outgoing.empty()){
        conn->want_read = true;
        conn->want_write = false;
    }
}
```

这里就只需要说一下，`send()`发送完消息后，会返回**实际发送的字节数**

其他的似乎并不难理解，我们就不再多说

#### handle_read()

```cpp
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
```

在这里，`handle_read()`中我们与`try_one_requests()`结合,首先建立连接，收集消息，当获取到了消息的**前四个字节**(也就是消息的长度)时，再等待剩余的字节，当一条完整的消息收集好后，将消息添加到`conn->outgoing`中，并设置`conn->want_write`为`true`，这样`handle_write()`就会开始处理,并发送这条消息。


#### main()

```cpp
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
```
在本文章中选择了非阻塞的方式来准备接收多个连接的发送和读取，而为了监控多个文件描述符(socket等)的状态，我们要使用`poll()`的系统调用(Windows下为`WSAPoll()`或其他系统调用)。

所以我们就先构造一个`pollfd`结构体的数组，然后调用`poll()`函数，就可以实现对多个文件描述符的监控。

因为我们的连接只会监听一个端口(6379)，所以每次我们的连接都会将这个监听放入`poll_args{}`中，以保证所有连接这个端口的`client`都可以正常连接。

> 需要注意的是，我们建立的所有的连接的状态都是存放到`fd2conn_map`中的，这里的所有的连接状态才是那些连接所正常的状态，而保存到`poll_args{}`中的状态，只是当前那个循环中的状态，当这个循环结束后，`poll_args{}`中的状态就可能不再正常了。

这就是为什么我们每次都要使用`poll_args.clear()`来进行清空，并重新循环`fd2conn_map`从新写入`poll_args{}`中。

```cpp
int poll(struct pollfd *fds, unsigned long nfds, int timeout);
// *fds 是一个数组，里面存放了要监控的文件描述符
// nfds 是要监控的文件描述符的个数
// timeout 是超时时间，单位是毫秒，-1 表示一直等待
//WSAPoll()的参数和这个poll()一样，只是描述不同

struct pollfd {
    int   fd;         // 要监控的文件描述符
    short events;     // 你关心的事件，比如 POLLIN(可读), POLLOUT(可写), POLLHUP(断开连接), POLLERR(错误)
    short revents;    // 内核返回的事件，告诉你哪些事件发生了
};// pollfd 结构体 又叫做 WSAPOLLFD 结构体，两个都是一个东西
```

我们使用`unordered_map`来保存所有连接，关于为什么不和网站一致使用数组保存所有的连接，主要是因为，在`linux`下，`accept`函数返回的`fd`是稠密整数(即从0开始递增)，而在`windows`下，`fd`是稀疏的，所以为了保证安全性，就使用了`unordered_map`来进行保存。


相关的代码：

```cpp
static Conn* handle_accept(SOCKET listen_fd){
    /*
    code...
    */
    SOCKET connfd = accept(listen_fd, (sockaddr*)&client_addr, &addrlen);
    /*
    code ...
    */
    Conn* conn = new Conn();
    conn->fd = connfd;
    conn->want_read = true;
    return conn;
}
```

### end

所以将上述代码整合起来就是完整的服务端代码了

```cpp
#define _WIN32_WINNT 0x0600
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <iostream>
#include <vector>
#include <unordered_map>
//#pragma comment(lib, "ws2_32.lib")

using namespace std;

static void msg(const char *fmt) {
    fprintf(stderr, "%s\n",fmt);
}

static void die(const char *msg) {
    int err = WSAGetLastError();
    fprintf(stderr, "[%d] %s\n", err, msg);
    WSACleanup();
    exit(1);
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
    vector<uint8_t> incoming;
    vector<uint8_t> outgoing;
};

static void buf_append(vector<uint8_t> &buf, const uint8_t *data, size_t n){
    buf.insert(buf.end(), data, data + n);
}

static void buf_consume(vector<uint8_t> &buf, size_t n){
    buf.erase(buf.begin(), buf.begin() + n);
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

static bool try_one_requests(Conn* conn){
    if(conn->incoming.size() < 4) return false;
    uint32_t len = 0;
    memcpy(&len, conn->incoming.data(), 4);

    if(len > k_max_msg){
        msg("message too long");
        conn->want_close = true;
        return false;
    }

    if(4 + len > conn->incoming.size()) return false;
    const uint8_t* request = &conn->incoming[4];
    printf("client request: len: %u data: %.*s\n", len, (int)len, request);

    buf_append(conn->outgoing, (uint8_t*)&len, 4);
    buf_append(conn->outgoing, request, len);

    buf_consume(conn->incoming, 4 + len);
    return true;
}

static void handle_write(Conn* conn){
    if(conn->outgoing.empty()) return;

    int rv = send(conn->fd, (const char*)conn->outgoing.data(), (int)conn->outgoing.size(), 0);
    if(rv == SOCKET_ERROR){
        int err = WSAGetLastError();
        if(err == WSAEWOULDBLOCK) return;
        msg("send() error");
        conn->want_close = true;
        return;
    }

    buf_consume(conn->outgoing, rv);
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

并进行编译

```bash
g++ -o server.exe server.cpp -lws2_32
```

## socket(client)

### start

对于服务端的代码就不再具体讲解了，感兴趣的可以自行查看，并分析代码

具体需要注意的是，内核的发送和接收数据，发送时可能因为发送的数据较大而导致一次的发送无法完整发送全部的数据，需要多次进行发送，读取同理，所以需要构建多次发送和读取的代码。

### end

```cpp
#include <iostream>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <cassert>
#include <vector>
#include <string>
#pragma comment(lib, "ws2_32.lib")


static void msg(const char* msg){
    fprintf(stderr, "%s\n", msg);
}
static void die(const char *msg) {
    int err = WSAGetLastError();
    fprintf(stderr, "[%d] %s\n", err, msg);
    WSACleanup();
    exit(1);
}



static int32_t read_full(int fd, uint8_t* buf, size_t n){
    while(n > 0){
        ssize_t rv = recv(fd,(char*)buf,n,0);
        if(rv < 0){
            std::cerr << "read error" << std::endl;
            return -1;
        }
        assert((size_t)rv <=n);
        n -= (size_t)rv;
        buf += (size_t)rv;
    }
    return 0;
}

static int32_t write_full(int fd, uint8_t* buf, size_t n){ 
    while(n>0){
        ssize_t rv = send(fd,(const char*)buf,n,0);
        if(rv < 0){
            std::cerr << "write error" << std::endl;
            return -1;
        }
        assert((size_t)rv <=n);
        n -= (size_t)rv;
        buf += (size_t)rv;
    }
    return 0;
}

static void buf_append(std::vector<uint8_t> &buf,const uint8_t* data,size_t len){
    buf.insert(buf.end(),data,data+len);
}

const size_t k_max_msg = 32 << 20;


static int32_t send_req(int fd, const uint8_t* text, size_t len){
    if(len > k_max_msg) return -1;
    std::vector<uint8_t> wbuf;
    buf_append(wbuf,(const uint8_t*)&len,4);
    buf_append(wbuf,text,len);

    return write_full(fd,wbuf.data(),wbuf.size());
}

static int32_t read_res(int fd){
    std::vector<uint8_t> rbuf;
    rbuf.resize(4);

    int32_t err = read_full(fd,rbuf.data(),4);
    if(err){
    }

    uint32_t len = 0;
    memcpy(&len,rbuf.data(),4);
    if(len > k_max_msg){
        msg("msg too long");
        return -1;
    }
    rbuf.resize(4+len);
    err = read_full(fd,rbuf.data()+4,len);
    if(err){
        msg("read failed");
        return err;
    }

    printf("len: %u data: %s\n",len, len < 100 ? len : 100,&rbuf[4]);
    return 0;
}

int main() {
    // 初始化Winsock
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2,2), &wsaData) != 0) {
        std::cerr << "WSAStartup failed" << std::endl;
        return 1;
    }

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        die("socket()");
    }

    struct sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(6379);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK); // 127.0.0.1

    std::cout << "Connecting to server..." << std::endl;
    int rv = connect(fd, (const struct sockaddr *)&addr, sizeof(addr));
    if (rv) {
        die("connect");
    }

    std::cout << "Connected to server!" << std::endl;

    std::vector<std::string> query_list = {
        "hello1","hello2","hello3",
        std::string(100,'z'),
        "hello5"
    };

    for(const std::string &s:query_list){

        int32_t err = send_req(fd,(uint8_t *)s.data(),s.size());
        if(err){
            std::cout << "Error: " << err << std::endl;
            break;
        }
    }

    for(size_t i = 0; i < query_list.size();++i){
        int32_t err = read_res(fd);
        if (err)
        {
            std::cout << "Error: " << err << std::endl;
            break;
        }
        
    }
        
    std::cout << "Done!" << std::endl;
    closesocket(fd);
    
    // 清理Winsock
    WSACleanup();
    return 0;
}
```

编译：
```bash
g++ -o client.exe client.cpp -lws2_32
```

## 结语

恭喜你，你已经成功创建了一个简单的非阻塞的TCP客户端程序。


