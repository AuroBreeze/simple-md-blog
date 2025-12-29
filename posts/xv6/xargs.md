---
title: xv6-2023 - xargs Lab
date  : 2025-11-30
time  : 16:51:18
archive: xv6-2023
categories: [OS, Kernel, C/C++]
summary: 实现xargs命令：从标准输入读取参数，为每行参数创建子进程执行命令，深入理解进程创建和参数传递。
---

# xv6-2023 - xargs Lab

## Overview

Write a simple version of the UNIX xargs program for xv6: its arguments describe a command to run, it reads lines from the standard input, and it runs the command for each line, appending the line to the command's arguments. Your solution should be in the file user/xargs.c.

The following example illustrates xarg's behavior:
```bash
$ echo hello too | xargs echo bye
bye hello too
$
```
  
Note that the command here is "echo bye" and the additional arguments are "hello too", making the command "echo bye hello too", which outputs "bye hello too".
Please note that xargs on UNIX makes an optimization where it will feed more than argument to the command at a time. We don't expect you to make this optimization. To make xargs on UNIX behave the way we want it to for this lab, please run it with the -n option set to 1. For instance
```bash
$ (echo 1 ; echo 2) | xargs -n 1 echo
1
2
$
```
Some hints:

Use fork and exec to invoke the command on each line of input. Use wait in the parent to wait for the child to complete the command.
To read individual lines of input, read a character at a time until a newline ('\n') appears.
kernel/param.h declares MAXARG, which may be useful if you need to declare an argv array.
Add the program to UPROGS in Makefile.
Changes to the file system persist across runs of qemu; to get a clean file system run make clean and then make qemu.

## solve it
