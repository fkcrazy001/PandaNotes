# QEMU TCG 代码翻译技术研究

想研究下QEMU的TCG技术，主要是以下几点：
1. QEMU地址模型（CPU访问地址时如何通过softmmu进行地址转换）
2. QEMU指令翻译（如何定义新指令、TCG指令实现、TCG如何翻译为host machine code）
3. TCG的ISA和寄存器映射规范

## 1. QEMU 地址模型与 SoftMMU

### 1.1 整体架构

QEMU在系统模式（system emulation）下使用软件MMU来实现虚拟地址到物理地址的转换。这个过程主要在 `accel/tcg/cputlb.c` 中实现。

```c
// cputlb.c:127-140
// Find the TLB index corresponding to the mmu_idx + address pair.
static inline uintptr_t tlb_index(CPUState *cpu, uintptr_t mmu_idx,
                                  vaddr addr)
{
    uintptr_t size_mask = cpu_tlb_fast(cpu, mmu_idx)->mask >> CPU_TLB_ENTRY_BITS;
    return (addr >> TARGET_PAGE_BITS) & size_mask;
}

// Find the TLB entry corresponding to the mmu_idx + address pair.
static inline CPUTLBEntry *tlb_entry(CPUState *cpu, uintptr_t mmu_idx,
                                     vaddr addr)
{
    return &cpu_tlb_fast(cpu, mmu_idx)->table[tlb_index(cpu, mmu_idx, addr)];
}
```

### 1.2 地址转换流程

当guest CPU访问内存时，流程如下：

```
Guest VA -> TLB lookup -> (命中) -> Host VA
                |
                +-> (未命中) -> MMU仿真代码 -> 更新TLB -> 重试
```

关键数据结构在 `tcg/tcg-op-ldst.c` 中定义的 `qemu_ld` 和 `qemu_st` 操作：

```c
// tcg-op-ldst.c:241-283
void tcg_gen_qemu_ld_i32_chk(TCGv_i32 val, TCGTemp *addr, TCGArg idx,
                             MemOp memop, TCGType addr_type)
{
    tcg_debug_assert(addr_type == tcg_ctx->addr_type);
    tcg_debug_assert((memop & MO_SIZE) <= MO_32);
    tcg_gen_qemu_ld_i32_int(val, addr, idx, memop);
}

static void tcg_gen_qemu_ld_i32_int(TCGv_i32 val, TCGTemp *addr,
                                    TCGArg idx, MemOp memop)
{
    MemOp orig_memop;
    MemOpIdx orig_oi, oi;
    TCGv_i64 copy_addr;
    TCGTemp *addr_new;

    tcg_gen_req_mo(TCG_MO_LD_LD | TCG_MO_ST_LD);
    orig_memop = memop = tcg_canonicalize_memop(memop, 0, 0);
    orig_oi = oi = make_memop_idx(memop, idx);

    // 字节序转换处理
    if ((memop & MO_BSWAP) && !tcg_target_has_memory_bswap(memop)) {
        memop &= ~MO_BSWAP;
        oi = make_memop_idx(memop, idx);
    }

    addr_new = tci_extend_addr(addr);
    copy_addr = plugin_maybe_preserve_addr(addr);
    gen_ldst1(INDEX_op_qemu_ld, TCG_TYPE_I32, tcgv_i32_temp(val), addr_new, oi);
    // ...
}
```

### 1.3 TLB 结构设计

TLB使用直接映射（direct-mapped）的方式，核心结构：

```c
// cputlb.c:95-103
static inline size_t tlb_n_entries(CPUTLBDescFast *fast)
{
    return (fast->mask >> CPU_TLB_ENTRY_BITS) + 1;
}

static inline size_t sizeof_tlb(CPUTLBDescFast *fast)
{
    return fast->mask + (1 << CPU_TLB_ENTRY_BITS);
}
```

每个TLB entry包含：
- `addr_read/addr_write/addr_code`: 不同访问类型的地址
- `addend`: 地址偏移量（guest VA -> host VA）
- `phys_addr`: 物理地址（可选）

## 2. QEMU 指令翻译机制

### 2.1 翻译流程概览

整体翻译流程在 `accel/tcg/translator.c` 中：

