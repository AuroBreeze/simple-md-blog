---
title: spinlock和sleeplock锁的使用极其注意事项
date: 2026-05-03
time: 15:28
archive: FrostVista
categories: [OS, Kernel, C/C++, FrostVista, RISC-V]
summary:
---

# 锁的使用

> 本文默认读者有对应的编程经验，过多细节不再赘述

在写`FrostVistaOS`的时候，在 OS 初始化早期，由于调度器尚未启动、进程尚未建立，会导致依赖进程上下文的睡眠锁无法正常工作。所以，我打算还是专门写一篇博客用来讲解锁的使用，因为我的锁的编写借鉴了`xv6`的代码，所以，理论上与`xv6`的锁的使用是通用的。

---

## `spinlock`

```c
struct spinlock {
	uint locked;
	char *name;
	struct cpu *cpu;
};
```

### `push_off`和`pop_off`

```c
void push_off(void)
{
	int old = intr_get();
	intr_off();

	struct cpu *c = get_cpu();
	if (c->noff == 0) {
		c->intena = old;
	}
	c->noff++;
}

void pop_off(void)
{
	if (intr_get()) {
		// By default, this is paired with `push_off`, which disables
		// interrupts; therefore, interrupts should still be disabled
		// here.
		panic("pop_off: interrupt enabled\n");
	}
	struct cpu *c = get_cpu();
	if (c->noff < 1) {
		panic("pop_off");
	}
	c->noff--;
	if (c->noff == 0 && c->intena) {
		intr_on();
	}
}
```

> `push_off`和`pop_off`是`cpu`级的控制，请牢记，下面将进行讲解

```c
// Per-CPU state.
struct cpu {
	int noff;		// Record nesting depth
	int intena; // Record the interrupt status before the first interrupt is
		    // disabled
};
```

我们当然很清楚的知道，锁是用来保护临界区的资源的，但是有没有想过另一种情况，当我们的在运行内核代码的时候，正好运行在临界区中，此时正持有锁，然后触发异常了，这种情况下，进入中断或异常处理程序，要是需要在中断或异常处理程序中，还需要获取锁，这个时候，在获取锁的时候，**又会关中断**，当处理完这个程序，释放掉中断或异常处理程序中的锁的时候，没有嵌套计数，就会**开中断**，导致返回到临界区的时候，可能会被中断打断，无法保护临界区。

当然，你也能会有些问题？

#### 这两个申请的锁又不是同一个自旋锁，为什么要记录嵌套层数和中断关闭情况？

我们在上面提到了，`spinlock`是`cpu`级的锁控制，`spinlock`依赖记录当前的`cpu`的中断情况`intena`和嵌套情况`noff`，所以只要是在这个`cpu`上运行的程序，`spinlock`都会将其记录到`cpu`的结构体上，这样就保证了同一个`cpu`上，可以正常的处理中断的开启和关闭情况，以及锁的嵌套情况(锁一定不是同一个锁，那样就重入了，xv6不支持锁的重入)。

#### 什么时候应该使用这两个函数？

我们可以看到`push_off`和`pop_off`的功能并不是很复杂，获取当前的中断情况，关中断，设置CPU的锁的情况。

这个两个函数本质是在**需要临时禁用当前 CPU 的中断，并且该禁用操作可能发生嵌套** 的时候使用。

所以，这里就有一个本质，那就是为了**恢复外部的中断情况，而不是直接开中断**，就像是`holding`检测是否持有锁，先通过关中断防止数据被意外的修改，在通过`pop_off`恢复外部的中断。

`push_off`和`pop_off`可以安全地关闭和开启中断，比直接使用`intr_off`和`intr_on`关闭和开启中断更加安全和方便。

### `sleep`和`wakeup`
```c
void sleep(void *chan, struct spinlock *lk)
{

	struct Process *p = get_proc();

	if (lk != &p->lock) {
		acquire(&p->lock);
		release(lk);
	}

	p->chan = chan;
	p->state = SLEEPING;

	sched();

	p->chan = 0;

	if (lk != &p->lock) {
		release(&p->lock);
		acquire(lk);
	}
}

void wakeup(void *chan)
{
	struct Process *p;
	extern struct Process proc[64];

	for (int i = 0; i < 64; i++) {
		p = &proc[i];
		acquire(&p->lock);
		if (p != get_proc() && p->chan == chan &&
		    p->state == SLEEPING) {
			p->state = RUNNABLE;
		}
		release(&p->lock);
	}
}
```

