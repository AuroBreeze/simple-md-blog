# Implementing Redis in C++ : I
# Redis C++ 实现笔记（I篇）

## 前言
本章代码及思路均来自[Build Your Own Redis with C/C++](https://build-your-own.org/redis/)

本文章只阐述我的理解想法，以及需要注意的地方。

本文章为续<<[Redis C++ 实现笔记（H篇）](https://blog.csdn.net/m0_58288142/article/details/151374071?fromshare=blogdetail&sharetype=blogdetail&sharerId=151374071&sharerefer=PC&sharesource=m0_58288142&sharefrom=from_link)>>所以本文章不再完整讲解全部代码，只讲解其不同的地方


## 主体思路

在原文中，作者给我们讲说了为什么要选择使用多线程：

1. 阻塞I/O : 如`DNS`查询(`getaddrinfo`)和`HTTP`请求(`libcurl`)，这些通常是阻塞式的，无法直接用于事件循环。解决方案是使用**非阻塞的回调式API**，如`c-ares`(`DNS`)或(`libcurl`)的非阻塞模式。
2. CPU 密集型任务 : 就比如我们在之前实现的键值的存储，其中的`ZSet`中，有`AVL树`和`hashtable`等存储结构，当我们要删除这个键的时候，也就是删除`AVL树`和`hashtable`中的数据，删除大型有序集合时，析构函数需要逐一删除每个元素，导致**O(N)**的性能瓶颈，可能会导致`server`端的卡顿或崩溃，所以我们就要考虑如何优化这个性能，在本文中也就是将`ZSet`中的数据，放到后台线程中，进行删除。

---

在进行讲解本文的思路和代码之前，我们需要先进行了解**多线程**的知识。

多线程`Multithreading`是指在同一个程序**进程**中，同时存在多个**执行流(线程)**的技术。每个线程都有自己的执行路径，但它们共享**同一个进程的资源**(如内存、文件句柄等)

要注意，多线程会共享**同一个进程的资源**，这个是一个很敏感的事情。

为什么这么说？

当我们有多个线程同时访问一个资源的时候，如果这个资源是**可变**的，那么**线程之间会相互影响**，可能会导致很多莫名奇怪的bug。

所以当我们们在多线程中访问一个资源时，**一定要**使用**锁**来保证线程安全。

什么是**锁**`mutex`？

**锁**是一种机制，它可以**保证**多个线程同时访问一个资源时，**不会相互影响**，但是**锁**只能有一个线程持有，其他线程只能等待持有锁的线程释放锁后才能获取锁，然后进行访问资源。这样就能保证在多线程中访问一个资源时，**不会相互影响**。

锁的实现方式有很多中，这里我们使用**互斥锁**来实现。

什么是互斥锁？

互斥锁`Mutex，Mutual Exclusion Lock`是多线程编程中最基本的一种锁，用来保证同一时刻只有一个线程可以访问共享资源，从而避免数据竞争`Race Condition`和不一致问题。

也就是说，当我们获取到锁的时候，其他的线程就只能等待，直到锁被释放，如果我们持有锁的时间够长，那么就会导致锁的等待时间过长，从而导致性能下降，所以说，我们持有锁的时间越短越好，我们应该在访问共享资源前立即获取锁，并在访问结束后立即释放锁，不要把不相关的(与访问共享资源无关)的操作放在锁内进行，尽可能减少锁的持有时间。

> 要知道，把不相关的操作都放在锁内，我们就会失去多线程的优势。

而我们如何获取锁？

这里我们就要讲`condition_variable`**条件变量**了。

**锁**与**条件变量**一般来说都是一起使用的，**锁**是用来保护共享资源，防止数据竞争的，而**条件变量**是当特定的条件满足的时候，让对应的线程获取**锁**(控制线程何时等待，何时继续)。

---

在本次的文章中，原作者改动的部分只有删除`zset`的代码，其他部分的改动较小，我们也就不再讲解了。

## code

### thread_pool.h

```cpp
#pragma once

#include <pthread.h>
#include <stddef.h>
#include <vector>
#include <deque>

struct Work{
    void (*f)(void*) = nullptr;
    void* arg = nullptr;
};

struct TheadPool{
    std::vector<pthread_t> threads;
    std::deque<Work> queue;
    pthread_mutex_t mutex;
    pthread_cond_t not_empty;
};

void thread_pool_init(TheadPool* tp, size_t num_threads);
void thread_pool_queue(TheadPool* tp, void (*f)(void*), void *arg);
```

在这段代码中，我们首先创建了一个`Work`结构体，这个结构体包含一个函数指针`f`和一个参数指针`arg`，也就是说，这个结构体，用来存放我们要使用的函数的指针和参数，我们为什么要这样写？

因为我们创建的线程可能会执行不同的操作，而写死一个函数的话，会**限制**我们写的**消费函数**，通过这样动态灵活的方式，我们就可以实现一个函数，可以执行多种不同的操作了。

在我们的`TheadPool`结构体中，我们使用双端队列`deque`来存储`Work`任务，同时我们使用`vector`来存储线程的`ID`(`typedef unsigned long long pthread_t`)，同时定义了**锁**`mutex`和**条件变量**`not_empty`。

> 关于为什么条件变量的取名是`not_empty`，因为在本文中，我们使用**生产-消费**模式，当队列为空的时候，消费者线程会等待，当队列不为空的时候，消费者线程会从队列中取出任务并执行。

### thread_pool.cpp

#### worker()

```cpp
static void* worker(void* arg){
    TheadPool* tp = (TheadPool*) arg;
    while(true){
        pthread_mutex_lock(&tp->mutex);

        // wait for the condition : a non-empty queue
        while(tp->queue.empty()){
            pthread_cond_wait(&tp->not_empty, &tp->mutex);
        }

        // got the job
        Work w = tp->queue.front();
        tp->queue.pop_front();
        pthread_mutex_unlock(&tp->mutex);

        // do the work
        w.f(w.arg);
    }
    return nullptr;
}
```

这就是我们的**消费线程**，在这里我们函数的定义是`static void* worker(void* arg)`，为什么要这样定义？因为我们创建线程的函数是`pthread_create(pthread_t *th, const pthread_attr_t *attr, void *(* func)(void *), void *arg);`也就是第三个参数，这里必须要求我们传`void*`，不过，这样并不妨碍我们函数正常的运行，我们只需要在函数中将参数转为我们想要的类型即可，比如我们这里转换成了`TheadPool`。

在我们代码中`TheadPool`结构体，就是我们的共享资源，在我们想要读取他的时候，我们就需要先获取**锁**，然后进行读取数据。

不过，要注意的是，如果我们的队列中是`empty`的话，我们执行下面的代码，`tp->queue.pop_front();`肯定是会报错的，所以在取数据前，我们先判断一下队列是否为空，如果为空，我们就等待，当然我们在等待的时候，我们要使用`pthread_cond_wait`，这个函数的作用是让线程等待，直到被其他线程唤醒，这个时候锁会被释放，让其他线程先执行，在被唤醒的时候，重新获取锁。

在我们判断是否为空的时候，我们使用了`while`循环，这个循环的作用是**避免虚假唤醒**，因为即使不使用`signal`或`broadcast`唤醒线程，线程也可能会被唤醒(具体了解可以自行查阅)，所以要使用`while`循环，判断，保证线程被唤醒的时候，队列不为空。

---

在本文中，我们要做的实现就是启用新的线程删除比较大的**有序集合**，所以在这里，你可以将`w.f`看作我们要执行的删除函数，这个函数执行的就是**CPU密集型的任务**，这个任务是与**访问共享资源**无关的，因为我们已经拿到了任务`Work`，我们就没有必要再使用**锁**了，所以我们将这个任务放到锁的外面，及时的将锁释放掉，提升运行效率。

#### init(), queue()

```cpp
void thread_pool_init(TheadPool* tp, size_t num_threads){
    assert(num_threads > 0);

    int rv = pthread_mutex_init(&tp->mutex, nullptr);
    assert(rv == 0);
    rv = pthread_cond_init(&tp->not_empty, nullptr);
    assert(rv == 0);

    tp->threads.resize(num_threads);
    for(size_t i = 0; i < num_threads; ++i){
        int rv = pthread_create(&tp->threads[i], nullptr, &worker, tp);
        assert(rv == 0);
    }
}

void thread_pool_queue(TheadPool* tp, void(*f)(void*), void* arg){
    pthread_mutex_lock(&tp->mutex);
    tp->queue.push_back(Work {f, arg});
    pthread_cond_signal(&tp->not_empty);
    pthread_mutex_unlock(&tp->mutex);
}
```

在`init`中，初始化了**锁**和**条件变量**，以及创建了`num_threads`个**线程**。

`thread_pool_queue`中，将任务加入队列，并使用`pthread_cond_signal`**通知**线程。

### server.cpp

原删除逻辑：
```cpp
static void entry_delete(Entry* ent){
    if(ent->type == T_ZSET){
        zset_clear(&ent->zset);
    }
    entry_set_ttl(ent, -1);
    delete ent;
}
```
---

改为：
```cpp
static void entry_del_sync(Entry* ent){
    if(ent->type == T_ZSET){
        zset_clear(&ent->zset);
    }
    delete ent;
}

static void entry_del_func(void* arg){
    entry_del_sync((Entry*)arg);
}

static void entry_del(Entry* ent){
    // unlink it from any data structures
    entry_set_ttl(ent, -1); // remove from the heap data structure
    // run the destructor in a thread pool for large data structures
    size_t set_size = (ent->type == T_ZSET) ? hm_size(&ent->zset.hmap) : 0;
    const size_t k_large_container_size = 1000;
    if(set_size > k_large_container_size){
        thread_pool_queue(&g_data.thread_pool, &entry_del_func, ent);
    }else{
        entry_del_sync(ent); // small; avoid context switches
    }
}
```

我们定义的`static void entry_del_func(void* arg)`也是为了适应我们的`Worker(void* arg)`的函数签名，我们将我们要使用的数据转换为我们需要的就可以。

在这里，我们首先检查数据结构是否为 `ZSET`。如果是，则调用 `hm_size()` 函数来获取 `ZSET` 的大小。然后，我们检查 `ZSET` 的大小是否大于 `k_large_container_size`。如果是，则将数据结构传递给 `thread_pool_queue()` 函数，该函数将数据结构传递给线程池。否则，我们会调用 `entry_del_sync()` 函数，该函数将数据结构传递给 `entry_del_sync()` 函数。


## end

这些就是代码修改的主体，其他的部分改动较小，我们就不再讲述了，鉴于代码放在这里实在太多，我给出我的github地址，大家可以去找`study/dev_6`的目录进行查看

github地址：[https://github.com/AuroBreeze/Implementing-Redis-in-C](https://github.com/AuroBreeze/Implementing-Redis-in-C)