```c
// translator.c:122-150
void translator_loop(CPUState *cpu, TranslationBlock *tb, int *max_insns,
                     vaddr pc, void *host_pc, const TranslatorOps *ops,
                     DisasContextBase *db)
{
    uint32_t cflags = tb_cflags(tb);
    TCGOp *icount_start_insn;
    TCGOp *first_insn_start = NULL;
    bool plugin_enabled;

    // 初始化DisasContext
    db->tb = tb;
    db->pc_first = pc;
    db->pc_next = pc;
    db->is_jmp = DISAS_NEXT;
    db->num_insns = 0;
    db->max_insns = *max_insns;
    db->insn_start = NULL;
    db->fake_insn = false;
    db->host_addr[0] = host_pc;
    db->host_addr[1] = NULL;
    db->record_start = 0;
    db->record_len = 0;
    db->code_mmuidx = cpu_mmu_index(cpu, true);

    ops->init_disas_context(db, cpu);
    // 开始翻译
    icount_start_insn = gen_tb_start(db, cflags);
    // ...
}
```

### 2.2 TCG opcode 定义

TCG指令定义在 `include/tcg/tcg-opc.h`：

```c
// include/tcg/tcg-opc.h:29-94
/* predefined ops */
DEF(discard, 1, 0, 0, TCG_OPF_NOT_PRESENT)
DEF(set_label, 0, 0, 1, TCG_OPF_BB_END | TCG_OPF_NOT_PRESENT)

/* variable number of parameters */
DEF(call, 0, 0, 3, TCG_OPF_CALL_CLOBBER | TCG_OPF_NOT_PRESENT)

DEF(br, 0, 0, 1, TCG_OPF_BB_END | TCG_OPF_NOT_PRESENT)
DEF(brcond, 0, 2, 2, TCG_OPF_BB_END | TCG_OPF_COND_BRANCH | TCG_OPF_INT)

DEF(mov, 1, 1, 0, TCG_OPF_INT | TCG_OPF_NOT_PRESENT)

DEF(add, 1, 2, 0, TCG_OPF_INT)
DEF(and, 1, 2, 0, TCG_OPF_INT)
DEF(sub, 1, 2, 0, TCG_OPF_INT)
DEF(xor, 1, 2, 0, TCG_OPF_INT)
// ... 更多算术逻辑操作

DEF(ld8u, 1, 1, 1, TCG_OPF_INT)   // load unsigned byte
DEF(ld8s, 1, 1, 1, TCG_OPF_INT)   // load signed byte
DEF(ld16u, 1, 1, 1, TCG_OPF_INT)  // load unsigned halfword
DEF(ld16s, 1, 1, 1, TCG_OPF_INT)  // load signed halfword
DEF(st8, 0, 2, 1, TCG_OPF_INT)    // store byte
DEF(st16, 0, 2, 1, TCG_OPF_INT)   // store halfword

DEF(qemu_ld, 1, 1, 1, TCG_OPF_CALL_CLOBBER | TCG_OPF_SIDE_EFFECTS | TCG_OPF_INT)
DEF(qemu_st, 0, 2, 1, TCG_OPF_CALL_CLOBBER | TCG_OPF_SIDE_EFFECTS | TCG_OPF_INT)
```

**DEF宏的参数说明**：
```c
// DEF(name, oargs, iargs, cargs, flags)
// - name: 指令名称
// - oargs: 输出参数个数
// - iargs: 输入参数个数  
// - cargs: 常量参数个数
// - flags: 标志位
```

### 2.3 如何定义新指令

以RISC-V的 `lui` 指令为例，展示如何定义和翻译新指令：

```c
// target/riscv/tcg/translator-rvi.c.inc
static bool trans_lui(DisasContext *ctx, arg_lui *a)
{
    gen_set_gpr(ctx, a->rd, a->imm);
    return true;
}
```

`lui` 指令将20位立即数加载到寄存器的高位。翻译过程：

1. **解码阶段**：从guest二进制中提取指令操作码和操作数
2. **翻译阶段**：调用 `trans_lui` 函数
3. **TCG IR生成**：调用 `gen_set_gpr` 生成TCG指令

```c
// 实际生成的TCG IR伪代码：
// mov_i32 t0, $imm20  (将立即数放入临时寄存器)
// deposit_i32 t0, t0, $0, 12  (将立即数移到高位)
// mov_i64 x[rd], t0  (写回目标寄存器)
```

### 2.4 TCG 指令操作API

TCG提供多种指令生成函数（位于 `tcg/tcg-op.c`）：

