# Implementing Redis in C++ : B

## 前言

本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

本文章为续<<[Implementing Redis in C++ : A](https://blog.csdn.net/m0_58288142/article/details/150490656?fromshare=blogdetail&sharetype=blogdetail&sharerId=150490656&sharerefer=PC&sharesource=m0_58288142&sharefrom=from_link)>>所以本文章不再完整讲解全部代码，只讲解其不同的地方

## socket(server)

### 主体思路

本文章在延续上文的非阻塞网络连接的代码上，修改为键值对存储，并使用socket进行通信。

在上文中，我们传输的数据的格式为(多条消息)：

```
+-----+------+-----+------+-----+-----+------+
| len | str1 | len | str2 | ... | len | strn |
+-----+------+-----+------+-----+-----+------+
```

在此基础上，我们修改了数据的格式为(单条消息)：

```
+-----+------+-----+------+-----+------+-----+-----+------+
| len | nstr | len | str1 | len | str2 | ... | len | strn |
+-----+------+-----+------+-----+------+-----+-----+------+
```

其中第一个`len`字段标识整个这单独一条消息的长度，第二个字段`nstr`标识这条消息的元素个数，第三个字段标识这条消息的第一个元素长度，第四个字段标识这条消息的第一个元素内容，以此类推。

其中我们打算使用的命令是`get`，`set`和`del`三个命令，其中`get`命令用于获取一个键所对应的值，`set`命令用于设置一个键所对应的值，`del`命令用于删除一个键所对应的值。

完整`client`端命令示例：

```bash
./client get key
./client set key value
./client del key
```

所以在我们的`server`端，我们需要额外的实现**键值对的存储**，**client端命令的解析**，以及**命令的响应**。

简单的思路:

**键值对的存储**：我们可以使用一个`map`来存储键值对，键为`string`，值为`string`，用`find`函数来查找键值对，用`swap`来设置键值对，用`erase`来删除键值对。

**client端命令的解析**：获取第一个`len`和`nstr`,之后解析剩下的消息。

### read_u32()
```cpp
const size_t k_max_args = 200 * 1000;

static bool read_u32(const uint8_t* &cur, const uint8_t* end, uint32_t &out){
    if(cur + 4 > end){ // not enough data for the first length
        return false;
    }
    memcpy(&out, cur , 4);
    cur += 4;
    return true;
}
```

首先是`read_u32()`这个函数，这个函数的主要功能是，当长度足够的时候(cur + 4 < end)，获取数据并将数据复制到指定的地址中，同时将数据的指针后移4个字节。

```
+-----+------+-----+------+-----+------+-----+-----+------+
| len | nstr | len | str1 | len | str2 | ... | len | strn |
+-----+------+-----+------+-----+------+-----+-----+------+
| 4   | 4    | 4   | str1 | 4   | str2 | ... | 4   | strn |
```

### read_str()

```cpp
static bool read_str(const uint8_t* &cur, const uint8_t* end, size_t n,std::string &out){
    if(cur + n > end) return false; // not enough data for the string
    out.assign(cur,cur + n);
    cur += n;
    return true;
}
```

这里的功能也并不难懂，需要注意的一点就是，`string`的`assign()`函数，在复制新内容到新空间时，会先清空就内容，再复制新内容。

### parse_req()

```cpp
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
```

```
+-----+------+-----+------+-----+------+-----+-----+------+
| len | nstr | len | str1 | len | str2 | ... | len | strn |
+-----+------+-----+------+-----+------+-----+-----+------+
| 4   | 4    | 4   | str1 | 4   | str2 | ... | 4   | strn |
```

先说这里的形参，`const uint8_t* data`，是已经处理好**前四个字节**的数据，也就是现在`data`的数据是从`nstr`开始了，而`std::vector<std::string> &out`中要存放的数据，是我们经过处理后获取到的完整数据。

比如(client -> server)：
```bash
./client set key value
```

那么最后，我们`out`中解析完的数据就是，

```python
out[0] = "set"
out[1] = "key"
out[2] = "value"
```

在上面的代码中，我们还看到了这段代码

```cpp
out.push_back(std::string());
if(!read_str(data,end,len,out.back())) return -1;
```

这段代码也是很有意思的，通过提前`push_back()`一个空的`string`，然后调用`read_str()`，将数据读入到这个空的`string`中，这样，`out`中，`out[i]`就是我们输入的参数了。

### do_request()

```cpp
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

static std::map<std::string,std::string> g_data;

static void do_request(std::vector<std::string> &cmd,Response &out){
    if(cmd.size() == 2 && cmd[0] == "get"){
        auto it = g_data.find(cmd[1]);
        if(it == g_data.end()){
            out.status = RES_NX;
            return ;
        }
        const std::string &val = it->second;
        out.data.assign(val.begin(),val.end());
        out.status = RES_OK;
    }else if(cmd.size() == 3 && cmd[0] == "set"){
        g_data[cmd[1]].swap(cmd[2]);
        out.status = RES_OK;
    }else if(cmd.size() == 2 && cmd[0] == "del"){
        g_data.erase(cmd[1]);
        out.status = RES_OK;
    }else{
        out.status = RES_ERR;

    }
}
```

这里具体的代码就是我们的**键值对**的处理的实现了

在这里的`std::vector<std::string> cmd`就是我们上面讲的`std::vector<std::string> out`，而在此处的`Response &out`就仅是一个准备处理响应的引用

### try_one_request()

```cpp
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
    printf("client request: len: %u data: %.*x\n", len, (int)len, request);

    std::vector<std::string> cmd;
    if(parse_req(request, len, cmd)<0){
        msg("parse_req failed");
        conn->want_close = true;
        return false;
    }

    Response resp;
    do_request(cmd,resp);
    make_response(resp,conn->outgoing);
    buf_consume(conn->incoming,4+len);

    return true;
}
```

这里的代码也就不过多讲解了，就是将前面的将的函数结合起来，先解析请求，然后执行请求，将响应数据放到缓冲区中，删除输入缓冲区中的数据，最后，等下一次循环的时候，将数据发送出去。

## socket(code)

```cpp
#define _WIN32_WINNT 0x0600
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <iostream>
#include <map>
#include <string>
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

static std::map<std::string,std::string> g_data;

static void do_request(std::vector<std::string> &cmd,Response &out){
    if(cmd.size() == 2 && cmd[0] == "get"){
        auto it = g_data.find(cmd[1]);
        if(it == g_data.end()){
            out.status = RES_NX;
            return ;
        }
        const std::string &val = it->second;
        out.data.assign(val.begin(),val.end());
        out.status = RES_OK;
    }else if(cmd.size() == 3 && cmd[0] == "set"){
        g_data[cmd[1]].swap(cmd[2]);
        out.status = RES_OK;
    }else if(cmd.size() == 2 && cmd[0] == "del"){
        g_data.erase(cmd[1]);
        out.status = RES_OK;
    }else{
        out.status = RES_ERR;

    }
}

static void make_response(const Response &resp, std::vector<uint8_t> &out){
    uint32_t resp_len = 4 + (uint32_t)resp.data.size();
    buf_append(out,(const uint8_t*)&resp_len,4);
    buf_append(out,(const uint8_t*)&resp.status,4);
    buf_append(out,resp.data.data(),resp.data.size());
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
    printf("client request: len: %u data: %.*x\n", len, (int)len, request);

    std::vector<std::string> cmd;
    if(parse_req(request, len, cmd)<0){
        msg("parse_req failed");
        conn->want_close = true;
        return false;
    }

    Response resp;
    do_request(cmd,resp);
    make_response(resp,conn->outgoing);
    buf_consume(conn->incoming,4+len);

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

## optimize(server)

### start

在原网站中，作者也提到了可以优化的部分(server)

> 然而，仍有改进空间：响应数据被复制了两次，首先从键值复制到 Response::data，然后从 Response::data 复制到 Conn::outgoing。 练习：优化代码，使响应数据直接发送到 Conn::outgoing。

这次我们的优化，不仅是减少数据复制的次数，同时还要优化数据存储的方法

### 简单的思路

首先是作者提到的：将数据存储在 **Conn::outgoing** 中，而不是在 **Response::data** 中，所以后续我们可以考虑，直接把`Response`直接砍掉。

除此之外，我们可以构建一个**环形缓冲区**，这样在我们在处理数据的时候，就可以实现**减少拷贝数据**，**O(1)的操作时间**等多优化。

### Ring_buf{}

```cpp
struct Ring_buf{
    std::vector<uint8_t> buf;
    size_t head;
    size_t tail;
    size_t cap;
    size_t status;

    Ring_buf():buf(256),head(0),tail(0),cap(256){
    }

    size_t size() const{ // 计算使用的容量
        return (cap + tail - head) % cap;

    }
    size_t free_cap() const{ // 剩余容量，空一个位
        return cap - size() -1 ;
    }

    bool full() const{ // 满，空一个位
        return (tail + 1) % cap == head;
    }

    bool empty() const{
        return head == tail;
    }
};
```

我们使用结构体来实现**环形缓冲区**，因为这个缓冲区是为了替代简单的`vector`的，所以我也将`status`放到了这里面，大家也可以把`status`放到其他的地方，方便**解耦**。


```cpp
Index:   0   1   2   3   4   5   6   7
Buffer: [ ] [ ] [x] [x] [x] [ ] [ ] [ ]
                 H           T
```

`size()`的计算也并不麻烦，在上面的示例中，**head = 2**，**tail = 5**，所以`size()`为`(8+5-2)%8 = 3`。因为我们要避免`head=tail`时出现的两种情况进行区分，到底是**满**还是**空**，所以我们空一个位置来区分。

> 这个空的位置也就是没有移动前`tail`所指向的位置

> Q: 为什么tail一定指向空位置？
> A: 假如我们填入三个内容，那内容是从**0**开始，增加到**2**的，而我们`tail`直接使用`0+3=3`，所以`tail`一定指向空位置

所以我们实际上最大的使用的空间是7个(按我们的举例)，`(tail+1)%cap`可以计算出已经使用完等。

### buf_append()

我们准备修改`incoming`和`outgoing`两个缓冲区，所以我们的函数`buf_append()`也应该进行修改。

```cpp
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
```

在数据进行拷贝前，我们会判断数据长度`n`和当前`tail`索引后方还剩多少空间可以使用，为什么会选择一个**小**的呢？

首先，在代码的开始，我们使用了 **n > buf.free_cap()**来保证，缓冲区有足够多的空间可以让我们存储数据。

那么现在假设：`n` < `buf.cap - buf.tail`
假设： 2 < 3
```cpp
Index:   0   1   2   3   4   5   6   7
Buffer: [ ] [ ] [x] [x] [x] [ ] [ ] [ ]
                 H           T
```

那么数据就直接会追加，而第二次的`memcpy`(保证分开的两端可以正常拷贝)也就不会在执行(n-min =0)。

相反：`n` > `buf.cap - buf.tail`
假设： 4 > 3

那么数据会先从缓冲区`tail`拷贝到缓冲区末尾，然后再从缓冲区开头将剩余的(n-min = n-(buf.cap - buf.tail))拷贝完。

那你可能会问，那万一`tail`在`head`前面，然后，复制足够的长度，不就把`head`覆盖了吗？

不不不，当然不会，我们一开始就说了，我们先使用了**n > buf.free_cap()**来保证，缓冲区有足够多的空间可以让我们存储数据，所以在这个时候，`n`一定会小于`buf.cap - buf.tail`，绝不会出现覆盖的情况。

> 注意：第二个`memcpy`只会在 `n` > `buf.cap - buf.tail`的时候生效，其他的时候只会直接在`tail`后面追加

最后通过**buf.tail = (buf.tail + n) % buf.cap;**移动尾指针。

### buf_consume()

```cpp
static void buf_consume(Ring_buf &buf, size_t n){
    buf.head = (buf.head + n) % buf.cap;
}
```

我们使用了**环形缓冲区**,所以我们没有必要去清空我们的`vector`，我们可以直接设置头指针的移动来实现清除的效果。

要是我们专门的去把我们的容器去置空的话，就比较浪费时间了。

### make_response()

```cpp
static void make_response(const string &resp, Ring_buf &out){
    uint32_t resp_len = 4 + (uint32_t)resp.size();
    buf_append(out,(const uint8_t*)&resp_len,4);
    buf_append(out,(const uint8_t*)&out.status,4);
    buf_append(out,(const uint8_t*)resp.data(),resp.size());
}
```

为了将`Response`这个结构体砍掉，我将`Response`这个结构体中的`status`数据放到了`Ring_buf`中，并将`Response`替换成了`string`。

### try_one_requests()

```cpp
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

    printf("client request: len: %u \n", len, (int)len);
    hex_dump(request.data(),len);

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
```

`try_one_requests()`这个函数的功能主要是读取并解析数据，其中`parse_req()`等函数并没有改变，我们也就不再讲解这些不变的内容了了。

```
+-----+------+-----+------+-----+------+-----+-----+------+
| len | nstr | len | str1 | len | str2 | ... | len | strn |
+-----+------+-----+------+-----+------+-----+-----+------+
| 4   | 4    | 4   | str1 | 4   | str2 | ... | 4   | strn |
```

我们正在使用**环形缓冲区**,所以当我们读取消息的时候,前面的四个字节的`len`也是有可能会被分隔开，所以为了保证能够正确的读取数据(获取消息的总长度，读取消息的第一个`len`)，我们也使用两个`memcpy`来获取数据，当然第二个`memcpy`也是只有当(cap-head < 4)的时候才会使用。

使用`min`来获取(4 或 cap-head)最小的值，其思想和我们在`buf_append`中的取最小值的思想一样，不过是改成了从**写**变成**读**，能完整的读取`len`就完整的读出来，读不出来就读一部分，然后从开头开始读，将剩余的部分读完。

在这中我们使用了中间量`uint8_t hdr[4]`来保存长度，然后拷贝到`len`中，直接使用`uint32_t len`的话，无法正常使用第二个`memcpy`函数。

```cpp
    std::vector<uint8_t> request(len);
    size_t start = (conn->incoming.head + 4)%conn->incoming.cap;
    size_t first = std::min<size_t>(len,conn->incoming.cap - start);
    memcpy(request.data(),&conn->incoming.buf[start],first);
    if(first < len){
        memcpy(request.data() + first,&conn->incoming.buf[0],len - first);
    }
```

这里的拷贝逻辑也同理，不再讲述。

以及最后我调整了响应的返回和制作逻辑

```cpp
    // Response resp;
    std::string s = do_request(cmd,conn->outgoing);
    if(!s.empty()){
        make_response(s,conn->outgoing);
    }else{
        std::string s = "Done!";
        make_response(s,conn->outgoing);
    }
```

### do_request()

```cpp
static string do_request(std::vector<std::string> &cmd,Ring_buf &buf){
    if(cmd.size() == 2 && cmd[0] == "get"){
        auto it = g_data.find(cmd[1]);
        if(it == g_data.end()){
            buf.status = RES_NX;
            return "0";
        }
        const std::string &val = it->second;
        // out.data.assign(val.begin(),val.end());
        // make_response(val,buf);
        buf.status = RES_OK;
        return val;
    }else if(cmd.size() == 3 && cmd[0] == "set"){
        g_data[cmd[1]].swap(cmd[2]);
        buf.status = RES_OK;
    }else if(cmd.size() == 2 && cmd[0] == "del"){
        g_data.erase(cmd[1]);
        buf.status = RES_OK;
        
    }else{
        buf.status = RES_ERR;
        
    }
    return "0";
};
```

这里的代码似乎也不用多说了，只改了一小部分。

### handle_write()

```cpp
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
```

这里我将代码稍微拆了一下，这里只需要注意一下，因为**环形缓冲区** 的原因，我们发送的消息也可能被截断，所以我们也要取最小值，取最小值的思路同上文所述，只是，这里只使用一遍`send`函数，等下一次循环才能将被截断的消息发送出去。

如果同时使用多个`send`函数，就可能会出现**乱序**的问题，可以自行了解。

### end

```cpp
#define _WIN32_WINNT 0x0600
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <iostream>
#include <map>
#include <string>
#include <vector>
#include <unordered_map>
#pragma comment(lib, "ws2_32.lib")

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

static std::map<std::string,std::string> g_data;

static string do_request(std::vector<std::string> &cmd,Ring_buf &buf){
    if(cmd.size() == 2 && cmd[0] == "get"){
        auto it = g_data.find(cmd[1]);
        if(it == g_data.end()){
            buf.status = RES_NX;
            return "0";
        }
        const std::string &val = it->second;
        // out.data.assign(val.begin(),val.end());
        // make_response(val,buf);
        buf.status = RES_OK;
        return val;
    }else if(cmd.size() == 3 && cmd[0] == "set"){
        g_data[cmd[1]].swap(cmd[2]);
        buf.status = RES_OK;
    }else if(cmd.size() == 2 && cmd[0] == "del"){
        g_data.erase(cmd[1]);
        buf.status = RES_OK;
        
    }else{
        buf.status = RES_ERR;
        
    }
    return "0";
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

    printf("client request: len: %u \n", len, (int)len);
    hex_dump(request.data(),len);

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
### epilogue

至此，我们的优化已经完成了，当然，现在优化的也并不是极致，过多的优化，还需要自己去更新，本文就优化到这里了。

## socket(client)

### start

同上文一样，我们不再讲解`client`端的代码，具体代码可以读者自行查看

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


const size_t k_max_msg = 4096;


static int32_t send_req(int fd, const std::vector<std::string> &cmd){
    uint32_t len = 4;
    for(const std::string &s:cmd){
        len += 4+s.size();
    }
    if(len > k_max_msg) return -1;
    char wbuf[4+k_max_msg];
    memcpy(wbuf,&len,4);
    uint32_t n = cmd.size();
    memcpy(&wbuf[4],&n,4);

    size_t cur = 8;
    for(const std::string &s:cmd){
        uint32_t p = (uint32_t)s.size();
        memcpy(&wbuf[cur],&p,4);
        memcpy(&wbuf[cur+4],s.data(),s.size());
        cur += 4+p;
    }

    return write_full(fd,(uint8_t *)wbuf,4+len);
}

static int32_t read_res(int fd){
    char rbuf[4+k_max_msg];

    int32_t err = read_full(fd,(uint8_t *)rbuf,4);
    if(err){
    }

    uint32_t len = 0;
    memcpy(&len,rbuf,4);
    if(len > k_max_msg){
        msg("msg too long");
        return -1;
    }
    
    err = read_full(fd,(uint8_t *)&rbuf[4],len);
    if(err){
        msg("read failed");
        return err;
    }

    uint32_t rescode = 0;
    if(len < 4){
        msg("bad response");
        return -1;
    }
    memcpy(&rescode,&rbuf[4],4);

    printf("server says:[%u] %.*s\n",rescode,len-4,&rbuf[8]);
    return 0;
}

int main(int argc, char **argv) {
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

    std::vector<std::string> cmd;
    for(int i = 1; i<argc ; ++i){
        cmd.push_back(argv[i]);
    }
    int32_t err = send_req(fd, cmd);
    if (err) {
        die("send_request");
    }

    err = read_res(fd);
    if (err) {
        die("read_res");
    }

    std::cout << "Done!" << std::endl;
    closesocket(fd);
    
    // 清理Winsock
    WSACleanup();
    return 0;
}
```




