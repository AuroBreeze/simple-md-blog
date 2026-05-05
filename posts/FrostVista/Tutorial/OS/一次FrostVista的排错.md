---
title: 一次FrostVista的排错
date: 2026-05-03
time: 15:28
archive: FrostVista
categories: [OS, Kernel, C/C++, FrostVista, RISC-V]
summary:
---
# 一次FrostVista的排错

## 前言

那几天在尝试使用`gdb`来追踪OS的运行流程的时候发现，自己的OS无法在`-O0`优化下运行(无优化)，但是可以在`-O2`优化下运行，这就让我感到很奇怪，这是为什么？同一套代码竟然会在不同的优化下产生这么大的差异？

## 优化

### 1. `-O0`：零优化（默认级别）

- **核心目标**：最快的编译速度，最好的调试体验。
    
- **特点**：
    
    - 如果你在编译时不加任何 `-O` 参数，编译器默认使用的就是 `-O0`。
        
    - 编译器几乎不做任何优化。它会将源代码机械、线性地翻译成机器指令。
        
    - 每一个变量都会被完整地保存在内存中，每一次运算都会老老实实地从内存读、计算、再写回内存。
        
- **适用场景**：**日常开发和调试（Debug）**。因为代码没有被重新排序或精简，当你使用 GDB 等调试器单步执行时，当前执行的汇编指令与你的源代码能做到完美的逐行对应，你可以随时查看任何变量的准确值。

### 2. `-O1`：基础优化

- **核心目标**：在不大幅增加编译时间的前提下，减少代码体积并提升运行速度。
    
- **特点**：
    
    - 编译器会尝试做一些简单的优化，例如：去除永远不会执行的死代码（Dead code elimination）、简单的常量折叠（Constant folding）等。
        
    - 它的原则是：只做那些“性价比最高”的优化，既不拖慢编译速度，也不消耗过多内存。
        
- **适用场景**：想要稍微提升一下运行速度，但又不想像 `-O2` 那样等太久编译的场景。
    

### 3. `-O2`：标准/推荐优化

- **核心目标**：在不牺牲过多代码体积的前提下，**最大化代码的执行效率**。
    
- **特点**：
    
    - 包含了 `-O1` 的所有优化，并开启了绝大多数不需要进行“空间换时间”折中的优化。
        
    - 编译器会进行更深入的指令调度、公共子表达式消除、寄存器分配优化等。
        
    - **代码执行顺序可能会被打乱**。编译器可能会把循环里的计算提到循环外，或者把几个操作合并。
        
- **适用场景**：**生产环境（Release）的标准配置**。大多数开源软件和商业软件在发布时都会默认使用 `-O2`，因为它在性能和文件大小之间取得了最佳平衡。在这个级别下调试会非常痛苦，因为变量可能被优化进了寄存器甚至直接消失了，单步调试时代码会来回乱跳。

更多的详细信息请查阅：https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html

## 问题发现

在整个代码运行的过程中，看到整体的OS代码会卡在`kalloc_init`这个过程中，这个过程是将内存收集并存放的过程，这个处理的时间会比较长。

当使用`gdb`调试卡住的时候，就可以使用`Ctrl+C`停下，然后`gdb`会给你当前运行的地址。

通过使用`info reg`查看所有的寄存器

```
ra             0x80008316       0x80008316
sp             0xffffffc08003fe30       0xffffffc08003fe30
gp             0x0      0x0
tp             0x0      0x0
t0             0xffffffc080dce000       -272715948032
t1             0x8003c000       2147729408
t2             0x0      0
fp             0x80035e38       0x80035e38
s1             0x0      0
a0             0xffffffc080dce000       -272715948032
a1             0xffffffc080004a7c       -272730404228
a2             0x80035e38       2147704376
a3             0x0      0
a4             0xf63    3939
a5             0x1000   4096
a6             0x0      0
a7             0x54494d45       1414090053
s2             0x0      0
s3             0x0      0
s4             0x0      0
s5             0x0      0
s6             0x0      0
s7             0x0      0
s8             0x0      0
s9             0x0      0
s10            0x0      0
s11            0x0      0
t3             0x0      0
t4             0x0      0
t5             0x0      0
t6             0x0      0
pc             0x80008290       0x80008290
```

还有`info reg mscratch mtval mepc mcause`
```
(gdb) info reg mscratch mtval mepc mcause
mscratch       0x8000000000000007       -9223372036854775801
mtval          0xffffffc080dce000       -272715948032
mepc           0x80008294       2147517076
mcause         0x7      7
```

通过观察看到`a7 = 0x54494d45`这正是我们使用`sbi_set_timer`来设置下一次`tick`时间的调用，不过很奇怪的是，在这里面`a0`, `a1`, `a2`.....`a5`这里面的数值有很多奇怪的地方，我们的`sbi_set_timer`只是会把这些数值置为`0`，而不是这些看不懂的**魔法数字**，我们也可以看到`sp`目前还指向虚拟地址空间的高地址空间， 但是发现`ra`也存放了返回的地址。

如果我们去查看ra保存的返回地址会发现，是在这个地方

```
  call m_trap

  mv a0, s0
```

`ra`竟然指向`mv a0, s0`，那么意思也就是说，这个时候已经进入开始执行了`m_trap`，但是在`m_trap`还没有处理完的时候就出发了其他的异常。

如果我们查看`mepc`会发现，`mepc`指向的位置是