```c
// tcg-op.c:40-105
TCGOp * NI tcg_gen_op1(TCGOpcode opc, TCGType type, TCGArg a1)
{
    TCGOp *op = tcg_emit_op(opc, 1);
    TCGOP_TYPE(op) = type;
    op->args[0] = a1;
    return op;
}

TCGOp * NI tcg_gen_op2(TCGOpcode opc, TCGType type, TCGArg a1, TCGArg a2)
{
    TCGOp *op = tcg_emit_op(opc, 2);
    TCGOP_TYPE(op) = type;
    op->args[0] = a1;
    op->args[1] = a2;
    return op;
}

TCGOp * NI tcg_gen_op3(TCGOpcode opc, TCGType type, TCGArg a1,
                       TCGArg a2, TCGArg a3)
{
    TCGOp *op = tcg_emit_op(opc, 3);
    TCGOP_TYPE(op) = type;
    op->args[0] = a1;
    op->args[1] = a2;
    op->args[2] = a3;
    return op;
}
```

**类型安全的包装器**：

```c
// tcg-op.c:117-180
static void DNI tcg_gen_op2_i32(TCGOpcode opc, TCGv_i32 a1, TCGv_i32 a2)
{
    tcg_gen_op2(opc, TCG_TYPE_I32, tcgv_i32_arg(a1), tcgv_i32_arg(a2));
}

static void DNI tcg_gen_op2_i64(TCGOpcode opc, TCGv_i64 a1, TCGv_i64 a2)
{
    tcg_gen_op2(opc, TCG_TYPE_I64, tcgv_i64_arg(a1), tcgv_i64_arg(a2));
}

static void DNI tcg_gen_add_i32(TCGv_i32 ret, TCGv_i32 a, TCGv_i32 b)
{
    tcg_gen_op2_i32(INDEX_op_add, ret, a, b);
}
```

## 3. TCG 到 Host Code 的翻译

### 3.1 Target Backend 架构

每个host架构有自己的backend，位于 `tcg/<arch>/` 目录。以x86_64为例：

```c
// tcg/x86_64/tcg-target.h:30-80
#define TCG_TARGET_NB_REGS   32

typedef enum {
    TCG_REG_EAX = 0,
    TCG_REG_ECX,
    TCG_REG_EDX,
    TCG_REG_EBX,
    TCG_REG_ESP,
    TCG_REG_EBP,
    TCG_REG_ESI,
    TCG_REG_EDI,

    TCG_REG_R8,
    TCG_REG_R9,
    TCG_REG_R10,
    TCG_REG_R11,
    TCG_REG_R12,
    TCG_REG_R13,
    TCG_REG_R14,
    TCG_REG_R15,

    TCG_REG_XMM0,
    TCG_REG_XMM1,
    TCG_REG_XMM2,
    TCG_REG_XMM3,
    TCG_REG_XMM4,
    TCG_REG_XMM5,
    TCG_REG_XMM6,
    TCG_REG_XMM7,
    TCG_REG_XMM8,
    TCG_REG_XMM9,
    TCG_REG_XMM10,
    TCG_REG_XMM11,
    TCG_REG_XMM12,
    TCG_REG_XMM13,
    TCG_REG_XMM14,
    TCG_REG_XMM15,

    TCG_REG_RAX = TCG_REG_EAX,
    TCG_REG_RCX = TCG_REG_ECX,
    TCG_REG_RDX = TCG_REG_EDX,
    TCG_REG_RBX = TCG_REG_EBX,
    TCG_REG_RSP = TCG_REG_ESP,
    TCG_REG_RBP = TCG_REG_EBP,
    TCG_REG_RSI = TCG_REG_ESI,
    TCG_REG_RDI = TCG_REG_EDI,

    TCG_AREG0 = TCG_REG_EBP,
    TCG_REG_CALL_STACK = TCG_REG_ESP
} TCGReg;
```

### 3.2 寄存器分配策略

TCG使用复杂的寄存器分配算法，x86_64的分配顺序：

```c
// tcg/x86_64/tcg-target.c.inc:52-88
static const int tcg_target_reg_alloc_order[] = {
    TCG_REG_RBP,
    TCG_REG_RBX,
    TCG_REG_R12,
    TCG_REG_R13,
    TCG_REG_R14,
    TCG_REG_R15,
    TCG_REG_R10,
    TCG_REG_R11,
    TCG_REG_R9,
    TCG_REG_R8,
    TCG_REG_RCX,
    TCG_REG_RDX,
    TCG_REG_RSI,
    TCG_REG_RDI,
    TCG_REG_RAX,
    TCG_REG_XMM0,
    TCG_REG_XMM1,
    // ... 更多XMM寄存器
};
```

