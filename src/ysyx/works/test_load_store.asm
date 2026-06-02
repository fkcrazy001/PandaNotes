## test load and store for mini-rv 
# store 0x12345678 into memory 0 at ram
# use lw to read to ra, then lbu to read

# sb 0xdeadbeef into memory 0x4 at ram
# use lw to read to ra, then lbu to read

## avaible cmd now is addi,lui,add,sw,sb,lw,lbu

# a1 作为基址寄存器，指向 RAM 起始地址 0
addi a1, x0, 0          # x1 = 0

# 构造常量 0x12345678 存入 x2
lui  x2, 0x12345        # x2 = 0x12345_000
addi x2, x2, 0x678      # x2 = 0x12345_678 = 0x12345678

# store word 到内存地址 0
sw   x2, 0(a1)          # MEM[0x0..0x3] = 0x12345678

# 用 lw 读回到 x3
lw   a0, 0(a1)          # x3 应该变成 0x12345678

# 用 lbu 读各个字节（假设小端：最低地址存最低字节 0x78）
lbu  ra, 0(a1)          # x4 = MEM[0]  = 0x78
lbu  ra, 1(a1)          # x5 = MEM[1]  = 0x56
lbu  ra, 2(a1)          # x6 = MEM[2]  = 0x34
lbu  ra, 3(a1)          # x7 = MEM[3]  = 0x12

# load 0x87654321 到ram 地址0x4
addi a1,a1,4
lui ra, 0x87654
addi ra, ra, 0x321
sb ra, 0(a1)
sb ra, 1(a1)
sb ra, 2(a1)
sb ra, 3(a1)


jalr zero, 64(zero)