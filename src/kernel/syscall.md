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

