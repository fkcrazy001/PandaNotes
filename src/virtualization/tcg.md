# QEMU TCG 研究

想研究下 QEMU 的 TCG (Tiny Code Generator) 翻译引擎，主要是以下几点：
1. Guest 代码到 Host 代码的翻译流程 (Frontend -> IR -> Backend)
2. 执行主循环 (cpu_exec) 与 翻译块 (Translation Block) 的生命周期管理
3. 编写 TCG Plugin 进行指令分析

## gemini 给出的意见
我先让 ai 给我生成一下调研的大概方向，这是它给出的。令我意外的是，
QEMU 的 TCG 模块已经高度解耦，甚至有项目单独将其剥离出来作为一个通用的 JIT 后端使用。

```markdown
这是一个非常经典且硬核的研究目标。TCG 是 QEMU 能够在 x86 上跑 ARM，或者在 ARM 上跑 RISC-V 的核心魔法。

下面为您设计一份分步、可行的研究方案。

宏观架构概览：
核心组件：
Frontend (前端): 负责将 Guest (客户机) 的二进制指令解码。
Middle-end (中端/TCG): 将解码后的指令转换为 TCG IR (中间表示)。
Backend (后端): 将 TCG IR 编译成 Host (宿主机) 的本地机器码。
Translation Block (TB): 翻译的基本单元，通常以跳转结束。

阶段一：黑盒观察翻译流 (目标 1)
先通过 QEMU 自带的日志功能观察输入输出。

工具: qemu-system-xxx 或 qemu-user
参数: -d in_asm,op,out_asm,nochain
in_asm: 打印 Guest 的汇编代码。
op: 打印生成的 TCG IR (中间码)。
out_asm: 打印最终生成的 Host 汇编代码。

阶段二：深入执行流与 TB 管理 (目标 2)
核心函数是 cpu_exec()。搞懂它是如何找到下一个 TB，或者在找不到时触发翻译的。

关键路径:
cpu_exec() -> tb_find() -> tb_lookup() (查缓存) -> tb_gen_code() (翻译) -> tcg_qemu_tb_exec() (执行)。

阶段三：TCG Plugins 插桩 (目标 3)
QEMU 引入了 TCG Plugins 机制，允许以动态库的形式加载插件，在翻译期间插入回调。这是目前做指令分析最推荐的方式，不需要侵入式修改核心源码。
```

嗯，方向很明确。QEMU 自带的 `-d` 调试选项非常强大，直接以此入手。
准备写个简单的 x86 汇编死循环，看看它到底翻译成了什么。

## Trace TCG: -d in_asm,op,out_asm

这里我跑了一个简单的 `inc %eax` 循环程序，节选了一个 Translation Block 的完整生命周期日志。
加了一些注释，分析它在干什么。

```assembly
----------------
IN: _start  <-- 这是 Guest (x86) 代码
0x4000b0:  mov    $0x0,%eax
0x4000b5:  inc    %eax
0x4000b6:  cmp    $0xa,%eax
0x4000b9:  jne    0x4000b5

----------------
OP:  <-- 这是 TCG IR (中间码)
 ld_i32 tmp0,env,$0xfffffffffffffff8      //以此类推，加载环境
 movi_i32 tmp1,$0x0
 mov_i32 eax,tmp1                         // 对应 mov $0x0, %eax
 
 label0:                                  // 对应循环标号
 mov_i32 tmp2,eax
 addi_i32 tmp2,tmp2,$0x1                  // 对应 inc %eax
 mov_i32 eax,tmp2
 
 mov_i32 tmp3,eax
 setcondi_i32 tmp4,tmp3,$0xa,ne           // 对应 cmp + jne 的逻辑判断
 brcondi_i32 tmp4,$0x0,ne,$label0         // 如果条件满足，跳回 label0
 
 exit_tb $0x0                             // 退出这个 TB
 
----------------
OUT: [size=120]  <-- 这是 Host (本机 x86_64) 代码
0x7f6c38000100:  mov    $0x0,%ebp
0x7f6c38000105:  mov    %ebp,0x0(%r14)    // 更新 Guest 的 EAX 寄存器 (映射在内存中)
...
0x7f6c38000120:  add    $0x1,%ebp         // 真正的本机加法指令
...
0x7f6c38000135:  cmp    $0xa,%ebp
0x7f6c38000138:  jne    0x7f6c38000120    // 真正的本机跳转
```

