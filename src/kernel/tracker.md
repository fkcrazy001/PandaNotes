# kernel_tracker

介绍一个跟踪内核行为的工具集。

## overview

项目组织方式参照这个仓库 <https://github.com/libbpf/libbpf-bootstrap> 中的 example 目录。

总体上分为两部分，ebpf程序 + 用户态工具

- ebpf 程序进行典型的如 kprobe 注册并将perf数据写入 map 中，用户态负责读取
- 用户态 程序将 ebpf 程序进行加载，然后从map中读取数据（bss，.data在bpf程序的实现中也是一个array map）

## 用户态程序

### bpf skeleton

可以通过这个工具，将所有的字节码和helper函数都放在一个头文件中。
这样用户态只需要 include 这个文件，就可以在运行时通过 bpf helper 将 字节码 注入到内核中。

```Makefile
# Generate BPF skeletons
$(OUTPUT)/%.skel.h: $(OUTPUT)/%.bpf.o | $(OUTPUT)
	$(call msg,GEN-SKEL,$@)
	$(Q)$(BPFTOOL) gen skeleton $< > $@

```

###  mode template

kernel 有 net, fs, mem, sched, irq, kvm等几个子系统。

在很多时候都要选择一个子系统进行观察。

在加载的时候，如果说一股脑把所有的 bpf 程序都加载进去，那对内核就是一种负担，而且没有必要。于是通过 mode 的方式来进行控制，在用户态启动的时候，需要选择一个模块，然后 mode 中有 filter 的方式，抽象为如下：

```c
struct mode_template {
	const char *name;
	const char *description;
	struct argp argp;
	void (*init)(void);
	bool (*check)(void);
	void (*header)(void);
	void (*run)(void);
	void (*dump)(void);
    // says if load map(if is map), program
	bool (*load)(bool is_map, const char * name);
};
```
map 和 program 通过 bpf_map__set_autocreate/bpf_program__set_autoload 来控制。

### mode load

初始化程序状态，然后通过 mode->load 来判断要不要load map/program。 

### TRICK: proxy read

用户态没法直接访问kernel里面的数据，可以设置一些proxy kprobe。 然后在用户态中触发它，从而可以把结果写进和用户态共享的bss段中。

### bpf Attach

attach all objects to kernel.

### Run loop

run loop 就是收集信息，然后展示出来。

目前有两种收集方式：

- mode->run()
- ringbuf map callback

## ebpf

### irq 子系统

这里可以观测一下 irq 处理的时间，以及查看某个进程（组）是不是经常被中断打断。

- hard irq
  - tp/irq/irq_handler_entry: hard irq
  - tp/irq/irq_handler_exit

- soft irq
  - tp/irq/softirq_entry
  - tp/irq/softirq_exit

### syscall 子系统

观测某些 syscall 传入参数和结果。

- tp/syscalls/sys_exit_*
- tp/syscalls/sys_enter_*

### mm 子系统

对于观测目的，就需要经常看一下某个进程 PAGE FAULT 特别多？ 如果特别多的话，就考虑是不是内存压力比较大/申请内存太多？

- kprobe/handle_mm_fault
- kretprobe/handle_mm_fault"

### net 子系统

- kprobe/kfree_skb_reason: 这个就很全了，所有的skb 被free（也就是说，发生了丢包å）都会走到这儿。由此可以观测当前系统丢包原因是什么
- tp/net/netif_receive_skb： 这个是很前期的 skb receive 流程（可以认为软中断之后就是它了），所以在这儿可以做一些统计之类的。

### kvm 子系统

- tp/kvm/kvm_entry && tp/kvm/kvm_exit： 可以根据这个记录一下 kvm 退出（为什么退出？）和进入。

### fs 子系统

- kprobe/filemap_read: 当文件被read时，会触发这个 kprobe 

### 

## rust 重构版本
