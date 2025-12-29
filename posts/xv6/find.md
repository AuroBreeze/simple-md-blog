---
title: xv6-2023 - find Lab
date  : 2025-11-30
time  : 16:51:18
archive: xv6-2023
categories: [OS, Kernel, C/C++]
summary: 实现UNIX find命令：递归遍历目录树查找指定文件，解析文件系统结构、目录项和inode操作。
---

# xv6-2023 - find Lab

## Overview

Write a simple version of the UNIX find program for xv6: find all the files in a directory tree with a specific name. Your solution should be in the file user/find.c.

Some hints:

Look at user/ls.c to see how to read directories.
Use recursion to allow find to descend into sub-directories.
Don't recurse into "." and "..".
Changes to the file system persist across runs of qemu; to get a clean file system run make clean and then make qemu.
You'll need to use C strings. Have a look at K&R (the C book), for example Section 5.5.
Note that == does not compare strings like in Python. Use strcmp() instead.
Add the program to UPROGS in Makefile.

## solve it

根据上文的提示，我要参照`user/ls.c`中的实现，来编写`find()`。

我们知道，`ls`命令是列出选定目录的所有文件，而我们的`find`命令是查找选定目录下的文件，这也就代表着，`ls`和`find`命令是及其相近的，不过`find`多了一个递归**子目录**的功能，和对比文件名称的功能。

## user/ls.c 函数解析

### user/ls.c ---> 0

通过查看`user/ls.c`中的定义，`void ls(char *path)`，我们来看`user/ls.c`主函数的代码：

```c
// void ls(char *path)

int
main(int argc, char *argv[])
{
  int i;

  if(argc < 2){
    ls(".");
    exit(0);
  }
  for(i=1; i<argc; i++)
    ls(argv[i]);
  exit(0);
}
```

我们可以看到，`ls`函数的参数是`char *path`，我们在仿写`find`函数的时候，可以按照他`ls`命令来仿写。

```c
  char buf[512], *p;
  int fd;
  struct dirent de;
  struct stat st;
```

在`user/ls.c`中，`buf`是存储目录信息的缓冲区，`p`是目录信息缓冲区的指针，`fd`是目录文件描述符，`de`是目录项结构体，`st`是文件状态结构体。

关于`dirent`结构体和`stat`结构体之间的关系，可以查看以下图示：

```c
[目录 inode]   (type = T_DIR)
     │
     │   包含数据块指针
     ▼
+-------------------------------+
|   目录数据块 (存放 dirent[])  |
+-------------------------------+
|  dirent:                      |
|   inum = 5   name = "."       |
|  dirent:                      |
|   inum = 1   name = ".."      |
|  dirent:                      |
|   inum = 12  name = "foo.txt" |───┐
|  dirent:                      |   │
|   inum = 13  name = "bar"     |───┼──► [inode #13] (type = T_DIR)
|  ...                          |   │
+-------------------------------+   │
                                    │
                                    ▼
                              [inode #12] (type = T_FILE)
                               │
                               │ inode 里有元数据
                               ▼
                         struct stat {
                            dev=1,
                            ino=12,
                            type=T_FILE,
                            nlink=1,
                            size=1024
                         }
```

接下来分析：

```c
  if((fd = open(path, O_RDONLY)) < 0){
    fprintf(2, "ls: cannot open %s\n", path);
    return;
  }
```
函数`open()`打开文件，并将文件描述符进行配置，设置文件描述符的只读模式。我们可以具体去`kernel/sysfile.c`中查看`sys_open()`函数的实现：

### kernel/sysfile.c sys_open() 函数解析

