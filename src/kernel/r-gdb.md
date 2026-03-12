# rgdb

A gdb write in Rust,  Inspired By https://tartanllama.xyz/posts/writing-a-linux-debugger/setup/ .

## GOALS: 

从文章中继承，后续看情况会不会新增

- Launch, halt, and continue execution
- Set breakpoints on
  - Memory addresses
  - Source code lines
  - Function entry
- Read and write registers and memory
- Single stepping
  - si
  - s
  - finish
  - n
- Print current source location
- Print backtrace
- Print values of simple variables

and more todo:
- Remote debugging
- Shared library and dynamic loading support
- Expression evaluation
- Multi-threaded debugging support


## SETUP

文章中说需要解析一下命令行参数和DWARF调试信息，原文中使用了  Linenoise 和 libelfin。 
Rust中的话就用 clap 和 gimli 好了，都是主流库，而且在MAC上也有支持，所以进行这个开发会更方便。

- 启动: 先不支持 attach 到 pid

通过下面这种方式启动，那么启动阶段要先创建一下子进程，在子进程中来通过 ptrace 系统调用来让自己停下来先，等着父进程来调试自己。

`rgdb $PROCESS <$ARGS>`

通过封装好的 command::new 这种函数，直接来启动子进程会导致子进程可能退出了，而父进程都没有机会去控制它。

所以这里不能用这个函数，必须使用 nix 库的函数，手动 fork 和 execv 子进程, 然后在这中间插入 SIGTRAP 信号，让子进程停下来先。
```rust
    // let sub_process = Command::new(prog.program).args(prog.args).spawn()?;
    let pid = match unsafe { fork()? } {
        ForkResult::Child => {
            ptrace::traceme()?;
            // traceme on some platform, like macos, doesn't send a signal
            unsafe { raise(SIGTRAP) };
            execv(&pn, &args)?;
            unreachable!();
        }
        ForkResult::Parent { child } => child,
    };
```

- 设计 debugger

设计一个 debugger， 这个 debugger 首先要能够

1. 接收用户输入
2. 操作子进程

对于处理用户输入，gdb有搜索和自动补全的功能，rust有 rustyline 可以很方便的解决这个问题。

然后需要把这些输入一个个翻译为对应的subcommand, 然后执行对应的动作。

## SUBCOMMAND 实现

### continue

很简单，就是通过 ptrace::cont 来通知内核(可以带上一个信号)。

关于系统调用具体干了什么，可以查看 [syscall专栏](syscall.md)。

### break point

有软件 break point 和 硬件 break point。

- 软件 break point

想法是这样的： 当break一个代码地址时，把这儿的指令改掉，比如说 改成 `int 3`(x86-64)上，这样执行到这儿就会陷入中断，linux 会执行 SIGTRAP 的逻辑。 这样父进程就能收到消息了。


- 硬件 break point