**分配原则**：
- callee-saved寄存器优先（RBX, RBP, R12-R15）
- caller-saved寄存器次之（RAX, RCX, RDX等）
- 向量寄存器单独分配

### 3.3 TCG IR 到 Host 汇编的翻译

以 `add` 指令为例，查看x86_64后端如何实现：

```c
// 伪代码展示翻译过程
TCG IR: add_i32 t0, t1, t2
       ↓
x86_64后端选择:
       mov eax, [t1寄存器或内存]
       add eax, [t2寄存器或内存]
       mov [t0位置], eax
```

函数调用约定定义：

```c
// tcg/x86_64/tcg-target.c.inc:92-120
static const int tcg_target_call_iarg_regs[] = {
#if defined(_WIN64)
    TCG_REG_RCX,
    TCG_REG_RDX,
#else
    TCG_REG_RDI,
    TCG_REG_RSI,
    TCG_REG_RDX,
    TCG_REG_RCX,
#endif
    TCG_REG_R8,
    TCG_REG_R9,
};

static TCGReg tcg_target_call_oarg_reg(TCGCallReturnKind kind, int slot)
{
    switch (kind) {
    case TCG_CALL_RET_NORMAL:
        tcg_debug_assert(slot >= 0 && slot <= 1);
        return slot ? TCG_REG_EDX : TCG_REG_EAX;
    // ...
    }
}
```

### 3.4 TCG类型系统

TCG定义多种数据类型：

```c
// include/tcg/tcg.h:128-149
typedef enum TCGType {
    TCG_TYPE_I32,     // 32位整数
    TCG_TYPE_I64,     // 64位整数
    TCG_TYPE_I128,    // 128位整数

    TCG_TYPE_V64,     // 64位向量
    TCG_TYPE_V128,    // 128位向量
    TCG_TYPE_V256,    // 256位向量

    /* 别名 */
    TCG_TYPE_REG = TCG_TYPE_I64,      // 主机寄存器大小
    TCG_TYPE_PTR,                      // 指针大小
} TCGType;
```

## 4. Translation Block (TB) 机制

### 4.1 TB 结构和链接

```c
// accel/tcg/translate-all.c:41-100
TBContext tb_ctx;

static int encode_search(TranslationBlock *tb, uint8_t *block)
{
    uint8_t *highwater = tcg_ctx->code_gen_highwater;
    uint64_t *insn_data = tcg_ctx->gen_insn_data;
    uint16_t *insn_end_off = tcg_ctx->gen_insn_end_off;
    uint8_t *p = block;
    int i, j, n;

    for (i = 0, n = tb->icount; i < n; ++i) {
        // 编码每条指令的信息
        for (j = 0; j < INSN_START_WORDS; ++j) {
            uint64_t prev = (i == 0 ? 0 : insn_data[(i - 1) * INSN_START_WORDS + j]);
            uint64_t curr = insn_data[i * INSN_START_WORDS + j];
            p = encode_sleb128(p, curr - prev);
        }
        // ...
    }
    return p - block;
}
```

### 4.2 TB 链接优化

```c
// docs/devel/tcg.rst:52-110
/*
 * 直接块链链接（Direct Block Chaining）
 * 
 * 优化前：每次执行完TB都要回到main loop查找下一个TB
 * 优化后：相邻TB之间直接跳转，避免回main loop
 */

// 关键函数
tcg_gen_goto_tb()      // 发出goto_tb TCG指令
tcg_gen_exit_tb()      // 退出当前TB
tcg_gen_lookup_and_goto_ptr()  // 查找并跳转到目标TB
```

### 4.3 TB 执行流程

```
+------------------+
|  CPU执行入口      |
|  cpu_exec()      |
+--------+---------+
         |
         v
+--------+---------+
|  查找TB缓存      |
|  tb_jmp_cache   |
+--------+---------+
         |
    [命中]    [未命中]
     |          |
     v          v
+--------+   +--------+
| 执行TB |   | 翻译guest |
| 代码   |   | 指令     |
+--------+   +--------+
     |          |
     +----->--------+
            |  生成TCG IR  |
            +--------+
            |  优化       |
            +--------+
            |  汇编       |
            +--------+
            |  缓存TB     |
            +--------+
```

