#
# RV32I subset test (only uses): add, addi, jalr, sw, lw, lbu, sb
# RAM/ROM unified address space; code and data share the same memory.
# Address space: 0x0000 - 0xffff (32-bit data width)
#
#
# Registers used conventionally:
# sp: stack pointer
# a0: pass/fail flag (expected 0 at halt; 1 indicates failure)
#

_start:
addi sp, zero, 1792
addi s0, zero, 1024
addi s1, zero, 1280

#
# -------- Test 1: sb/lbu/lw endianness & byte overwrite --------
addi t0, zero, 0x11
sb t0, 0(s0)
addi t0, zero, 0x22
sb t0, 1(s0)
addi t0, zero, 0x33
sb t0, 2(s0)
addi t0, zero, 0x44
sb t0, 3(s0)
lw t1, 0(s0)
sw t1, 0(s1)

addi t0, zero, 0xff
sb t0, 1(s0)
lw t1, 0(s0)
sw t1, 4(s1)
lbu t2, 1(s0)
sw t2, 8(s1)

#
# -------- Test 2: jalr return address (+4) correctness --------
addi a0, zero, 1
addi t0, zero, func_ret_test
addi t0, t0, 1
jalr ra, 0(t0)
addi a0, zero, 0
sw a0, 12(s1)

#
# -------- Test 3: nested call & stack save/restore --------
addi a0, zero, 1
addi t0, zero, func_nested
jalr ra, 0(t0)
addi a0, zero, 0
sw a0, 16(s1)

#
# -------- Test 4: indirect jump through memory (lw + jalr) --------
addi t3, zero, 1408
addi t0, zero, case0
sw t0, 0(t3)
addi t0, zero, case1
sw t0, 4(t3)

addi t4, zero, 1
add t4, t4, t4
add t4, t4, t4
add t5, t3, t4
lw t6, 0(t5)
jalr ra, 0(t6)
sw a1, 20(s1)

#
# -------- Test 5: high address wrap/mask (0xfffc) --------
addi t0, zero, 0
addi t0, t0, -4
addi t1, zero, 0xef
sb t1, 0(t0)
addi t1, zero, 0xbe
sb t1, 1(t0)
addi t1, zero, 0xad
sb t1, 2(t0)
addi t1, zero, 0xde
sb t1, 3(t0)
lw t2, 0(t0)
sw t2, 24(s1)
lbu t3, 3(t0)
sw t3, 28(s1)

#
# Halt loop
addi t0, zero, halt
jalr zero, 0(t0)

#
# -------- Functions --------

func_ret_test:
jalr zero, 0(ra)

func_nested:
addi sp, sp, -12
sw ra, 8(sp)
sw s0, 4(sp)

addi t0, zero, 0xaa
sb t0, -1(sp)
lbu t1, -1(sp)
sw t1, 32(s1)

addi a0, zero, 1
addi t0, zero, func_leaf
jalr ra, 0(t0)
addi a0, zero, 0

lw s0, 4(sp)
lw ra, 8(sp)
addi sp, sp, 12
jalr zero, 0(ra)

func_leaf:
jalr zero, 0(ra)

case0:
addi a1, zero, 0x111
jalr zero, 0(ra)

case1:
addi a1, zero, 0x222
jalr zero, 0(ra)

halt:
addi t0, zero, halt
jalr zero, 0(t0)

#
# ------------- Expected results -------------
# a0 = 0x00000000
#
# result memory base s1 = 0x00000500
# [0x0500] word = 0x44332211
# [0x0504] word = 0x4433ff11
# [0x0508] word = 0x000000ff
# [0x050c] word = 0x00000000
# [0x0510] word = 0x00000000
# [0x0514] word = 0x00000222
# [0x0518] word = 0xdeadbeef
# [0x051c] word = 0x000000de
# [0x0520] word = 0x000000aa
