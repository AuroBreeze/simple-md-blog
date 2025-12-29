---
title: xv6-2023 - pingpong Lab
date  : 2025-11-30
time  : 16:51:18
archive: xv6-2023
categories: [OS, Kernel, C/C++]
summary: 实现进程间通信的ping-pong程序：使用管道和fork创建父子进程，通过双向管道传递消息。
---

# xv6-2023 - pingpong Lab

## Overview

Write a user-level program that uses xv6 system calls to ''ping-pong'' a byte between two processes over a pair of pipes, one for each direction. The parent should send a byte to the child; the child should print "<pid>: received ping", where <pid> is its process ID, write the byte on the pipe to the parent, and exit; the parent should read the byte from the child, print "<pid>: received pong", and exit. Your solution should be in the file user/pingpong.c.

Some hints:

Add the program to UPROGS in Makefile.
Use pipe to create a pipe.
Use fork to create a child.
Use read to read from a pipe, and write to write to a pipe.
Use getpid to find the process ID of the calling process.
User programs on xv6 have a limited set of library functions available to them. You can see the list in user/user.h; the source (other than for system calls) is in user/ulib.c, user/printf.c, and user/umalloc.c.

## slove it

根据上文的信息，我们知道我们要使用`pipe()`和`fork()`函数，来实现这样的一个功能，父进程向子进程发送一个字节，子进程接收到字节后，将字节写入父进程，并进行打印。

我们通过阅读`xv6 book`的第一章内容，我们知道，`pipe`管道是一个**半双工**的管道，即**只能有一个读进程和一个写进程**，这也就意味着，我们一个管道是无法来实现两个进程间的通信的，所以我们要创建两个管道，一个用于父进程向子进程发送字节，一个用于子进程向父进程发送字节。

> 需要注意的是，我们在使用`pipe`管道的时候，我们要及时关闭无意义的管道读/写端，否则可能会导致程序阻塞。
> 也就是说，我们要写入消息时，要先关闭读端`close(p[0])`，写入消息后，再关闭写端`close(p[1])`。同理，我们要读取消息时，要先关闭写端`close(p[1])`，读取消息后，再关闭读端`close(p[0])`。

### pipe

我们先来看`pipe()`的代码实现

```c
uint64
sys_pipe(void)
{
  uint64 fdarray; // user pointer to array of two integers
  struct file *rf, *wf;
  int fd0, fd1;
  struct proc *p = myproc();

  argaddr(0, &fdarray);
  if(pipealloc(&rf, &wf) < 0)
    return -1;
  fd0 = -1;
  if((fd0 = fdalloc(rf)) < 0 || (fd1 = fdalloc(wf)) < 0){
    if(fd0 >= 0)
      p->ofile[fd0] = 0;
    fileclose(rf);
    fileclose(wf);
    return -1;
  }
  if(copyout(p->pagetable, fdarray, (char*)&fd0, sizeof(fd0)) < 0 ||
     copyout(p->pagetable, fdarray+sizeof(fd0), (char *)&fd1, sizeof(fd1)) < 0){
    p->ofile[fd0] = 0;
    p->ofile[fd1] = 0;
    fileclose(rf);
    fileclose(wf);
    return -1;
  }
  return 0;
}
```

我们看`user/user.h`中的定义为`int pipe(int*);`其中参数是`int*`也就是一个指针。

所以在`kernel/sysfile.c`中的`sys_pipe()`中定义了`uint fdarray;`来接收地址，用`argaddr()`函数将地址保存在`fdarray`中。

在约定的`pipe`管道中，`p[0]`是读端，`p[1]`是写端。

所以在`sys_pipe()`中，定义了两个文件描述符`rf`和`wf`，分别保存读端和写端，并使用`pipealloc()`函数创建管道，也就是将`rf`设置为只读，`wf`设置为只写。

```c
int
pipealloc(struct file **f0, struct file **f1)
{
    /*
        other code
    */
    if((pi = (struct pipe*)kalloc()) == 0)
    goto bad;
    pi->readopen = 1;
    pi->writeopen = 1;
    pi->nwrite = 0;
    pi->nread = 0;
  initlock(&pi->lock, "pipe");
    (*f0)->type = FD_PIPE;
    (*f0)->readable = 1;  // 读端
    (*f0)->writable = 0;
    (*f0)->pipe = pi;
    (*f1)->type = FD_PIPE;
    (*f1)->readable = 0;
    (*f1)->writable = 1;  // 写端
    (*f1)->pipe = pi;
    /*
        other code
    */
}

struct file {
  enum { FD_NONE, FD_PIPE, FD_INODE, FD_DEVICE } type;
  int ref; // reference count
  char readable;
  char writable;
  struct pipe *pipe; // FD_PIPE
  struct inode *ip;  // FD_INODE and FD_DEVICE
  uint off;          // FD_INODE
  short major;       // FD_DEVICE
};
```

