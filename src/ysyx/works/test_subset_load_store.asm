#
# RV32I subset test (only uses): add, addi, jalr, sw, lw, lbu, sb
# Memory map: code+data share the same address space (RAM/ROM unified)
#
#
# Base address for data: 0x400 (1024), chosen to avoid overlapping with code
addi a0, zero, 1024
#
# Write 4 bytes: 0x11 0x22 0x33 0x44 to [0x400..0x403]
addi t0, zero, 0x11
sb t0, 0(a0)
addi t0, zero, 0x22
sb t0, 1(a0)
addi t0, zero, 0x33
sb t0, 2(a0)
addi t0, zero, 0x44
sb t0, 3(a0)
#
# Load back as a 32-bit word (little-endian): 0x44332211
lw t1, 0(a0)
#
# Store that word to [0x404..0x407], then read each byte with lbu
sw t1, 4(a0)
lbu t2, 4(a0)
lbu t3, 5(a0)
lbu t4, 6(a0)
lbu t5, 7(a0)
#
# Add bytes: 0x11+0x22+0x33+0x44 = 0xAA
add t6, t2, t3
add t6, t6, t4
add t6, t6, t5
#
# Store/check the sum as a byte
sb t6, 8(a0)
lbu s0, 8(a0)
#
# Halt: jump to itself (this jalr is at PC=80)
jalr zero, 80(zero)
#
# ------------- Expected results -------------
# Registers at end (before the last jalr loops):
# a0 = 0x00000400
# t1 = 0x44332211
# t2 = 0x00000011
# t3 = 0x00000022
# t4 = 0x00000033
# t5 = 0x00000044
# t6 = 0x000000aa
# s0 = 0x000000aa
#
# Memory (byte) expected:
# [0x0400] = 0x11
# [0x0401] = 0x22
# [0x0402] = 0x33
# [0x0403] = 0x44
# [0x0404] = 0x11
# [0x0405] = 0x22
# [0x0406] = 0x33
# [0x0407] = 0x44
# [0x0408] = 0xAA
