# rgdb

A gdb write in Rust,  Inspired By https://tartanllama.xyz/posts/writing-a-linux-debugger/setup/ .

my project: <https://github.com/fkcrazy001/rgdb.git>s

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

硬件断点利用处理器提供的调试寄存器来实现，不需要修改目标程序的指令。这在调试只读内存（如 ROM）或者设置数据断点（Watchpoint）时非常有用。

实现思路：
1. **x86-64**: 使用 `DR0`-`DR3` 调试寄存器存储断点地址，并通过 `DR7` 调试控制寄存器来启用它们。在 Linux 中，可以通过 `ptrace(PTRACE_POKEUSER, ...)` 来设置这些寄存器，偏移量通常由 `libc` 或 `nix` 提供。
2. **AArch64**: 使用 `DBGBVR<n>_EL1` (Breakpoint Value Registers) 和 `DBGBCR<n>_EL1` (Breakpoint Control Registers)。在 Linux 中，通常通过 `ptrace(PTRACE_SETREGSET, ...)` 配合 `NT_ARM_HW_BREAK` 寄存器集类型来配置。

限制：
- 硬件断点的数量有限（x86 通常为 4 个，ARM 通常为 2-16 个）。
- 设置硬件断点不涉及内存修改，因此不会破坏指令缓存。

### register

为了观察和修改程序的状态，我们需要读写 CPU 寄存器的能力。

在 Linux 上，我们可以通过 `ptrace(PTRACE_GETREGS, ...)` 一次性获取所有的通用寄存器。
- 对于 **x86_64**，这会返回 `user_regs_struct`，包含了 `rax`, `rbx`, `rip`, `rsp` 等。
- 对于 **AArch64**，通常使用 `PTRACE_GETREGSET` 并指定 `NT_PRSTATUS` 来获取寄存器信息。

一旦获取了寄存器结构体，我们就可以：
1. **read**: 打印指定寄存器的值，或者打印全部寄存器。
2. **write**: 修改指定寄存器的值，然后通过 `PTRACE_SETREGS` 写回。

### memory

除了寄存器，观察进程内存也至关重要。

1. **read**: 使用 `ptrace(PTRACE_PEEKDATA, ...)` 读取指定地址的内存。由于这个系统调用每次只读取一个字（word），我们需要循环调用来读取大块内存。
2. **write**: 使用 `ptrace(PTRACE_POKEDATA, ...)` 向指定地址写入数据。这同样是按字操作的。在写入断点（软件断点）时，我们实际上就是在进行内存写入。

## ELF and DWARF (Step 4)

为了让调试器理解源代码，我们需要解析二进制文件中的调试信息。

### ELF 解析
使用 `object` 库来解析 ELF 文件结构。主要用于查找符号表（Symbol Table）以及定位 DWARF 相关的 Section（如 `.debug_info`, `.debug_line`）。

### DWARF 解析
使用 `gimli` 库来处理 DWARF 格式。
1. **行表 (Line Table)**: 用于机器码地址与源代码行号之间的映射。
2. **编译单元 (Compilation Units)**: 调试信息的顶层结构。
3. **加载地址处理**: 对于 PIE (Position Independent Executables)，调试信息中的地址是相对偏移。我们需要通过 `/proc/<pid>/maps` 获取进程的加载基址，并将绝对地址转换为相对偏移后再进行 DWARF 查找。

### 调试信息查找路径
为了与 GDB 行为一致，`rgdb` 会按以下顺序查找调试信息：
1. 二进制文件自身的 Section。
2. 同目录下的 `.debug` 文件。
3. 系统全局调试路径 `/usr/lib/debug/`。

## Source and Signals (Step 5)

增强了信号处理、源代码显示，以及 REPL 的退出体验，提升调试“可用性”。

### 信号处理
在 `handle_wait_status` 中，增加了对进程状态的全面处理：
1. **Stopped**: 处理由信号（如 `SIGTRAP`, `SIGSEGV` 等）引起的停止。
2. **Exited**: 捕获进程正常退出的状态及退出码。
3. **Signaled**: 捕获进程被信号终止的情况。

