---
title: xv6-2023 - Sleep Lab
date  : 2025-11-30
time  : 16:51:18
archive: xv6-2023
categories: [OS, Kernel, C/C++]
summary: 实现sleep命令：解析命令行参数，调用系统调用暂停进程指定时间，深入分析系统调用机制。
---

# xv6-2023 - Sleep Lab


## Overview
Implement a user-level sleep program for xv6, along the lines of the UNIX sleep command. Your sleep should pause for a user-specified number of ticks. A tick is a notion of time defined by the xv6 kernel, namely the time between two interrupts from the timer chip. Your solution should be in the file user/sleep.c.

Some hints:

Before you start coding, read Chapter 1 of the xv6 book.
Put your code in user/sleep.c. Look at some of the other programs in user/ (e.g., user/echo.c, user/grep.c, and user/rm.c) to see how command-line arguments are passed to a program.
Add your sleep program to UPROGS in Makefile; once you've done that, make qemu will compile your program and you'll be able to run it from the xv6 shell.
If the user forgets to pass an argument, sleep should print an error message.
The command-line argument is passed as a string; you can convert it to an integer using atoi (see user/ulib.c).
Use the system call sleep.
See kernel/sysproc.c for the xv6 kernel code that implements the sleep system call (look for sys_sleep), user/user.h for the C definition of sleep callable from a user program, and user/usys.S for the assembler code that jumps from user code into the kernel for sleep.
sleep's main should call exit(0) when it is done.
Look at Kernighan and Ritchie's book The C programming language (second edition) (K&R) to learn about C.

## slove it

首先我们通过查看`user/echo.c`和`user/grep.c`，我们知道,**系统调用函数**的两个参数分别是`int argc`(即参数的个数)，`char *argv[]`(参数的数组)。

假设我们的输入是`sleep 10`，那么`argc`为2，`argv[0]`为`sleep`，`argv[1]`为`10`。

同时我们根据`hint`，我们去查看`kernel/sysproc.c`中的`sys_sleep(void)`，这是`user/user.h`中`sleep()`调用的函数。

> 关于为什么我们点击`sleep()`无法找到对应的函数，是因为，所有关联的函数，都通过`usys.S`进行映射。

```c
用户态进程
+--------------------+
| int r = sleep(10); |
+--------------------+
          |
          v
   usys.S 封装函数
   -----------------
   li a7, SYS_sleep   ; 把系统调用号放到 a7
   ecall              ; 触发陷入 (进入内核)
   -----------------
          |
          v
=================== 内核态 ===================
          |
          v
 trap handler 保存寄存器 → 填写 trapframe
          |
          v
 syscall() 分发器
 +------------------------------------------+
 | num = p->trapframe->a7  (取系统调用号)   |
 | if(num合法)                             |
 |    调用 syscalls[num]()                  |
 | else                                     |
 |    返回 -1                               |
 +------------------------------------------+
          |
          v
 sys_sleep()
 +------------------------------------------+
 | 解析参数 argint(0, &n)                    |  
 | 从 a0寄存器中获取参数 n                    |
 | while(ticks - ticks0 < n) {              |
 |    sleep(&ticks, &tickslock);            |
 | }                                        |
 | return 0;                                |
 +------------------------------------------+
          |
          v
 返回值写入 p->trapframe->a0
          |
          v
 usertrapret()
   恢复寄存器 (含 a0)
   sret → 切回用户态
          |
          v
用户态继续执行
+--------------------------------+
| r = (返回值在 a0，即 0 或 -1) |
+--------------------------------+

```

我们在这里需要知道的是，`RISC-V`的约定，是**寄存器 a7** 中保存系统调用号，所以在`kernel/syscall.c`中，有专门的函数的映射，也就是`syscalls[]`，另一个`RISC-V`的约定是，**寄存器 a0 - a5** 中保存系统调用的参数，也就是我们在`user/user.h`中的函数的参数
，同时处理完的返回值也会保存在**寄存器 a0** 中。

也就是说，在`kernel/syscall.c`中的这句话`p->trapframe->a0 = syscalls[num]();`就是调用函数，并将返回值保存在**寄存器 a0** 中。

```c
uint64
sys_sleep(void)
{
  int n;
  uint ticks0;

  argint(0, &n);
  if(n < 0)
    n = 0;
  acquire(&tickslock);
  ticks0 = ticks;
  while(ticks - ticks0 < n){
    if(killed(myproc())){
      release(&tickslock);
      return -1;
    }
    sleep(&ticks, &tickslock);
  }
  release(&tickslock);
  return 0;
}
```

上面是系统调用`sys_sleep()`的具体实现，在这里的`n`是我们准备传入的`sleep 10`中的`10`，(当然现在只是定义了变量，10 不可能凭空传进去)，我们往下看，就能看到第一个有关`n`的函数调用`argint(0, &n);`。

`argint()`这个函数可以这样拆分名称，`arg`和`int`，`arg`表示参数，`int`表示参数的类型，这里参数的类型是`int`。

其中，`acquire()`和`release()`用来获取**锁**和释放**锁**，用来保护共享资源。在这里我们先不深入探究。

我们在`while`会发现还有一个`if`的判断语句，`if(killed(myproc()))`，这里的作用就是判断我们当前的进程是否被杀死，如果被杀死就将锁释放。

`myproc()`这个可以简单理解为**获取当前进程**。


我们可以看一下`kernel/syscall.c`中的`argint()`的具体实现：

```c
void
argint(int n, int *ip)
{
  *ip = argraw(n);
}

static uint64
argraw(int n)
{
  struct proc *p = myproc();
  switch (n) {
  case 0:
    return p->trapframe->a0;
  case 1:
    return p->trapframe->a1;
  case 2:
    return p->trapframe->a2;
  case 3:
    return p->trapframe->a3;
  case 4:
    return p->trapframe->a4;
  case 5:
    return p->trapframe->a5;
  }
  panic("argraw");
  return -1;
}
```

函数`argraw()`中，我们通过`switch`语句，将`n`映射到对应的寄存器中，然后返回对应的值。

也就是说，`argint(int n, int *ip)`函数中的`n`就是对应的寄存器，我们上面也说过了，我们传入的参数会依次保存在寄存器中，我们在`user/user.h`查看函数`sleep()`函数，就是`int sleep(int);`，仅传入一个参数，那么这个参数就会被保存到寄存器`a0`中。

> 感兴趣可以去看看`kernel/proc.h`中的`struct proc`结构体，里面有`trapframe`成员变量，这个结构体中保存了**寄存器**的值。

## code

具体的代码的运行我们已经了解了，如果还想具体的深入，我建议查看[使用gdb](https://pdos.csail.mit.edu/6.1810/2023/labs/syscall.html)来深入查看一下运行过程，会理解很多。

```c
#include "kernel/types.h"
#include "kernel/stat.h"
#include "user/user.h"

int main(int argc, char *argv[]){
    if(argc != 2){
        fprintf(2, "Usage: sleep <time>\n");
        exit(1);
    };
    int time = atoi(argv[1]);
    if(time < 0){
        fprintf(2, "Usage: sleep <time> > 0\n");
        exit(1);
    }
    sleep(time);
    exit(0);
}
```

整体的代码并不难理解，接收到参数后，使用`atoi()`将参数转换成数字，然后调用`sleep()`函数，等待指定的`tick`就可以了。