并通过`fdalloc()`分配文件描述符，并返回给用户。

```c
static int fdalloc(struct file *f)
{
  int fd;
  struct proc *p = myproc();  // 获取当前进程结构体

  for(fd = 0; fd < NOFILE; fd++){   // 遍历进程的文件表
    if(p->ofile[fd] == 0){          // 找到一个空闲的文件描述符位置
      p->ofile[fd] = f;             // 将文件结构体指针存入该位置
      return fd;                     // 返回分配到的文件描述符
    }
  }
  return -1;  // 如果没有空闲位置，返回 -1 表示失败
}
```

其中`NOFILE`是每个进程最多持有的文件描述符数，为16。

```c
fd: 0 1 2 3 4 ... 15
p->ofile: f0 f1 0 0 0 ... 0
```

> 在`sys_pipe()`中的`if((fd0 = fdalloc(rf)) < 0 || (fd1 = fdalloc(wf)) < 0) if(fd0 >= 0) p->ofile[fd0] = 0;`(简化了一下，与原文略有不同)，当其中一个文件描述符分配失败时，会释放已经分配的文件描述符，并返回 -1 错误，分为两种情况，通过`fd0 < 0`的短路进入`if`语句，或者通过`fd1 < 0`进入，我们要确保将文件描述符的正确释放，所以要判断`fd0 >= 0`时也就是`fd0`分配成功，而`fd1 < 0`分配失败的时候，要将`fd0`释放，避免资源泄露。

我们使用`copyout()`将文件描述符保存到用户空间中，并返回给用户。

> 为什么要使用`copyout()`来将数据保存到用户空间中呢？
> 因为用户空间和内核空间是隔离的，内核空间中的数据不能直接访问用户空间中的数据，所以需要使用`copyout()`来将数据保存到用户空间中。

```c
// Copy from kernel to user.
// Copy len bytes from src to virtual address dstva in a given page table.
// Return 0 on success, -1 on error.
int
copyout(pagetable_t pagetable, uint64 dstva, char *src, uint64 len)
```

根据`copyout()`的定义及注释，我们需要四个参数：

1. pagetable: 页表
2. dstva: 目标地址
3. src: 源数据
4. len: 数据长度

其中，我们使用的`struct proc *p = myproc();`，已经获取了当前进程结构体，所以可以直接使用`p->pagetable`作为参数`pagetable`。

`dstva`是目标地址，这里我们使用`fdarray`作为目标地址，也就是我们传入的`pipe(p)`中`p`的地址，`fdarray`是一个指针，所以`dstva`就是`fdarray`的地址。

`src`是源数据，这里我们使用`&fd0`和`&fd1`作为源数据，也就是我们分配的文件描述符`fd0`和`fd1`。

`len`是数据长度，这里我们使用`sizeof(fd0)`和`sizeof(fd1)`作为数据长度，也就是我们分配的文件描述符`fd0`和`fd1`的长度。

这样就可以将我们获取到的文件描述符保存到用户空间中。

### code

```c
#include "kernel/types.h"
#include "kernel/stat.h"
#include "user/user.h"

int
main(int argc, char *argv[])
{
    if(argc != 1){
        fprintf(2, "Usage: pingpong\n");
        exit(1);
    }

    int p1[2], p2[2];
    pipe(p1); // parent -> child
    pipe(p2); // child -> parent

    int pid = fork();
    if(pid < 0){
        fprintf(2, "fork failed\n");
        exit(1);
    }

    if(pid == 0){
        // ===== 子进程 =====
        close(p1[1]); // 子进程不写 p1
        close(p2[0]); // 子进程不读 p2

        char buf[10];
        read(p1[0], buf, sizeof(buf));
        fprintf(1, "%d: received %s\n", getpid(), buf);

        write(p2[1], "pong", 4);

        close(p1[0]);
        close(p2[1]);
    } else {
        // ===== 父进程 =====
        close(p1[0]); // 父进程不读 p1
        close(p2[1]); // 父进程不写 p2

        write(p1[1], "ping", 4);

        char buf[10];
        read(p2[0], buf, sizeof(buf));
        fprintf(1, "%d: received %s\n", getpid(), buf);

        close(p1[1]);
        close(p2[0]);
    }

    exit(0);
}
```

在上文中，我们讲`pipe()`函数的返回值保存在`p[0]`和`p[1]`中，同时是先返回的`rf`，然后返回的`wf`，也就是说`p[0]`是读端，`p[1]`是写端。

> 数组`p`中存放的两个数据，都是**文件描述符**

通过`fork()`创建子进程，并通过`pipe`传递消息(在这里不深入为什么要及时关闭无用的管道读/写端)。

运行成功的输出为：

```bash
2: received ping
1: received pong
```