## 5. 具体实例：ADD指令翻译全过程

### 5.1 Guest代码

```assembly
# RISC-V: add x3, x1, x2
# 功能: x3 = x1 + x2
```

### 5.2 TCG IR生成

```c
// 翻译器生成以下TCG指令序列：
tcg_gen_add_i64(tmp0, cpu_x[1], cpu_x[2]);  // tmp0 = x1 + x2
tcg_gen_mov_i64(cpu_x[3], tmp0);           // x3 = tmp0
tcg_gen_exit_tb(tb, TB_EXIT_REQUESTED);    // 退出TB
```

### 5.3 汇编优化后

```asm
# x86_64优化后的代码 (伪代码)
mov     rax, QWORD PTR [rbp + x1_offset]   ; 加载x1
add     rax, QWORD PTR [rbp + x2_offset]   ; 加上x2
mov     QWORD PTR [rbp + x3_offset], rax    ; 保存x3
jmp     next_tb_address                      ; 跳转到下一个TB
```

### 5.4 内存访问路径

```
TCG虚拟寄存器(cpu_x[1]) 
    ↓
映射到host寄存器或内存位置
    ↓
通过softmmu访问实际内存
    ↓
TLB查找 → 地址转换 → Host访问
```

## 6. 实践：添加自定义指令

### 6.1 步骤概述

1. **在target翻译器中添加decode函数**
2. **定义trans_*函数生成TCG IR**
3. **注册到指令解码表**

### 6.2 代码示例

```c
// 1. 在target/riscv/insn_trans/trans_xxx.c.inc中添加

static bool trans_my_custom_op(DisasContext *ctx, arg_my_custom_op *a)
{
    TCGv temp = tcg_temp_new();
    TCGv result = tcg_temp_new();
    
    // 生成TCG IR
    tcg_gen_andi_i64(temp, get_gpr(ctx, a->rs1), a->mask);  // temp = rs1 & mask
    tcg_gen_shri_i64(temp, temp, a->shift);                  // temp >>= shift
    tcg_gen_andi_i64(result, temp, a->width - 1);            // result = temp & (width-1)
    
    // 写回结果
    gen_set_gpr(ctx, a->rd, result);
    
    // 释放临时寄存器
    tcg_temp_free(temp);
    tcg_temp_free(result);
    
    return true;
}

// 2. 在decode函数中调用
// decode_my_custom_op() -> trans_my_custom_op()
```

### 6.3 注意事项

- **性能考虑**: 复杂指令用helper函数实现更高效
- **异常处理**: 需要处理非法指令和特权级异常
- **原子性**: 多线程环境下需考虑内存屏障

## 7. QEMU 中断/异常机制

### 7.1 整体架构

QEMU的中断/异常处理机制是模拟guest CPU的核心功能之一。它需要处理两种场景：
1. **Guest内部异常**：指令执行过程中触发的异常（如非法指令、页面错误）
2. **外部中断**：来自外设的中断信号（如定时器、I/O设备）

核心处理流程在 `accel/tcg/cpu-exec.c` 中实现：

```c
// cpu-exec.c:701-750
if (cpu->exception_index >= EXCP_INTERRUPT) {
    /* exit request from the cpu execution loop */
    *ret = cpu->exception_index;
    if (*ret == EXCP_DEBUG) {
        cpu_handle_debug_exception(cpu);
    }
    cpu->exception_index = -1;
    return true;
}

#ifndef CONFIG_USER_ONLY
    if (replay_exception()) {
        const TCGCPUOps *tcg_ops = cpu->cc->tcg_ops;

        bql_lock();
        tcg_ops->do_interrupt(cpu);  // 调用架构特定的中断处理
        bql_unlock();
        cpu->exception_index = -1;
        // ...
    }
#endif
```

### 7.2 Guest指令触发的异常

#### 7.2.1 异常分类

以RISC-V为例，异常类型定义在 `target/riscv/cpu_bits.h`：