```c
uint64
sys_open(void)
{
  char path[MAXPATH];
  int fd, omode;
  struct file *f;
  struct inode *ip;
  int n;

  argint(1, &omode);
  if((n = argstr(0, path, MAXPATH)) < 0)
    return -1;

  begin_op();

  if(omode & O_CREATE){
    ip = create(path, T_FILE, 0, 0);
    if(ip == 0){
      end_op();
      return -1;
    }
  } else {
    if((ip = namei(path)) == 0){
      end_op();
      return -1;
    }
    ilock(ip);
    if(ip->type == T_DIR && omode != O_RDONLY){
      iunlockput(ip);
      end_op();
      return -1;
    }
  }

  if(ip->type == T_DEVICE && (ip->major < 0 || ip->major >= NDEV)){
    iunlockput(ip);
    end_op();
    return -1;
  }

  if((f = filealloc()) == 0 || (fd = fdalloc(f)) < 0){
    if(f)
      fileclose(f);
    iunlockput(ip);
    end_op();
    return -1;
  }

  if(ip->type == T_DEVICE){
    f->type = FD_DEVICE;
    f->major = ip->major;
  } else {
    f->type = FD_INODE;
    f->off = 0;
  }
  f->ip = ip;
  f->readable = !(omode & O_WRONLY);
  f->writable = (omode & O_WRONLY) || (omode & O_RDWR);

  if((omode & O_TRUNC) && ip->type == T_FILE){
    itrunc(ip);
  }

  iunlock(ip);
  end_op();

  return fd;
}
```

我们不再递归，将其他函数全部解析，只告诉函数的作用。


```c
  char path[MAXPATH];
  int fd, omode;
  struct file *f;
  struct inode *ip;
  int n;

  argint(1, &omode);
  if((n = argstr(0, path, MAXPATH)) < 0)
    return -1;
```

这段代码我们应该很熟悉了，将寄存器中保存的参数取出，也就是`open(path, O_RDONLY)`中的`path`和`O_RDONLY`。

```c
  begin_op();
  end_op();
```
`begin_op()`和`end_op()`函数是别用于开始和结束一个磁盘操作(保证磁盘操作的**原子性**操作)。


```c
    if((ip = namei(path)) == 0){
      end_op();
      return -1;
    }
    ilock(ip);
    if(ip->type == T_DIR && omode != O_RDONLY){
      iunlockput(ip);
      end_op();
      return -1;
    }
```

在下面`if`判断的`else`块中，我们调用了`namei()`函数，这个函数的功能是返回文件名对应的**inode**。

`namei()`会解析传入的路径并进行寻找`inode`。

随后通过

```c
  if((f = filealloc()) == 0 || (fd = fdalloc(f)) < 0){
    if(f) 
      fileclose(f);
    iunlockput(ip);
    end_op();
    return -1;
  }
```

我们将`file`结构体进行分配，并返回一个`file`文件描述符。

代码的最后，将数据复制到`file`结构体中，并将`file`的文件描述符返回给用户。

### user/ls.c ---> 1

我们继续分析`ls.c`中的代码。

```c
    if(fstat(fd, &st) < 0){
        fprintf(2, "find: cannot stat %s\n", path);
        close(fd);
        return -1;
    }

  // st 的结构体
  struct stat {
    int dev;     // File system's disk device
    uint ino;    // Inode number
    short type;  // Type of file
    short nlink; // Number of links to file
    uint64 size; // Size of file in bytes
};
```

`fstat()`函数的功能是将文件描述符`fd`对应的文件状态信息复制到`st`结构体中。

```c
    if(strlen(path) + 1 + DIRSIZ + 1 > sizeof buf){
        printf("find: path too long\n");
        close(fd);
        return -1;
    }
```

在这个判断条件中，`strlen(path) + 1 + DIRSIZ + 1`表示的是`path`的长度加上一个`/`和`DIRSIZ`，`DIRSIZ`表示的是目录项名字的**最大长度**，再加上一个`\0`。

> 判断中的两个`1`，分别代表将要插入的`/`和结束符`\0`。

```c
    short type = st.type;
    if(type == T_FILE || type == T_DEVICE){
        char *basename = _basename(path);
        if(strcmp(name, basename) == 0){
            fprintf(1, "%s\n", path);
        }
    }else if(type == T_DIR){
        p = buf+strlen(buf);
        *p++ = '/';
        while(read(fd, &de, sizeof(de)) == sizeof(de)){
            if(strcmp(de.name, ".") == 0 || strcmp(de.name, "..") == 0)
                continue;
            if(de.inum == 0)
                continue;
            memmove(p, de.name, DIRSIZ);
            p[DIRSIZ] = 0;
            if(stat(buf, &st) < 0){
                fprintf(2, "find: connt stat %s\n", buf);
                continue;
            }
            find(buf, name);
        }
    }
```