## Datapath 优化：Block Chaining (块链接)
在 TCG 中，性能优化的关键点在于减少“上下文切换”。
如果每执行完一个 TB 都返回 C 语言写的 `cpu_exec` 主循环去查找下一个 TB，开销巨大。

QEMU 使用了 **Block Chaining** 技术：
1.  当前 TB 执行完后，如果发现下一个 TB 已经在 Cache (TranslationBuffer) 中。
2.  直接修改当前 TB 结尾的机器码（patch jump instruction），让它直接跳转到下一个 TB 的物理地址。
3.  **完全绕过 QEMU 主循环**，CPU 在生成的代码块之间直接跳转。

这解释了为什么在 profile QEMU 时，经常看到 CPU 时间主要花在 `unknown` 或者 JIT 生成的匿名内存段中，而不是 QEMU 的二进制文件里。

- [性能测试](./tcg_chaining_perf.md)
  (留个坑，我想测一下 `-d nochain` 禁用这个特性后的性能下降幅度)

## TCG IR 分析
TCG IR 是一个基于**虚拟寄存器**的 RISC 风格指令集。它屏蔽了底层硬件差异。

### 寄存器映射 (cpu_env)
Guest 的物理寄存器（如 x86 的 EAX, ARM 的 R0）在 TCG 看来，其实都是内存。
它们被定义在 `CPUArchState` 结构体中。

```c
// target/i386/cpu.h
typedef struct CPUX86State {
    target_ulong regs[CPU_NB_REGS]; // EAX, ECX... 数组
    target_ulong eip;
    target_ulong eflags;
    // ...
} CPUX86State;
```
TCG 运行时，会有一个 Host 寄存器（通常是 x86_64 的 `%r14` 或 `%rbp`）专门指向这个结构体的基地址（即 `cpu_env`）。
指令 `ld_i32 tmp, env, offset` 本质上就是 `mov reg, [base + offset]`。

### 操作码 (Opcodes)
指令定义在 `tcg/tcg-opc.h`，非常简洁：
*   `mov_i32` / `add_i32`: 基础运算。
*   `qemu_ld_i32`: **关键指令**。它负责访问 Guest 的内存。这不仅仅是一个 load，它背后可能触发 SoftMMU (软件模拟 TLB 查表) 或者直接访问 Host 虚拟地址 (User Mode)。
*   `call`: 当 TCG 搞不定复杂逻辑（如浮点运算、系统寄存器操作）时，会生成调用 C helper 函数的指令。

## TCG Plugin 机制
这是我最感兴趣的部分。以前要监控指令执行，得修改 `target/xxx/translate.c`，非常痛苦且难以维护。
现在 QEMU 提供了 Plugin API，类似于加载动态库。

### 加载过程
在 `tb_gen_code` 阶段，如果有 Plugin 被加载，QEMU 会调用 Plugin 注册的 callback。

```c
// 伪代码：Plugin 插入逻辑
void vcpu_tb_trans(qemu_plugin_id_t id, struct qemu_plugin_tb *tb) {
    size_t n = qemu_plugin_tb_n_insns(tb);
    
    // 遍历 TB 中的每一条指令
    for (int i = 0; i < n; i++) {
        struct qemu_plugin_insn *insn = qemu_plugin_tb_get_insn(tb, i);
        // 在指令执行前插入回调
        qemu_plugin_register_vcpu_insn_exec_cb(insn, my_analysis_func, ...);
    }
}
```

Plugin 支持两种回调方式：
1.  **Inline**: 直接在生成的 JIT 代码中插入计数指令（如 `inc [mem]`），性能极高，不发生函数调用。
2.  **Callback**: 在执行点调用一个 C 函数，适合复杂分析，但有上下文切换开销。

### 源码位置
`tests/plugin/` 下有很多现成的例子，比如 `insn.c` (统计指令数) 和 `mem.c` (统计内存访问)。
这看起来是一个非常好的切入点，可以用来实现基本的 Basic Block 覆盖率统计工具。
