

from typing import List


class Cpu:
    pc=0
    regs=[0]*4

    def li(self, idx,v):
        self.regs[idx] = v
    
    def add(self, d,f,to):
        self.regs[d] = self.regs[f]+self.regs[to]
    
    def bner0(self, idx,addr):
        if self.regs[0] != self.regs[idx]:
            self.pc = addr
            return True
        return False

    def print(self):
        print(f"({self.pc},{self.regs[0]},{self.regs[1]},{self.regs[2]},{self.regs[3]})")

    def run_dump(self,progrom,lc=40):
        while self.pc < len(progrom) and lc:
            self.print()
            pre_pc = self.pc
            op = progrom[self.pc]
            # add
            jump = False
            if op[0] == 0:
                self.add(op[1],op[2],op[3])
            elif op[0] == 2:
                self.li(op[1],op[2])
            elif op[0] == 3:
                jump = self.bner0(op[1],op[2])
            
            if not jump:
                self.pc+=1
            lc-=1
    def get_rindex(self,s:str)->int:
        if not s.lower().startswith('r'):
            print(f"invalid reg {s}")
            exit(1)
        return int(s[1:].strip(','))
    def get_imm(self,s):
        return int(s)
    
    def load_asm(self,asms: List[str])->List[List[int]]:
        p = []
        for opcode in asms:
            opcode = opcode.lower().strip()
            op = opcode.split(" ")
            if op[0]== 'li':
                p.append([2,self.get_rindex(op[1]),self.get_imm(op[2])])
            elif op[0] == 'add':
                p.append([0,self.get_rindex(op[1]), self.get_rindex(op[2]),self.get_rindex(op[3])])
            elif op[0] == 'bner0':
                p.append([3,self.get_rindex(op[1]),self.get_imm(op[2])])
            else:
                print(f"invalid opcode {op}")
                exit(1)
        return p
    def run_asm(self, asms: List[str]):
        self.run_dump(self.load_asm(asms))

cpu = Cpu()
# cpu.run_asm([
#     "li r0, 10   # 这里是十进制的10",
#     "li r1, 0",
#     "li r2, 0",
#     "li r3, 1",
#     "add r1, r1, r3",
#     "add r2, r2, r1",
#     "bner0 r1, 4",
#     "bner0 r3, 7"
# ])

# 验证奇数求和
cpu.run_asm([
" li r0, 11",
" li r1, 1",
" li r2, 0",
" li r3, 2",
" add r2, r2, r1",
" add r1, r1, r3",
" bner0 r1, 4",
" bner0 r3, 7",
])