在`spinlock`中的睡眠是需要依赖进程和`cpu`的，进程挂靠在`cpu`下面，所以这也就导致了，我遇到的问题，在OS启动之初，要是想使用bread读取文件系统，并加载文件，那就需要进程的运行，因为`sleep`是需要切换进程的，但是在初始化之初，没有进程可以切换，也就无法运行。

`sleep`是为了实现睡眠的功能，等待某个信号量，将信号放到当前进程的`chan`中，并使其睡眠，等待唤醒。

唤醒的机制也很简单，找对应的进程即可，并将其唤醒。

## `sleeplock`

```c
struct sleeplock {
	int locked;
	struct spinlock lock;
	// struct spinlock {
	// 	uint locked;
	// 	char *name;
	// 	struct cpu *cpu;
	// };

	char *name;
	int pid;
};
```

### 如何理解加了一层嵌套的`sleeplock`

我们在上面可以看到`sleeplock`的具体实现，他是对`spinlock`锁的一个封装。

`sleeplock`的使用和`spinlock`的使用的根本区别在什么地方？

```c
void acquire(struct spinlock *lk)
{
	push_off();

	if (holding(lk)) {
		panic("acquire: already holding lock");
	}
	while (__sync_lock_test_and_set(&lk->locked, 1) != 0)
		;
	// Prevent reordering from causing data to be accessed before the lock
	// is acquired
	__sync_synchronize();

	lk->cpu = get_cpu();
}

void acquiresleep(struct sleeplock *lk)
{
	acquire(&lk->lock);
	while (lk->locked) {
		sleep(lk, &lk->lock);
	}
	lk->locked = 1;
	lk->pid = get_proc()->pid;
	release(&lk->lock);
}
void releasesleep(struct sleeplock *lk)
{
	acquire(&lk->lock);
	lk->locked = 0;
	lk->pid = 0;
	wakeup(lk);
	release(&lk->lock);
}
```

首先，`acquire`会保证`sleeplock`的互斥，只能同时持有一个这样的锁。

其次是，通过使用

```c
	while (lk->locked) {
		sleep(lk, &lk->lock);
	}
```

来实现睡眠等待，当此处的锁已经被获取后，进行睡眠。

所以其他进程再次想要获取这个锁的时候，内部的`&lk->lock`即`spinlock`就已经被释放了，所以还可以正常的申请，不过进入后还是会因为已经被其他进程获取，自己进入睡眠。

这样也就可以保证，`releasesleep`可以正常的获取内部的锁，并释放，然后通知所有正在等待的锁。

## 锁与`proc`,`cpu`的关系

在这里实现的`sleeplock`是基于`spinlock`实现的。

在`spinlock`的实现中，

`push_off`和`pop_off`是依赖获取当前的`cpu`进行保存，中断情况和嵌套情况。因为`CPU`必定会在运转，所以`push_off`和`pop_off`，以及由此衍生出的`holding`, `acquire`, `release`都是可以正常的使用的。

而实现的`sleep`，需要`CPU`下挂载的进程(`get_proc`基于当前的`cpu`结构体获取他下面挂载的`proc`)，因为还依赖于`sched`，所以`sched`所依赖的`cpu`记录的上下文`context`，和当前进程`proc`的上下文`context`，所以这整体就需要依赖调度器的运转。

所以由此衍生的`acquiresleep`也就需要调度器的运转。

但是`wakeup`因为是遍历进程数组所实现的，所以并不需要依赖其他的东西。`releasesleep`同理。

## 额外的内容

所以，回到开头，在OS初始化初期，系统环境尚未完全建立，我应该怎么解决要初始化文件系统，但是需要依赖调度器及环境的问题？

或许`xv6`给了一个很好的答案，使用非常简单的编译好的`.S`文件，写到运行环境里面作为第一个运行的程序，在这个程序中，实现文件系统的初始化等。

`xv6`的实现思路就是将`SYS_exec`的调用编写成一个数组`initcode`，然后修改`context.ra`，让这个`ra`指向我们其他初始化的函数，将我们那些需要完整的初始化完成，最后调用`usertrapret`返回`U`模式，实现完整的初始化流程