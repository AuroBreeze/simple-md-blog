# Implementing Redis in C++ : D

## 前言

本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

本文章为续<<[Implementing Redis in C++ : C](https://blog.csdn.net/m0_58288142/article/details/150582066?fromshare=blogdetail&sharetype=blogdetail&sharerId=150582066&sharerefer=PC&sharesource=m0_58288142&sharefrom=from_link)>>所以本文章不再完整讲解全部代码，只讲解其不同的地方

## 完成优化后的代码

- **TLV (Type-Length-Value) 协议格式**: 实现了完整的二进制TLV响应格式
- **多种数据类型支持**:
  - `TAG_NIL` (0): nil值
  - `TAG_ERR` (1): 错误代码和消息
  - `TAG_STR` (2): 字符串类型
  - `TAG_INT` (3): 64位整数
  - `TAG_DBL` (4): 双精度浮点数
  - `TAG_ARR` (5): 数组类型
- **优化的响应序列化**: 使用TLV格式替代简单的状态码+数据格式
- **二进制协议兼容性**: 支持更复杂的数据结构和类型系统
- **扩展性**: 易于添加新的数据类型和协议功能

##  TLV (Type-Length-Value) 协议格式

TLV (Type-Length-Value) 是一种数据编码格式，它将数据分为三个部分：**类型、长度和值**。

在之前的文章中，我们只使用了简单的**长度和消息格式**，为了使我们的网络传输更加高效，我们将使用`TLV`数据编码方式来**序列化**数据，并进行传输和解析。

我们设定如下的数据传输格式：

```cpp
  nil       int64           str                   array      int64 and so on
┌─────┐   ┌─────┬─────┐   ┌─────┬─────┬─────┐   ┌─────┬─────┬─────┬─────┬─────┐
│ tag │   │ tag │ int │   │ tag │ len │ ... │   │ tag │ len │ tag │ int │ ... │
└─────┘   └─────┴─────┘   └─────┴─────┴─────┘   └─────┴─────┴─────┴─────┴─────┘
   1B        1B    8B        1B    4B   ...        1B    4B   ...
```

为什么要使用`TLV`？

我们可以看到我们上面定义的数据传输格式，首先通过`tag`来判断数据类型，然后对对应的数据进行解析(**自描述性**，**数据验证**)，保证数据传输的类型安全，同时还使用`len`，来校验数据传输的长度(**支持错误检测**，**数据验证**)，防止数据传输过程中出现数据截断。

简单来说：`TLV`格式通过提供灵活、高效、易扩展和易解析的数据编码方式，在网络协议、数据传输、存储和通信中展现了巨大的优势。它使得数据交换更加标准化和高效，减少了复杂度并提高了协议的可扩展性。

我们这次要处理的数据结构是：

```c++
┌─────┐┌─────┐┌─────┬─────┐┌─────┬─────┬─────┐┌─────┬─────┬─────┐
│ len ││ tag ││ tag │ int ││ tag │ len │ ... ││ tag │ len │ ... │
└─────┘└─────┘└─────┴─────┘└─────┴─────┴─────┘└─────┴─────┴─────┘
  4B    1B    1B    4B    1B    1B    4B    ...  1B    1B    ...
  
len: 整条消息的长度
tag: 标记符，用于区分消息类型
```

## 主体思路

在先前我们已经实现了一个简单的自定义的网络传输格式，如下图所示，但是原文作者并没有修改`client`端发送操作指令的代码，所以我们的修改，就主要聚焦于**server端发送消息的代码**和**client端接收消息的代码**，并在这些代码中使用我们的**自定义TLV网络传输格式**。

> **server端接收消息的代码**和**client端发送消息的代码**就不需要再动了，这些都是与操作指令有关的，并不与数据传输有关。

```cpp
 +-----+------+-----+------+-----+------+-----+-----+------+
 | len | nstr | len | str1 | len | str2 | ... | len | strn |
 +-----+------+-----+------+-----+------+-----+-----+------+
```

同时，因为新增了`key`这个命令，用来查看所有的**键**，所以在`hashtable`新增了`hm_foreach`遍历所有节点的通用的功能。

在原文中`server`端发送数据的处理思路：在`server`在处理最开始的`len`的时候，我们是要**置空**的(置空最前面4字节，后面再填充长度)，我们先将要传输的所有数据都存到我们的缓冲区中，最后计算消息的总长度，使用`memcpy`将长度拷贝到缓冲区最前面4字节，然后发送数据。

### hashtable.cpp  hm_foreach()

```cpp
static bool h_foreach(HTab* htab,bool (*f)(HNode*, void*),void* arg){
    for(size_t i=0; htab->mask !=0 && i<= htab->mask; ++i){
        for(HNode* node=htab->tab[i]; node != nullptr; node= node->next){
            if(!f(node, arg)){
                return false;
            }
        }
    }
    return true;
}

void hm_foreach(HMap* hmap, bool (*f)(HNode*, void*),void* arg){
    h_foreach(&hmap->newer, f, arg) && h_foreach(&hmap->older, f, arg);
}
```

在这里又使用了`bool (*f)(HNode*, void*)`这个函数指针，这个函数指针的返回值是一个布尔值，形参分别是`HNode*`和`void*`，在`h_foreach`函数中，用他来控制循环是否进行。

这段代码似乎并不难懂，`htab->mask`是**桶**的数量，然后遍历每个桶中的数据，将所有的节点遍历一遍，并由后来传入的函数指针`f`来处理是否继续进行。

在`hm_foreach`中则将两表整合一起来，将两个表都遍历一遍，其中使用了`&&`运算符，这样只有当第一个表返回`true`时，第二个表才会被遍历，否则就不遍历第二个表。

读者可自行在`hashtable.h`中新增`hm_foreach`函数，实现两个表同时遍历，下面将不再完整放置整个`hashtable.cpp`和`hashtable.h`文件。

## server.cpp

### server.cpp cb_keys(), do_keys()

```cpp
static bool cb_keys(HNode* node, void* arg){
    Ring_buf &buf = *(Ring_buf*)arg;
    const std::string& key = container_of(node, Entry, node)->key;
    //container_of 根据内容反推整体
    out_str(buf, key.data(), key.size());
    return true;
}

static void do_keys(std::vector<string>&, Ring_buf &buf){
    out_arr(buf, (uint32_t)hm_size(&g_data.db));
    hm_foreach(&g_data.db, &cb_keys, (void*)&buf);
}
```
> `out_str()`就是将字符串写入缓冲区(写入`tag`, `len`和`value`)，`out_arr()`就是将数组写入缓冲区(只写入`tag`和`len`)，这个我们后面详细介绍。

将这里的`cb_keys()`和`do_keys()`及上面我们刚说的`hm_foreach()`放到一起，在这里，`cb_keys()`是回调函数，可能单独这样放上代码不太好理解，我将回调函数和实参一起放到`h_foreach`中判断`return`的地方

```cpp

bool b = cb_keys(node, &buf);
// Ring_buf &buf = *(Ring_buf*)buf;
// const std::string& key = container_of(node, Entry, node)->key;
// out_str(buf, key.data(), key.size());
// return true;
if(!b){
    return false;
}
```

就相当于遍历所有节点，将所有节点中的`string Entry::key`都写入了缓冲区。

当然，如果有其他的需求，也可以写其他的回调函数，并放入`hm_foreach`中。

### buf_append()

```cpp
static void buf_append(Ring_buf &buf, const uint8_t *data, size_t n){
    if (n > buf.free_cap()) return;
    size_t min = std::min(n,buf.cap - buf.tail);
    memcpy(&buf.buf[buf.tail], data, min);
    memcpy(&buf.buf[0], data + min, n - min);
    buf.tail = (buf.tail + n) % buf.cap;
}

static void buf_append_u8(Ring_buf& buf, uint8_t data){
    buf_append(buf, (const uint8_t*)&data, sizeof(data));
}

static void buf_append_u32(Ring_buf& buf, uint32_t data){
    buf_append(buf, (const uint8_t*)&data, 4);
}

static void buf_append_i64(Ring_buf& buf, int64_t data){
    buf_append(buf, (const uint8_t*)&data, 8);
}

static void buf_append_dbl(Ring_buf& buf, double data){
    buf_append(buf, (const uint8_t*)&data, 8);
}
```

新增的这些`buf_append()`不过是具体化了一下每个函数的分配的空间。

`u8`是分配一个字节，多用来分配我们自定义的`tag`(1字节)，`u32`分配四字节，用来分配消息的长度，`i64`用来传输64位整数，`dbl`用来传输64位浮点数。

### TAG, ERR

```cpp
enum {
    ERR_UNKNOWN = 1, // unknown command
    ERR_TOO_BIG = 2  // response too big
};

enum{
    TAG_NIL = 0,    // nil
    TAG_ERR = 1,    // error code + msg
    TAG_STR = 2,    // string
    TAG_INT = 3,    // int64
    TAG_DBL = 4,    // double
    TAG_ARR = 5,    // array
};
```

### out()

```cpp
static void out_nil(Ring_buf& buf){
    buf_append_u8(buf, TAG_NIL);
}

static void out_str(Ring_buf& buf, const char* s, size_t size){
    buf_append_u8(buf, TAG_STR);
    buf_append_u32(buf, (uint32_t)size);
    buf_append(buf, (const uint8_t*)s, size);
}

static void out_int(Ring_buf& buf, int64_t val){
    buf_append_u8(buf, TAG_INT);
    buf_append_i64(buf, val);
}

static void out_dbl(Ring_buf& buf, double val){
    buf_append_u8(buf, TAG_DBL);
    buf_append_dbl(buf, val);
}

static void out_err(Ring_buf& buf, uint32_t code, const std::string &msg){
    buf_append_u8(buf, TAG_ERR);
    buf_append_u32(buf, code);
    buf_append_u32(buf, (uint32_t)msg.size());
    buf_append(buf, (const uint8_t*)msg.data(), msg.size());
}

static void out_arr(Ring_buf& buf, uint32_t n){
    buf_append_u8(buf, TAG_ARR);
    buf_append_u32(buf, n);
}
```

这些将数据写到缓冲区的功能，就得看我们是如何**自定义`TLV`传输**的了，按照我们的开头的定义：

```cpp
  nil       int64           str                   array      int64 and so on
┌─────┐   ┌─────┬─────┐   ┌─────┬─────┬─────┐   ┌─────┬─────┬─────┬─────┬─────┐
│ tag │   │ tag │ int │   │ tag │ len │ ... │   │ tag │ len │ tag │ int │ ... │
└─────┘   └─────┴─────┘   └─────┴─────┴─────┘   └─────┴─────┴─────┴─────┴─────┘
   1B        1B    8B        1B    4B   ...        1B    4B   1B    8B    ...
```

我们要传输的数据中`nil`, `int64`, `double64`都是不需要传输长度的(当然解析的时候也会麻烦一点)，而`string`和`array`需要传输长度。

所以在写需要传输长度的函数的时候，都会多一个`buf_append_u32`来添加长度，作为`TLV`中的`L`字段。

当然特殊一点的`arr`就只分配了`tag`和`len`，因为具体的需要我们传输的数据都是后面添加的，所以，如果我们要使用`out_arr`，就必须知道我们要**添加的内容有多大**，也就是在`do_keys()`中，我们使用`(uint32_t)hm_size(&g_data.db)`获取到了所有存在哈希表中数据的大小，并使用了`cb_keys`将数据添加到`out_arr`中。


### response()

```cpp
static void response_begin(Ring_buf& buf, size_t *header){
    *header = buf.size(); // message header position
    buf_append_u32(buf, 0);
}

static size_t response_size(Ring_buf& buf, size_t header){
    return buf.size() - header - 4;
}

static void response_end(Ring_buf& buf, size_t header){
    size_t msg_size = response_size(buf, header);
    if(msg_size > k_max_msg){
        buf.tail = (buf.tail + buf.cap - msg_size) % buf.cap ;
        out_err(buf, ERR_TOO_BIG, "response too big");
        msg_size = response_size(buf, header);
    }
    uint32_t len = (uint32_t)msg_size;
    // buf_append(buf, (const uint8_t*)&len, sizeof(len));
    memcpy(&buf.buf[(buf.head+header) % buf.cap], &len, 4);
}
```

这是我们处理待发送数据的函数，`response_begin()`的主要功能就是，获取还没发送消息前，缓冲区的数据有多大，并向缓冲区添加四个空字节，作为消息长度的占位符，后面数据都添加完后，会使用`response_end()`来计算待发送消息的长度，检查是否超过最大长度，并替换掉占位符。

因为我们是维护的指针，所以我们在调整缓冲区的时候，只需要调整`tail`指针就行，这样`out_err`的值就会覆盖掉我们刚才写入的内容。

还有一点需要注意的是，我们使用的是`size_t header`，其中储存着我们未进行操作前缓冲区的数据长度，所以我们真正前面置空的4个字节，不一定是`buf->head`指针指向的地方，所以当我们要将长度使用`memcpy`拷贝进去的时候，要拷贝到`buf.buf`中 **((buf.head+header)%buf.cap)** 指向的地方。

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

    printf("client request: len: %u \n", len);
    // hex_dump(request.data(),len);

    std::vector<std::string> cmd;
    if(parse_req(request.data(), len, cmd)<0){
        msg("parse_req failed");
        conn->want_close = true;
        return false;
    }




    // Response
    size_t header_pos = 0;
    response_begin(conn->outgoing, &header_pos);
    do_request(cmd, conn->outgoing);
    response_end(conn->outgoing, header_pos);

    // make_response(resp,conn->outgoing);
    buf_consume(conn->incoming,4+len);

    return true;
}
```

`try_one_requests()`函数的功能我们先前的文章已经讲过一些了，这次主要变动的地方就是**响应**的生成，关于响应生成的三个函数我们上面也讲过了，我们也就不再多说了。

## end

通过本文的学习，我们成功实现了Redis的TLV (Type-Length-Value) 协议格式，这是一个重要的里程碑。TLV格式为我们的Redis实现带来了诸多优势：

### 主要成果总结

1. **完整的二进制协议支持**：实现了多种数据类型的TLV编码，包括nil、错误、字符串、整数、浮点数和数组类型
2. **类型安全的数据传输**：通过tag字段确保数据类型的正确解析和验证
3. **高效的序列化机制**：使用环形缓冲区优化了数据的序列化和反序列化过程
4. **扩展性架构**：易于添加新的数据类型和协议功能
5. **新增keys命令**：实现了哈希表的遍历功能，支持查看所有键

### 技术亮点

- **自描述性协议**：TLV格式使得数据具有自描述性，接收方可以根据tag和length字段正确解析数据
- **错误检测机制**：length字段提供了数据完整性校验，防止数据截断和损坏
- **内存效率优化**：环形缓冲区的使用减少了内存分配和拷贝操作
- **灵活的扩展机制**：枚举类型的tag设计使得添加新数据类型变得简单

### 未来展望

虽然我们已经实现了基础的TLV协议，但仍有许多可以改进和扩展的方向：

1. **更多数据类型支持**：可以添加哈希表、集合、有序集合等Redis核心数据类型
2. **客户端TLV解析**：目前只实现了服务端的TLV编码，客户端还需要相应的解析逻辑
3. **性能优化**：可以进一步优化缓冲区的使用和内存管理
4. **协议兼容性**：考虑与Redis官方协议的兼容性，或者实现协议转换层
5. **安全性增强**：添加认证、加密等安全特性

### 结语

TLV协议格式的实现标志着我们的Redis项目进入了一个新的阶段。从简单的文本协议到二进制协议，我们不仅提升了性能，更重要的是建立了一个可扩展、类型安全的通信基础。这个基础将支持我们未来实现更多复杂的Redis功能和优化。

## code

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

    Ring_buf():buf(1024),head(0),tail(0),cap(1024){
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

    bool clear(){
        head = tail;
        return true;
    }
};


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

const size_t k_max_msg = 4096;

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

static void buf_append(Ring_buf &buf, const uint8_t *data, size_t n){
    if (n > buf.free_cap()) return;
    size_t min = std::min(n,buf.cap - buf.tail);
    memcpy(&buf.buf[buf.tail], data, min);
    memcpy(&buf.buf[0], data + min, n - min);
    buf.tail = (buf.tail + n) % buf.cap;
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

//不再使用
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

enum {
    ERR_UNKNOWN = 1, // unknown command
    ERR_TOO_BIG = 2  // response too big
};

enum{
    TAG_NIL = 0,    // nil
    TAG_ERR = 1,    // error code + msg
    TAG_STR = 2,    // string
    TAG_INT = 3,    // int64
    TAG_DBL = 4,    // double
    TAG_ARR = 5,    // array
};
//  nil       int64           str                   array
// ┌─────┐   ┌─────┬─────┐   ┌─────┬─────┬─────┐   ┌─────┬─────┬─────┐
// │ tag │   │ tag │ int │   │ tag │ len │ ... │   │ tag │ len │ ... │
// └─────┘   └─────┴─────┘   └─────┴─────┴─────┘   └─────┴─────┴─────┘
//    1B        1B    8B        1B    4B   ...        1B    4B   ...

static void buf_append_u8(Ring_buf& buf, uint8_t data){
    buf_append(buf, (const uint8_t*)&data, sizeof(data));
}

static void buf_append_u32(Ring_buf& buf, uint32_t data){
    buf_append(buf, (const uint8_t*)&data, 4);
}

static void buf_append_i64(Ring_buf& buf, int64_t data){
    buf_append(buf, (const uint8_t*)&data, 8);
}

static void buf_append_dbl(Ring_buf& buf, double data){
    buf_append(buf, (const uint8_t*)&data, 8);
}


static void out_nil(Ring_buf& buf){
    buf_append_u8(buf, TAG_NIL);
}

static void out_str(Ring_buf& buf, const char* s, size_t size){
    buf_append_u8(buf, TAG_STR);
    buf_append_u32(buf, (uint32_t)size);
    buf_append(buf, (const uint8_t*)s, size);
}

static void out_int(Ring_buf& buf, int64_t val){
    buf_append_u8(buf, TAG_INT);
    buf_append_i64(buf, val);
}

static void out_dbl(Ring_buf& buf, double val){
    buf_append_u8(buf, TAG_DBL);
    buf_append_dbl(buf, val);
}

static void out_err(Ring_buf& buf, uint32_t code, const std::string &msg){
    buf_append_u8(buf, TAG_ERR);
    buf_append_u32(buf, code);
    buf_append_u32(buf, (uint32_t)msg.size());
    buf_append(buf, (const uint8_t*)msg.data(), msg.size());
}

static void out_arr(Ring_buf& buf, uint32_t n){
    buf_append_u8(buf, TAG_ARR);
    buf_append_u32(buf, n);
}

enum{
    RES_OK = 0,
    RES_ERR = 1, // error
    RES_NX = 2 , // key not found
};

// +--------+---------+
// | status | data... |
// +--------+---------+


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

static void do_get(std::vector<std::string> &cmd, Ring_buf &buf){
    Entry key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((const uint8_t*) key.key.data(), key.key.size());
    //hashtable lookup
    HNode* node = hm_lookup(&g_data.db,&key.node,&entry_eq);
    if(!node){
        out_nil(buf);
        return;
    }
    const std::string* val = &container_of(node,Entry,node)->val;
    out_str(buf, val->data(), val->size());
}

static void do_set(std::vector<std::string> &cmd, Ring_buf& buf){
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

    out_nil(buf);
}

static void do_del(std::vector<std::string> &cmd, Ring_buf& buf) {
    // a dummy `Entry` just for the lookup
    Entry key;
    key.key.swap(cmd[1]);
    key.node.hcode = str_hash((uint8_t *)key.key.data(), key.key.size());
    // hashtable delete
    HNode *node = hm_delete(&g_data.db, &key.node, &entry_eq);
    if (node) { // deallocate the pair
        delete container_of(node, Entry, node);
    }

    out_int(buf, node ? 1 : 0);
}

static bool cb_keys(HNode* node, void* arg){
    Ring_buf &buf = *(Ring_buf*)arg;
    const std::string& key = container_of(node, Entry, node)->key;
    out_str(buf, key.data(), key.size());
    return true;
}

static void do_keys(std::vector<string>&, Ring_buf &buf){
    out_arr(buf, (uint32_t)hm_size(&g_data.db));
    hm_foreach(&g_data.db, &cb_keys, (void*)&buf);
}


static void do_request(std::vector<std::string> &cmd,Ring_buf &buf){
    if(cmd.size() == 2 && cmd[0] == "get"){
        do_get(cmd, buf);
    }else if(cmd.size() == 3 && cmd[0] == "set"){
        do_set(cmd, buf);
    }else if(cmd.size() == 2 && cmd[0] == "del"){
        do_del(cmd, buf);
    }else if(cmd.size() == 1 && cmd[0] == "keys"){
        do_keys(cmd, buf);
    }else{
        out_err(buf, ERR_UNKNOWN, "unknown command.");    
    }
};

static void response_begin(Ring_buf& buf, size_t *header){
    *header = buf.size(); // message header position
    buf_append_u32(buf, 0);
}

static size_t response_size(Ring_buf& buf, size_t header){
    return buf.size() - header - 4;
}

static void response_end(Ring_buf& buf, size_t header){
    size_t msg_size = response_size(buf, header);
    if(msg_size > k_max_msg){
        buf.tail = (buf.tail + buf.cap - msg_size) % buf.cap ;
        out_err(buf, ERR_TOO_BIG, "response too big");
        msg_size = response_size(buf, header);
    }
    uint32_t len = (uint32_t)msg_size;
    // buf_append(buf, (const uint8_t*)&len, sizeof(len));
    memcpy(&buf.buf[(buf.head+header)%buf.cap], &len, 4);
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
    // hex_dump(request.data(),len);

    std::vector<std::string> cmd;
    if(parse_req(request.data(), len, cmd)<0){
        msg("parse_req failed");
        conn->want_close = true;
        return false;
    }

    // Response
    size_t header_pos = 0;
    response_begin(conn->outgoing, &header_pos);
    do_request(cmd, conn->outgoing);
    response_end(conn->outgoing, header_pos);



    // make_response(resp,conn->outgoing);
    buf_consume(conn->incoming,4+len);

    return true;
}

static void send_all(Conn* conn,Ring_buf &buf){
    size_t n = buf.size();
    size_t min = std::min(n,buf.cap - buf.head);
    //cout <<" size: " << n << endl; 
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

```cpp
//client.cpp
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