当捕获到 `Exited/Signaled` 时，会标记 inferior 已退出，REPL 会自动结束（不需要手动 `q`）。

### 源码上下文显示
当程序在带有调试信息的地址停止时，`rgdb` 会自动：
1. **定位源码**: 通过 DWARF 信息找到对应的文件和行号。
2. **显示代码**: 读取源码文件并打印当前行及其前后各 3 行的上下文。
3. **高亮当前行**: 使用 `=>` 标记当前正在执行的行。

### 断点位置的地址校正
在 x86_64 上，执行到 `int3`（`0xCC`）后 CPU 会把 `RIP` 停在 “断点地址 + 1”。因此在展示源码和做行号映射时，`rgdb` 会对 `SIGTRAP` 做 `pc-1` 的校正，从而把“当前停止位置”显示成正确的源码行。

### 历史记录的健壮性
`rustyline` 会尝试读取/写入 `.rgdb_history`。在 `sudo` 调试、或文件权限变化的情况下，保存历史记录可能失败。为了避免退出时因为历史记录保存失败导致程序报错，保存失败会被忽略。

## Source-Level Stepping (Step 6)

实现了基于源代码的单步执行命令。

### 指令级单步 (`si`)
使用 `ptrace(PTRACE_SINGLESTEP, ...)` 执行下一条机器码指令。如果当前位于断点位置，会自动处理断点的跳过和恢复。

### 源码级单步 (`s`)
执行代码直到源代码的行号发生变化。底层通过循环执行 `si` 并比对 DWARF 行表信息实现。如果进入了子函数且子函数有调试信息，会停在子函数的第一行。

### 源码级跳过 (`n`)
`rgdb` 的 `n` 不再简单地“循环 single-step 直到行号变化”。实际实现采用了更接近 gdb 的策略：**用 DWARF 行表找出“下一行语句”的地址，然后设置临时断点并 continue 过去**。

核心流程：
1. **确定当前行**：从当前 `PC` 映射到 `SourceLocation(file,line,column)`。
2. **查找下一行地址**：遍历 `.debug_line` 的行表，寻找满足条件的下一条 row：
   - 与当前文件匹配（支持 basename 末尾匹配）
   - `row.is_stmt()` 为真（过滤掉非语句点）
   - `row.line > current_line` 且 `row.address > current_pc_offset`
3. **设置临时断点**：在下一行地址插入断点（temporary breakpoint）。
4. **continue 执行**：进程运行到临时断点时停止。
5. **清理临时断点**：跨过断点时自动恢复原指令，并从断点表中移除该断点。

当当前行已经是函数最后一行、行表找不到“下一行”时，`n` 会直接 `continue` 直到进程退出，从而避免“跳进运行时/库代码后停在奇怪地址”的体验。

### 退出当前函数 (`finish`)
继续执行直到当前函数返回。
- **x86_64**: 通过读取 `RSP` 指向的栈顶获取返回地址，并设置临时断点。
- **AArch64**: 通过读取 `LR` (X30) 寄存器获取返回地址，并设置临时断点。

## Source-Level Breakpoints (Step 7)

支持通过源代码层面的标识符设置断点。

### 地址断点
支持原始的十六进制地址断点。
```text
gdb> break 0x40114e
```

### 函数名断点
支持通过函数名称设置断点。实现上会遍历 DWARF 的 `DW_TAG_subprogram`，找到匹配 `DW_AT_name` 的条目，并读取 `DW_AT_low_pc` 作为函数入口。

为了让断点更“像 gdb”，`rgdb` 不一定把断点打在函数序言（prologue）的位置，而是尽量定位到函数体内第一条可执行语句（first statement）：
1. 先取到 `low_pc` 对应的源码行；
2. 再用行表找到该行之后的下一条语句地址；
3. 把断点打在那条语句的地址上（这样 `b main; c` 更容易停在 `int i = 0;` 而不是 `{`）。

```text
gdb> break main
```

### 文件:行号断点
支持通过 `文件名:行号` 的方式设置断点。实现上遍历 DWARF 行表（`.debug_line`）找到匹配行号且文件名匹配的 row，并把 row.address 转换为运行时地址。