在这段代码中，我使用了`_basename()`用来获取路径里的文件名，然后进行判断是否是需要要查找的文件。

这段代码的重点是对目录进行遍历，并调用`find()`函数进行递归查找。

当我们进入`else`块中，`buf`中存放着我们的路径，我们将指针`p`指向`buf`的末尾，并添加一个`/`，准备在拼接新的路径并进行递归。

在使用`read()`读取目录时，目录中的内容大概是这样的：

```c
+-------------------------------+
|   目录数据块 (存放 dirent[])  |
+-------------------------------+
|  dirent:                      |
|   inum = 5   name = "."       |
|  dirent:                      |
|   inum = 1   name = ".."      |
|  dirent:                      |
|   inum = 12  name = "foo.txt" |
|  dirent:                      |   
|   inum = 13  name = "bar"     |
|  ...                          |   
+-------------------------------+ 
```

使用`while`配合`read(fd, &de, sizeof(de)) == sizeof(de)`会读出目录项，直到读完所有的目录项。

在`read()`中每次读取目录项(内核使用`fd`索引对应的`file`结构体)，都会修改`file->off`，来记录偏移位置，直到读完所有的目录项。

然后使用`memmove()`将读取目录项下的名字复制到`buf`中，并使用`p[DIRSIZ]`向`buf`中添加一个结束符。

然后使用`stat()`将`buf`中存放的路径的文件信息保存到`st`中。

最后进行递归调用

### _basename()
`_basename()`函数用于获取路径中的文件名。

```c
static char *_basename(char *path){
    char *p;

    for(p = path+strlen(path); p>=path && *p != '/'; --p);
    ++p;
    return p;
}
```

`_basename()`函数的实现原理是：从路径的最后一个字符开始，逐个字符向前遍历，直到找到第一个斜杠（/）的位置，然后返回该位置之后的字符。

## code

```c
#include "kernel/types.h"
#include "kernel/stat.h"
#include "user/user.h"
#include "kernel/fs.h"
#include "kernel/fcntl.h"

static char *_basename(char *path){
    char *p;

    for(p = path+strlen(path); p>=path && *p != '/'; --p);
    ++p;
    return p;
}
int find(char *path, char *name){
    char buf[512], *p;
    int fd;
    struct dirent de;
    struct stat st;

    if((fd = open(path, O_RDONLY)) < 0){
        fprintf(2, "find: cannot open %s\n", path);
        return -1;
    }

    if(fstat(fd, &st) < 0){
        fprintf(2, "find: cannot stat %s\n", path);
        close(fd);
        return -1;
    }
    if(strlen(path) + 1 + DIRSIZ + 1 > sizeof buf){
        printf("find: path too long\n");
        close(fd);
        return -1;
    }
    strcpy(buf, path);
    
    short type = st.type;
    if(type == T_FILE || type == T_DEVICE){
        char *basename = _basename(path);
        if(strcmp(name, basename) == 0){
            fprintf(1, "%s\n", path);
        }
    }else if(type == T_DIR){
        p = buf+strlen(buf);
        *p++ = '/';
        while(read(fd, &de, sizeof(de)) == sizeof(de)){
            if(strcmp(de.name, ".") == 0 || strcmp(de.name, "..") == 0)
                continue;
            if(de.inum == 0)
                continue;
            memmove(p, de.name, DIRSIZ);
            p[DIRSIZ] = 0;
            if(stat(buf, &st) < 0){
                fprintf(2, "find: connt stat %s\n", buf);
                continue;
            }
            find(buf, name);
        }
    }
    close(fd);
    return 1;
}

int main(int argc, char *argv[]){
    if(argc != 3){
        fprintf(2, "Usage: find <path> <name>\n");
        exit(0);
    }
    find(argv[1], argv[2]);
    exit(0);
    return 0;
}
```
