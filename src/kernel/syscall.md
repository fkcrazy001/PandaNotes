# syscall

在linux上的各种 syscall 的机制研究，如果复杂的syscall，会另开专题来研究。

## PTRACE 系统调用
<https://man7.org/linux/man-pages/man2/ptrace.2.html>

```c
long ptrace(enum __ptrace_request op, pid_t pid,
                   void *addr, void *data);
```
每一个 op 都有不同的意思，所以对每一个op进行查看。

tracee: 被trace的对象，永远是一个线程。

tracer: trace 发起者。

### PTRACE_TRACEME

文档上是这么说的: tracee(calling thread) 在 fork 之后可以执行这个系统调用，这样会置位可被TRACE的标志。还特意提到了，这个不会中断子进程的执行。

这和网上很多文档说的不一致，分析一下源码 (linux v6.19.6)。
```c
kernel/ptrace.c: SYSCALL_DEFINE4(ptrace, long, request, long, pid, unsigned long, addr, unsigned long, data)
                    => ptrace_traceme(void): current->ptrace = PT_PTRACED; // 这里就是设置了这个标志

// 尝试查看哪些地方用了 这个 flag，最终找到这样一条调用链
sys_execv =>  fs/exec.c: do_execveat_common => bprm_execve => exec_binprm 
                                                                => ptrace_event(PTRACE_EVENT_EXEC) {
                                                                    if ((current->ptrace & (PT_PTRACED|PT_SEIZED)) == PT_PTRACED)
			                                                            send_sig(SIGTRAP, current, 0);
                                                                }                                                        
// 系统调用返回到用户态之前，会去检查信号，在被 TRACE 情况下， 所有信号都会导致子进程被挂起(除了sig kill)。
// 代码在 signal.c: get_signal 函数中。

```

后续在文档中发现，ptrace有一个名为 PTRACE_O_TRACEEXEC 的option，新的gdb都应该用这个option。
所以网上很多的文档反而是描述了老的行为。man文档中推荐的才是较为新的且好的操作。

```txt
If the PTRACE_O_TRACEEXEC option is not in effect, all successful
calls to execve(2) by the traced process will cause it to be sent
a SIGTRAP signal, giving the parent a chance to gain control
before the new program begins execution.
```

### PTRACE_CONT

```txt
Restart the stopped tracee process.  If data is nonzero, it
is interpreted as the number of a signal to be delivered to
the tracee; otherwise, no signal is delivered.  Thus, for
example, the tracer can control whether a signal sent to
the tracee is delivered or not.  (addr is ignored.)
```

紧接着上面的子进程被挂起之后，发送 cont 会让子进程被唤醒， 
并且唤醒理由放在 exit_code 中(`ptrace_resume` 函数中)，会被翻译为signal继续去执行子进程的信号处理流程。

### PTRACE_SINGLESTEP

单步执行下一条指令。对于 `si` 这种“指令级步进”，底层就是循环：
1. `ptrace(PTRACE_SINGLESTEP, pid, 0, sig)`
2. `waitpid(pid, ...)` 等待 tracee 因为单步陷入而停止（通常是 `SIGTRAP`）

内核侧主要路径（不同版本/架构细节会有差异）：
```c
kernel/ptrace.c: SYSCALL_DEFINE4(ptrace, ...) => ptrace_request(...)
  case PTRACE_SINGLESTEP:
    ptrace_resume(child, request, data);
      -> user_enable_single_step(child);
      -> wake_up_state(child, __TASK_TRACED/ TASK_RUNNING ...);
```
`user_enable_single_step` 是架构相关的入口：x86_64 通常依赖 TF/trap flag，arm64 走对应的单步机制。

### PTRACE_GETREGS / PTRACE_SETREGS

读写“通用寄存器快照”。在 `gdb` 中对应 `register read/write` 子命令。

用户态调用模型：
1. tracee 停在 traced-stop（一般来自断点/单步/信号）
2. tracer `PTRACE_GETREGS` 拉取寄存器结构体
3. 如需修改，改完后 `PTRACE_SETREGS` 写回
4. `PTRACE_CONT`/`PTRACE_SINGLESTEP` 继续运行

内核侧主要路径：
```c
kernel/ptrace.c: SYSCALL_DEFINE4(ptrace, ...) => ptrace_request(...)
  case PTRACE_GETREGS:
  case PTRACE_SETREGS:
    arch_ptrace(request, child, addr, data);
```
寄存器格式是架构相关的：x86_64 是 `user_regs_struct`；arm64 更推荐用 `GETREGSET/SETREGSET`（见下）。

### PTRACE_GETREGSET / PTRACE_SETREGSET

更通用/可扩展的寄存器访问接口，配合 `addr = (void*)NT_*` 指定寄存器集类型，`data` 指向 `struct iovec`。
在 `gdb` 里常见的用法：
- `NT_PRSTATUS`：通用寄存器（含 PC/SP 等）
- `NT_ARM_HW_BREAK`：arm64 硬件断点寄存器集

用户态调用模型：
1. 准备 `iovec { .iov_base = buf, .iov_len = len }`
2. `ptrace(PTRACE_GETREGSET, pid, NT_PRSTATUS, &iov)` 读取
3. 修改 `buf` 后 `ptrace(PTRACE_SETREGSET, pid, NT_PRSTATUS, &iov)` 写回

内核侧主要路径（抽象层次）：
```c
kernel/ptrace.c: SYSCALL_DEFINE4(ptrace, ...) => ptrace_request(...)
  case PTRACE_GETREGSET:
  case PTRACE_SETREGSET:
    ptrace_regset(child, request, addr /* NT_* */, data /* iovec */);
      -> regset = task_user_regset_view(child)->regsets[...]
      -> regset->get()/set()
```

### PTRACE_PEEKDATA / PTRACE_POKEDATA

按“一个 machine word”读写 tracee 的虚拟内存，是软件断点（写 `int3/0xCC`）和 `memory read/write` 的基础。

用户态调用模型：
1. `word = ptrace(PTRACE_PEEKDATA, pid, addr, 0)` 读取
2. 修改目标字节（例如把最低字节改成 `0xCC`）
3. `ptrace(PTRACE_POKEDATA, pid, addr, word)` 写回

内核侧主要路径（抽象层次）：
```c
kernel/ptrace.c: SYSCALL_DEFINE4(ptrace, ...) => ptrace_request(...)
  case PTRACE_PEEKDATA:
  case PTRACE_POKEDATA:
    ptrace_peekdata/ptrace_pokedata(...)
      -> access_process_vm(child, addr, buf, len, flags);
```
常见现象：
- 地址无效/不可访问时，容易在用户态看到 `EIO`
- 软件断点触发时，x86_64 的 `RIP` 会停在 “断点地址 + 1”，所以调试器一般要做 `pc-1` 校正

### PTRACE_POKEUSER

写 tracee 的 “user area” 中的字段（不同架构含义不同）。在 `gdb` 的硬件断点实现里，x86_64 常用它来写 DR0-DR3/DR7 这样的调试寄存器映射。

内核侧主要路径（抽象层次）：
```c
kernel/ptrace.c: SYSCALL_DEFINE4(ptrace, ...) => ptrace_request(...)
  case PTRACE_POKEUSER:
    arch_ptrace(request, child, addr, data);
```
是否允许写、写到哪里、如何落到真实硬件寄存器，基本都在架构代码里做校验与转换。