```
   # Protect kernel timer interrupt context by swapping mscratch and a0
  csrrw a0, mscratch, a0

  # save the register to the memory pointed to by mscratch
  sd ra, 0(a0)
```

指向的是`sd ra, 0(a0)`这个位置，然后整个OS就卡住了

## 为什么会在这里卡住？

我们可以看到，`ra`已经指向了下面的调用`m_trap`的位置，证明，这个`m_trap`确实是调用了，不过，没有处理完就出现了错误，导致整个OS无法运行。

为什么会出现这种情况？为什么`-O2`可以正常运行，但是`-O0`就会出问题，我们将两种编译后的内核反汇编后查看`m_trap`函数

`-O0`版本： 

```asm
void m_trap(uint64 mcause, uint64 mepc, uint64 *regs)
{
ffffffc0800071c6:	7159                	addi	sp,sp,-112
ffffffc0800071c8:	f486                	sd	ra,104(sp)
ffffffc0800071ca:	f0a2                	sd	s0,96(sp)
ffffffc0800071cc:	1880                	addi	s0,sp,112
ffffffc0800071ce:	faa43423          	sd	a0,-88(s0)
ffffffc0800071d2:	fab43023          	sd	a1,-96(s0)
ffffffc0800071d6:	f8c43c23          	sd	a2,-104(s0)
	// Check whether the most significant bit is ahn exception or an
	// interrupt
	int is_interrupt = (mcause >> 63) & 1;
ffffffc0800071da:	fa843783          	ld	a5,-88(s0)
ffffffc0800071de:	93fd                	srli	a5,a5,0x3f
ffffffc0800071e0:	fef42623          	sw	a5,-20(s0)

...
```

`-O2`版本：

```asm
ffffffc080003fa6 <m_trap>:
{
	// Check whether the most significant bit is ahn exception or an
	// interrupt
	int is_interrupt = (mcause >> 63) & 1;

	uint64 code = mcause & ((1ULL << 63) - 1);
ffffffc080003fa6:	577d                	li	a4,-1
ffffffc080003fa8:	00175793          	srli	a5,a4,0x1
ffffffc080003fac:	8fe9                	and	a5,a5,a0
	int is_interrupt = (mcause >> 63) & 1;
ffffffc080003fae:	03f55693          	srli	a3,a0,0x3f

	// WARNING: Ban kprintf and panic
	// Because the current SP is not in a valid state, the SP has already
	// been saved, and the current SP is in an undefined state.
	if (is_interrupt) {
ffffffc080003fb2:	00054663          	bltz	a0,ffffffc080003fbe <m_trap+0x18>
			w_mip(r_mip() | MIP_STIP); // Key: Set STIP to allow S
						   // to receive scause = 5
		}
...
```

在这里可以看到，`-O0`版本的代码，将会调整`sp`将参数存放到栈上，但是，在M态下，MMU是默认禁用的，我们在上面可以看到我们的`sp`指针指向虚拟高地址，这个地址根本不存在在物理地址上，所以当调整`sp`，准备访问栈的时候就会报错。

而在`-O2`优化的版本下，所有的数据都存在在寄存器上，不依赖栈，所以就没有使用`sp`
指针从而避免了这个错误。

这也就是导致两种不同的优化方案而导致的不同。

## 其他问题

### 为什么将下次时间设置的够远就可以正常运行？

如果设置的够远，OS也仅仅是在这段时间完成任务后，再次遇到这个问题，然后卡住，`-O0`的情况下，只要使用了`sbi`的调用，那么这个问题是必然会出现的，只要`tick`发生了，那就一定会因为`sp`的问题而卡住

### 为什么第一次设置sbi调用就没有问题？

这个整个问题的核心就在于`sp`的**指向位置**，在第一次调用`sbi_set_timer`的时候，这个时候是在执行`timerinit`函数，还没有通过`switch_to_high_address`将`sp`拉到虚拟高地址。

所以，这个时候`sp`处在虚拟低地址，也就是`VA=PA`的时候，这个时候传入的`sp`就是可以直接在物理地址使用，所以这个问题就没有触发。

## 如何解决这个问题？

要解决这个也很简单，因为`-O0`优化的版本进入`m_trap`的第一件事情就是调整`sp`，这个时候`sp`是虚拟高地址，那我们就可以在进入`m_trap`之前调整`sp`指针，让`sp`指向一个专门为M态服务的栈空间。

最好的方法就是在`start.S`中划分一段空间作为栈空间

```asm
    .section .bss.m_trap_stack
    .align 12
    .global m_trap_stack
m_trap_stack:
    .space 0x4000  # 16KB
    
    .global m_trap_stack_top
m_trap_stack_top:
```

在进入`m_trap`的时候调整`sp`

```asm
  csrr t0, mhartid         # Get current CPU ID
  slli t0, t0, 12          # Multiply hartid by 4096 (left shift by 12)
  la sp, m_trap_stack_top
  sub sp, sp, t0           # Adjust stack pointer for the specific CPU
```

这样就可以了。

### 疑问

为什么不在内核代码中，建立一个大的空数组作为栈空间，或者为什么不在`ld`文件中建立一个空间。

首先在`ld`文件中建立这样的一个空间，和在`start.S`这里是一样的。

在内核代码中建立这样的空间，首先是麻烦，建立数组后，还有再把指针指向数组的末尾，其次，是内存对齐的问题，栈`SP`指针要求16字节对齐，这样的话，还需要再为了数组写一个对齐，这个有些不够优雅，而在`start.S`中用个`.align 4`就可以了。