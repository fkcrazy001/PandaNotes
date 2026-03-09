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

通过下面这种方式启动，那么启动阶段要先创建一下子进程，在子进程中来通过 ptrace 系统调用来控制子进程。

`rgdb $PROCESS <$ARGS>`

