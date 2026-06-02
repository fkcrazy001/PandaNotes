
# test lui and add asm for mini rv

lui a0, 1 # 4k

lui ra, 2  # 8k

add ra, ra, a0 # ra = 12k

# halt
jalr zero, 12(zero)