enum{
    TAG_NIL = 0,    // nil
    TAG_ERR = 1,    // error code + msg
    TAG_STR = 2,    // string
    TAG_INT = 3,    // int64
    TAG_DBL = 4,    // double
    TAG_ARR = 5,    // array
};

static int32_t print_response(const uint8_t* data, size_t size){
    if(size < 1){
        msg("bad response 86");
    }
    switch(data[0]){
        case TAG_NIL:
            printf("(nil)\n");
            return -1;
        case TAG_ERR:
            if(size< 1 + 8){
                msg("bad response TAG_ERR_1");
                return -1;
            }
            {
                int32_t code = 0;
                uint32_t len = 0;
                memcpy(&code, &data[1], 4);
                memcpy(&len, &data[1+4], 4);
                if(size < 1 + 8 + len){
                    msg("bad response TAG_ERR_2");
                    return -1;
                }
                printf("(err) %d %.*s\n", code, len, &data[1 + 8]);
                return 1+8+len;
            }
        case TAG_STR:
            if(size < 1 + 4){
                msg("bad response TAG_STR_1");
                return -1;
            }
            {
                uint32_t len = 0;
                memcpy(&len, &data[1], 4);
                if(size< 1 + 4 + len){
                    msg("bad response TAG_STR_2");
                    return -1;
                }
                printf("(str) %.*s\n", len, &data[1 + 4]);
                return 1 + 4 + len;
            }
        case TAG_INT:
            if (size < 1 + 8) {
                msg("bad response TAG_INT");
                return -1;
            }
            {
                int64_t val = 0;
                memcpy(&val, &data[1], 8);
                printf("(int) %ld\n", val);
                return 1 + 8;
            }
        case TAG_DBL:
            if (size < 1 + 8) {
                msg("bad response TAG_DBL");
                return -1;
            }
            {
                double val = 0;
                memcpy(&val, &data[1], 8);
                printf("(dbl) %g\n", val);
                return 1 + 8;
            }
        case TAG_ARR:
            if(size < 1 + 4){
                msg("bad response TAG_ARR");
                return -1;
            }
            {
                uint32_t len =0;
                memcpy(&len, &data[1], 4);
                printf("(arr) len=%u", len);
                size_t arr_bytes = 1 + 4;
                for(uint32_t i = 0; i < len; i++){
                    int32_t rv = print_response(&data[arr_bytes], size-arr_bytes);
                    if(rv < 0){
                        return rv;
                    }
                    arr_bytes += (size_t)rv;
                }
                printf("(arr) end\n");
                return (int32_t)arr_bytes;
            }
        default:
            msg("bad response default");
            return -1;
    }
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

    int32_t rv = print_response((uint8_t*)&rbuf[4], len);
    if(rv > 0 && (uint32_t)rv != len){
        msg("bad response 194");
        rv = -1;
    }
    return rv;
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
