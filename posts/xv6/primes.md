---
title: xv6-2023 - primes Lab
date  : 2025-11-30
time  : 16:51:18
archive: xv6-2023
categories: [OS, Kernel, C/C++]
summary: 实现质数筛选器：使用管道和递归进程创建筛选管道，每个进程过滤当前质数的倍数。
---

# xv6-2023 - primes Lab

## Overview

Write a user-level program that uses xv6 system calls to find prime numbers using a pipeline of processes. The program should generate numbers from 2 to 35, and use a recursive pipeline approach where each process in the pipeline filters out multiples of a prime number it receives. Each process should print the prime number it finds and pass the remaining numbers to the next process. Your solution should be in the file user/primes.c.

Some hints:

- Add the program to UPROGS in Makefile.
- Use pipe to create pipes for inter-process communication.
- Use fork to create child processes.
- Use read to read from a pipe, and write to write to a pipe.
- Use recursion to create a pipeline of processes.
- User programs on xv6 have a limited set of library functions available to them. You can see the list in user/user.h; the source (other than for system calls) is in user/ulib.c, user/printf.c, and user/umalloc.c.

## solve it

根据上文的信息，我们知道我们要使用`pipe()`和`fork()`函数，以及递归来实现一个质数筛选器。程序应该生成数字2到35，然后通过管道传递给第一个进程。每个进程从管道中读取第一个数字作为质数，然后过滤掉所有能被这个质数整除的数字，将剩余的数字传递给下一个进程。

我们通过阅读代码可以了解到，这个程序使用了递归的方式来创建进程管道。每个进程负责：

1. 从父进程的管道中读取第一个数字作为质数
2. 打印这个质数
3. 创建一个新的管道
4. 创建一个子进程来处理剩余的数字
5. 过滤掉所有能被当前质数整除的数字，将剩余的数字写入子进程的管道

### pipe 和 fork

我们先来看`pipe()`和`fork()`的使用：

`pipe(int p[2])` 创建一个管道，其中 `p[0]` 是读端，`p[1]` 是写端。

`fork()` 创建一个子进程，在父进程中返回子进程的PID，在子进程中返回0。

### 递归过程

程序的核心是`primes()`函数的递归调用：

```c
void primes(int p0) {
    int prime;
    if (read(p0, &prime, sizeof(prime)) <= 0) {
        close(p0);
        exit(0);
    }
    printf("prime %d\n", prime);

    int p[2];
    pipe(p);

    if (fork() == 0) {
        // 子进程
        close(p[1]);   // 只读
        primes(p[0]);  // 递归
    } else {
        // 父进程
        close(p[0]);   // 只写
        int n;
        while (read(p0, &n, sizeof(n)) > 0) {
            if (n % prime != 0) {
                write(p[1], &n, sizeof(n));
            }
        }
        close(p[1]);
        close(p0);
        wait(0);
        exit(0);
    }
}
```

### main 函数

`main()`函数负责初始化过程：

```c
int main() {
    int p[2];
    pipe(p);

    if (fork() == 0) {
        close(p[1]);
        primes(p[0]);
    } else {
        close(p[0]);
        for (int i = 2; i <= 35; i++) {
            write(p[1], &i, sizeof(i));
        }
        close(p[1]);
        wait(0);
    }
    exit(0);
}
```

### 工作流程

1. `main()`函数创建第一个管道并生成数字2-35
2. 第一个子进程调用`primes()`开始递归过程
3. 每个`primes()`调用：
   - 读取第一个数字作为质数并打印
   - 创建新的管道和子进程
   - 过滤掉当前质数的倍数，将剩余数字传递给子进程
4. 当没有更多数字可读时，递归终止

### code

```c
#include "kernel/types.h"
#include "user/user.h"

void primes(int p0) {
    int prime;
    if (read(p0, &prime, sizeof(prime)) <= 0) {
        close(p0);
        exit(0);
    }
    printf("prime %d\n", prime);

    int p[2];
    pipe(p);

    if (fork() == 0) {
        // 子进程
        close(p[1]);   // 只读
        primes(p[0]);  // 递归
    } else {
        // 父进程
        close(p[0]);   // 只写
        int n;
        while (read(p0, &n, sizeof(n)) > 0) {
            if (n % prime != 0) {
                write(p[1], &n, sizeof(n));
            }
        }
        close(p[1]);
        close(p0);
        wait(0);
        exit(0);
    }
}

int main() {
    int p[2];
    pipe(p);

    if (fork() == 0) {
        close(p[1]);
        primes(p[0]);
    } else {
        close(p[0]);
        for (int i = 2; i <= 35; i++) {
            write(p[1], &i, sizeof(i));
        }
        close(p[1]);
        wait(0);
    }
    exit(0);
}
```

运行成功的输出为：

```bash
prime 2
prime 3
prime 5
prime 7
prime 11
prime 13
prime 17
prime 19
prime 23
prime 29
prime 31
```