```text
gdb> break main.c:12
```

### PIE/非 PIE 的地址换算
`rgdb` 会检测 ELF 类型：PIE（ET_DYN）需要根据 `/proc/<pid>/maps` 的加载基址做地址重定位；非 PIE（ET_EXEC）则使用绝对地址（不额外加基址），避免出现 `b main` 计算出错误地址导致 `ptrace::read` 返回 `EIO` 的问题。

## Stack Unwinding (Step 8)

实现了函数调用栈的回溯功能 (`backtrace/bt`)。

### 帧指针回溯（Frame Pointer Unwinding）
当前实现采用基于帧指针链的简单回溯算法（对使用 `-fno-omit-frame-pointer` 编译的程序最可靠）：
1. **获取当前状态**：读取 `PC` 与帧指针 `RBP`（x86_64）或 `X29`（AArch64）。
2. **函数名解析**：优先通过 DWARF 的 `DW_TAG_subprogram` 做地址范围匹配，打印 `func+0xoffset`；如果 DWARF 不可用则尽量用符号表兜底（仅限当前可执行文件）。
3. **源码行映射**：用行表把 `PC` 映射回 `file:line:column`。
4. **沿 FP 链向上走**：
   - x86_64：`[RBP]` 是上一帧 `RBP`，`[RBP+8]` 是返回地址
   - AArch64：`[FP]` 是上一帧 `FP`，`[FP+8]` 是返回地址（对应 LR 保存位）
5. **终止条件**：帧指针为 0、读取失败或超过最大深度（50）。

另外，为了避免在断点处把 `PC` 打印成 “地址+1”，回溯的第 0 帧会在检测到当前停在断点后做一次 `pc-1` 的修正。

## Handling Variables (Step 9)

实现了读取并打印源代码变量值的功能。

### 变量查找
1. **获取当前作用域**: 根据当前的 `PC` 指针，在 DWARF 信息中定位当前的子程序（Subprogram）。
2. **名称匹配**: 在当前子程序的作用域内，查找匹配给定名称的 `DW_TAG_variable` 或 `DW_TAG_formal_parameter` 标签。
3. **位置评估**: 解析变量的 `DW_AT_location` 属性。

### 变量位置求值（简化版）
为了保证稳定性，`rgdb` 目前实现了对常见 location expression 的直接求值（而不是尝试完整覆盖所有 DWARF 表达式）：
1. **DW_OP_fbreg（栈上变量）**：会读取 `DW_AT_frame_base`（本项目里常见的是 `DW_OP_call_frame_cfa`），并用简化的 CFA 计算来定位变量地址，然后 `ptrace` 读取内存。
2. **寄存器变量**：如果 location 表示寄存器，会直接读取对应寄存器值。
3. **绝对地址**：如果 location 给出地址，会直接读取该地址处的内存。

### 类型大小推导
为了避免把栈上相邻变量“读进来”，`rgdb` 会读取 `DW_AT_type`，沿着类型引用链查找 `DW_AT_byte_size`，从而确定读取的字节数（例如 `int` 读取 4 字节）。

```text
gdb> p i
0x0
```

## Advanced Topics (Step 10)

本阶段探索了一些高级调试技术，主要包括对符号表（Symbol Table）的支持。

### 符号表支持 (ELF Symbols)
即使二进制文件被剥离（stripped）了 DWARF 调试信息，或者在调试某些系统库时，我们仍然可以通过 ELF 符号表来设置断点。
1. **加载符号**: 在初始化时使用 `object` 库解析 ELF 的 `.symtab` 或 `.dynsym` 段。
2. **符号查找**: 实现了 `lookup_symbol`，允许用户通过导出的符号名称进行断点设置。
3. **加载地址适配**: 与 DWARF 映射一致，符号地址也会根据进程的加载基址（Load Address）进行动态偏移计算。

目前符号表解析仅覆盖**当前可执行文件**。共享库（例如 libc）符号解析属于后续增强项（需要遍历 `/proc/<pid>/maps` 并解析每个映射的 ELF）。

```text
gdb> break malloc
# 即使没有源码，也能在库函数入口设置断点
```