```c
// target/riscv/cpu_bits.h:761-786
typedef enum RISCVException {
    RISCV_EXCP_NONE = -1, /* sentinel value */
    RISCV_EXCP_INST_ADDR_MIS = 0x0,    // 指令地址未对齐
    RISCV_EXCP_INST_ACCESS_FAULT = 0x1, // 指令访问错误
    RISCV_EXCP_ILLEGAL_INST = 0x2,     // 非法指令
    RISCV_EXCP_BREAKPOINT = 0x3,       // 断点
    RISCV_EXCP_LOAD_ADDR_MIS = 0x4,    // 加载地址未对齐
    RISCV_EXCP_LOAD_ACCESS_FAULT = 0x5, // 加载访问错误
    RISCV_EXCP_STORE_AMO_ADDR_MIS = 0x6, // 存储地址未对齐
    RISCV_EXCP_STORE_AMO_ACCESS_FAULT = 0x7, // 存储访问错误
    RISCV_EXCP_U_ECALL = 0x8,          // 用户模式ECALL
    RISCV_EXCP_S_ECALL = 0x9,          // 超级用户模式ECALL
    RISCV_EXCP_M_ECALL = 0xb,          // 机器模式ECALL
    RISCV_EXCP_INST_PAGE_FAULT = 0xc,  // 指令页错误
    RISCV_EXCP_LOAD_PAGE_FAULT = 0xd,  // 加载页错误
    RISCV_EXCP_STORE_PAGE_FAULT = 0xf, // 存储页错误
    // ...
} RISCVException;
```

#### 7.2.2 异常触发机制

**方式一：TCG指令直接触发**

```c
// target/riscv/translate.c:257-262
static void generate_exception(DisasContext *ctx, RISCVException excp)
{
    gen_update_pc(ctx, 0);
    gen_helper_raise_exception(tcg_env, tcg_constant_i32(excp));
    ctx->base.is_jmp = DISAS_NORETURN;
}
```

**方式二：非法指令异常**

```c
// target/riscv/translate.c:264-273
static void gen_exception_illegal(DisasContext *ctx)
{
    tcg_gen_st_i32(tcg_constant_i32(ctx->opcode), tcg_env,
                   offsetof(CPURISCVState, bins));
    if (ctx->virt_inst_excp) {
        generate_exception(ctx, RISCV_EXCP_VIRT_INSTRUCTION_FAULT);
    } else {
        generate_exception(ctx, RISCV_EXCP_ILLEGAL_INST);
    }
}
```

**使用案例：地址未对齐异常**

```c
// target/riscv/translate.c:275-279
static void gen_exception_inst_addr_mis(DisasContext *ctx, TCGv target)
{
    tcg_gen_st_tl(target, tcg_env, offsetof(CPURISCVState, badaddr));
    generate_exception(ctx, RISCV_EXCP_INST_ADDR_MIS);
}
```

#### 7.2.3 Helper函数处理异常

当翻译的TCG代码执行到 `helper_raise_exception` 时：

```c
// target/riscv/op_helper.c:46-63
G_NORETURN void riscv_raise_exception(CPURISCVState *env,
                                      RISCVException exception,
                                      uintptr_t pc)
{
    CPUState *cs = env_cpu(env);

    trace_riscv_exception(exception,
                          riscv_cpu_get_trap_name(exception, false),
                          env->pc);

    cs->exception_index = exception;
    cpu_loop_exit_restore(cs, pc);  // 关键：退出当前TB并跳转到异常处理
}

void helper_raise_exception(CPURISCVState *env, uint32_t exception)
{
    riscv_raise_exception(env, exception, 0);
}
```

### 7.3 外部中断处理

#### 7.3.1 中断标志位定义

```c
// target/riscv/cpu_bits.h:793-794
#define RISCV_EXCP_INT_FLAG                0x80000000  // 中断标志
#define RISCV_EXCP_INT_MASK                0x7fffffff // 掩码

// 中断类型定义
#define IRQ_U_SOFT                         0   // 用户软件中断
#define IRQ_S_SOFT                         1   // 超级用户软件中断
#define IRQ_M_SOFT                         3   // 机器软件中断
#define IRQ_U_TIMER                        4   // 用户定时器中断
#define IRQ_S_TIMER                        5   // 超级用户定时器中断
#define IRQ_M_TIMER                        7   // 机器定时器中断
#define IRQ_U_EXT                          8   // 用户外部中断
#define IRQ_S_EXT                          9   // 超级用户外部中断
#define IRQ_M_EXT                          11  // 机器外部中断
```

#### 7.3.2 中断处理流程

外部中断通过 `cpu_handle_interrupt` 函数处理：

```c
// cpu-exec.c:779-884
static inline bool cpu_handle_interrupt(CPUState *cpu,
                                        TranslationBlock **last_tb)
{
    // 1. 检查是否有中断请求
    if (unlikely(cpu_test_interrupt(cpu, ~0))) {
        bql_lock();
        if (cpu_test_interrupt(cpu, CPU_INTERRUPT_DEBUG)) {
            cpu_reset_interrupt(cpu, CPU_INTERRUPT_DEBUG);
            cpu->exception_index = EXCP_DEBUG;
            bql_unlock();
            return true;
        }

        if (cpu_test_interrupt(cpu, CPU_INTERRUPT_HALT)) {
            replay_interrupt();
            cpu_reset_interrupt(cpu, CPU_INTERRUPT_HALT);
            cpu->halted = 1;
            cpu->exception_index = EXCP_HLT;
            bql_unlock();
            return true;
        }

        // 2. 调用架构特定的中断处理
        if (tcg_ops->cpu_exec_interrupt(cpu, interrupt_request)) {
            // 处理完成后返回
            cpu->exception_index = -1;
            *last_tb = NULL;
        }
        bql_unlock();
    }

    // 3. 检查退出请求
    if (unlikely(qatomic_load_acquire(&cpu->exit_request)) || icount_exit_request(cpu)) {
        if (cpu->exception_index == -1) {
            cpu->exception_index = EXCP_INTERRUPT;
        }
        return true;
    }

    return false;
}
```

#### 7.3.3 CPU状态通知机制

**中断请求标志**：

```c
// cpu-exec.c:728
tcg_ops->do_interrupt(cpu);  // 在中断处理时被调用
```

**外设触发中断流程**：

```
外设中断源
    ↓
设置CPU的interrupt_request标志
    ↓
设置exit_request请求CPU退出当前TB
    ↓
cpu_handle_interrupt()检测到中断
    ↓
调用架构特定的do_interrupt()
    ↓
保存现场、切换到中断处理模式
```

### 7.4 核心退出机制：longjmp

QEMU使用 `siglongjmp` 实现从任意位置退出当前TB：

```c
// accel/tcg/cpu-exec-common.c:60-75
void cpu_loop_exit(CPUState *cpu)
{
    /* Undo the setting in cpu_tb_exec.  */
    cpu->neg.can_do_io = true;
    /* Undo any setting in generated code.  */
    qemu_plugin_disable_mem_helpers(cpu);
    siglongjmp(cpu->jmp_env, 1);  // 跳转到cpu_exec的longjmp捕获点
}

void cpu_loop_exit_restore(CPUState *cpu, uintptr_t pc)
{
    if (pc) {
        cpu_restore_state(cpu, pc);  // 恢复CPU状态到异常发生前
    }
    cpu_loop_exit(cpu);
}
```

**执行流程**：

```
helper_raise_exception()
    ↓
cpu_loop_exit_restore()
    ↓
siglongjmp(cpu->jmp_env, 1)
    ↓
    [跳回 cpu_exec 的 sigsetjmp 捕获点]
    ↓
cpu_handle_exception()
    ↓
tcg_ops->do_interrupt(cpu)  // 处理异常/中断
```

### 7.5 案例分析：RISC-V Ecall指令

#### 7.5.1 指令功能

ECALL指令用于从低特权级切换到高特权级（如U -> S -> M）。

#### 7.5.2 翻译实现

```c
// target/riscv/insn_trans/trans_rvi.c
static bool trans_ecall(DisasContext *ctx, arg_ecall *a)
{
    RISCVException excp;
    if (a->mode == PRV_U) {
        excp = RISCV_EXCP_U_ECALL;
    } else if (a->mode == PRV_S) {
        excp = RISCV_EXCP_S_ECALL;
    } else if (a->mode == PRV_VS) {
        excp = RISCV_EXCP_VS_ECALL;
    } else {
        excp = RISCV_EXCP_M_ECALL;
    }
    generate_exception(ctx, excp);
    return true;
}
```

#### 7.5.3 完整流程图

```
Guest执行ECALL指令
    ↓
TCG翻译：generate_exception(RISCV_EXCP_XXX_ECALL)
    ↓
TCG IR: helper_raise_exception(env, exception_id)
    ↓
执行helper_raise_exception()
    ↓
riscv_raise_exception()
    ↓
设置 cs->exception_index = exception_id
    ↓
cpu_loop_exit_restore(cs, pc)
    ↓
siglongjmp -> 返回cpu_exec主循环
    ↓
cpu_handle_exception()检测到异常
    ↓
tcg_ops->do_interrupt(cpu)  // RISC-V特定处理
    ↓
保存当前PC到mepc寄存器
    ↓
根据mstatus确定新特权级
    ↓
设置mtval等CSR寄存器
    ↓
跳转到对应的异常处理向量
```

### 7.6 案例分析：外部定时器中断

#### 7.6.1 中断触发路径

```
Host定时器触发
    ↓
QEMU定时器回调函数
    ↓
设置RISC-V的mip.MTIP位
    ↓
调用qemu_cpu_kick(cpu)请求CPU处理
    ↓
CPU执行流中检测到中断
```

#### 7.6.2 代码实现

```c
// 假设在hw/riscv/virt.c中
static void riscv_timer_cb(void *opaque)
{
    RISCVCPU *cpu = opaque;
    CPURISCVState *env = &cpu->env;

    // 设置定时器中断挂起位
    qatomic_set(&env->mip, MIP_MTIP);

    // 通知CPU有中断
    qemu_cpu_kick(CPU(cpu));
}

// 触发CPU中断处理
void qemu_cpu_kick(CPUState *cpu)
{
    qatomic_store_release(&cpu->exit_request, true);
    // ...
}
```

#### 7.6.3 CPU中断处理

```c
// cpu-exec.c:779-884
while (!cpu_handle_interrupt(cpu, &last_tb)) {
    // 执行TB
    tb = cpu_tb_exec(cpu, tb, &tb_exit);
}

// cpu_handle_interrupt内部
if (unlikely(cpu_test_interrupt(cpu, ~0))) {
    // 测试各种中断源
    if (cpu_test_interrupt(cpu, CPU_INTERRUPT_HALT)) {
        // 处理HALT中断
    }
    // 调用架构特定的中断处理
    tcg_ops->cpu_exec_interrupt(cpu, interrupt_request);
}
```

### 7.7 异常处理关键点

| 场景 | 触发方式 | 关键函数 | 退出机制 |
|------|----------|----------|----------|
| 非法指令 | decode阶段检测 | `gen_exception_illegal()` | `helper_raise_exception()` |
| 页错误 | 内存访问时 | `tcg_gen_qemu_ld/st` | TLB未命中路径 |
| 系统调用 | ECALL指令 | `generate_exception()` | `cpu_loop_exit_restore()` |
| 外部中断 | 外设触发 | `qemu_cpu_kick()` | `cpu_handle_interrupt()` |
| 断点 | DEBUG触发 | `EXCP_DEBUG` | `cpu_handle_debug_exception()` |

### 7.8 总结

QEMU中断/异常机制的核心设计：

1. **统一异常索引**：`cpu->exception_index` 保存当前异常类型
2. **TCG辅助函数**：`helper_raise_exception()` 实现从翻译代码中触发异常
3. **长跳转机制**：使用 `siglongjmp` 从任意位置退出TB
4. **架构解耦**：`tcg_ops->do_interrupt()` 抽象架构差异
5. **中断通知**：`interrupt_request` 和 `exit_request` 协调CPU响应中断

这种设计既保证了异常处理的灵活性，又最小化了性能开销。

## 8. 总结

### 核心概念回顾

| 组件 | 作用 | 关键文件 |
|------|------|----------|
| TCG IR | 中间表示，guest与host解耦 | include/tcg/tcg-opc.h |
| SoftMMU | 地址翻译，TLB管理 | accel/tcg/cputlb.c |
| Backend | TCG IR到机器码 | tcg/x86_64/tcg-target.c.inc |
| Translator | Guest指令到TCG IR | target/riscv/tcg/translator-*.c |
| Exception/Interrupt | 异常处理机制 | accel/tcg/cpu-exec.c, op_helper.c |

### 进一步研究

1. **性能优化**: TB链接、指令缓存、寄存器分配优化
2. **向量化**: SIMD指令的TCG支持和向量寄存器映射
3. **多线程**: MTTCG (Multi-Threaded TCG) 实现
4. **插件系统**: QEMU plugin与TCG的交互

这个文档覆盖了QEMU TCG的核心架构。由于代码量很大，建议针对具体模块深入研究。
