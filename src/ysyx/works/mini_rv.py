from typing import List
import sys
import re

class MiniRV:
    def __init__(self):
        self.fp = None
        self.ins = []
        self.labels = {}
        self.cur_pc = 0
        self.parser = {}
        self.__init_parser()
        self.abi_to_x = {
            "zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
            "t0": 5, "t1": 6, "t2": 7,
            "s0": 8, "fp": 8, "s1": 9,
            "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15, "a6": 16, "a7": 17,
            "s2": 18, "s3": 19, "s4": 20, "s5": 21, "s6": 22, "s7": 23, "s8": 24, "s9": 25, "s10": 26, "s11": 27,
            "t3": 28, "t4": 29, "t5": 30, "t6": 31,
        }

    def __init_parser(self):
        self.parser = {
            "lui": self.__parse_lui,
            "auipc": self.__parse_auipc,
            "jal": self.__parse_jal,
            "jalr": self.__parse_jalr,
            "beq": lambda c: self.__parse_branch(c, 0b000),
            "bne": lambda c: self.__parse_branch(c, 0b001),
            "blt": lambda c: self.__parse_branch(c, 0b100),
            "bge": lambda c: self.__parse_branch(c, 0b101),
            "bltu": lambda c: self.__parse_branch(c, 0b110),
            "bgeu": lambda c: self.__parse_branch(c, 0b111),
            "lb": lambda c: self.__parse_load(c, 0b000),
            "lh": lambda c: self.__parse_load(c, 0b001),
            "lw": lambda c: self.__parse_load(c, 0b010),
            "lbu": lambda c: self.__parse_load(c, 0b100),
            "lhu": lambda c: self.__parse_load(c, 0b101),
            "sb": lambda c: self.__parse_store(c, 0b000),
            "sh": lambda c: self.__parse_store(c, 0b001),
            "sw": lambda c: self.__parse_store(c, 0b010),
            "addi": lambda c: self.__parse_itype_alu(c, 0b000),
            "slti": lambda c: self.__parse_itype_alu(c, 0b010),
            "sltiu": lambda c: self.__parse_itype_alu(c, 0b011),
            "xori": lambda c: self.__parse_itype_alu(c, 0b100),
            "ori": lambda c: self.__parse_itype_alu(c, 0b110),
            "andi": lambda c: self.__parse_itype_alu(c, 0b111),
            "slli": lambda c: self.__parse_shift_imm(c, 0b001, 0b0000000),
            "srli": lambda c: self.__parse_shift_imm(c, 0b101, 0b0000000),
            "srai": lambda c: self.__parse_shift_imm(c, 0b101, 0b0100000),
            "add": lambda c: self.__parse_rtype_alu(c, 0b000, 0b0000000),
            "sub": lambda c: self.__parse_rtype_alu(c, 0b000, 0b0100000),
            "sll": lambda c: self.__parse_rtype_alu(c, 0b001, 0b0000000),
            "slt": lambda c: self.__parse_rtype_alu(c, 0b010, 0b0000000),
            "sltu": lambda c: self.__parse_rtype_alu(c, 0b011, 0b0000000),
            "xor": lambda c: self.__parse_rtype_alu(c, 0b100, 0b0000000),
            "srl": lambda c: self.__parse_rtype_alu(c, 0b101, 0b0000000),
            "sra": lambda c: self.__parse_rtype_alu(c, 0b101, 0b0100000),
            "or": lambda c: self.__parse_rtype_alu(c, 0b110, 0b0000000),
            "and": lambda c: self.__parse_rtype_alu(c, 0b111, 0b0000000),
            "ecall": self.__parse_ecall,
            "ebreak": self.__parse_ebreak,
            "fence": self.__parse_fence,
            "fence.i": self.__parse_fence_i,
        }

    # ---------- 小工具 ----------
    def __clean(self, s: str) -> str:
        # 去掉常见分隔符（保留括号以便 jalr 解析 imm(rs1)）
        return s.strip().lower().rstrip(',')

    def __parse_reg(self, token: str) -> int:
        t = self.__clean(token)
        if t.startswith('x') and t[1:].isdigit():
            x = int(t[1:])
            if not (0 <= x <= 31):
                raise ValueError(f"寄存器超范围: {token}")
            return x
        if t not in self.abi_to_x:
            raise ValueError(f"未知寄存器: {token}")
        return self.abi_to_x[t]

    def __parse_imm_or_label(self, token: str) -> int:
        t = self.__clean(token)
        if t in self.labels:
            return int(self.labels[t])
        return self.__parse_imm(token)

    def __parse_imm(self, token: str) -> int:
        t = self.__clean(token)
        # 支持 10/16 进制：1, -16, 0xff, -0x10
        try:
            return int(t, 0)
        except Exception:
            raise ValueError(f"非法立即数: {token}")

    def __simm(self, imm: int, bits: int) -> int:
        lo = -(1 << (bits - 1))
        hi = (1 << (bits - 1)) - 1
        if imm < lo or imm > hi:
            raise ValueError(f"{bits}位有符号立即数超范围: {imm}")
        return imm & ((1 << bits) - 1)

    def __imm12(self, imm: int) -> int:
        # I-type signed 12-bit: [-2048, 2047]
        if imm < -2048 or imm > 2047:
            raise ValueError(f"I-type 12位立即数超范围: {imm}")
        return imm & 0xFFF

    def __uimm20(self, imm: int) -> int:
        # U-type 20-bit（直接放到[31:12]），这里允许传负数并按 20bit 截断
        if imm < -(1 << 19) or imm > ((1 << 20) - 1):
            # 这里的范围策略你也可以改成只允许 [0, 2^20-1]
            raise ValueError(f"U-type 20位立即数建议范围: {imm}")
        return imm & 0xFFFFF

    def __to_hex32(self, inst: int) -> str:
        return f"0x{inst & 0xFFFFFFFF:08x}"

    def __encode_r(self, opcode: int, funct3: int, funct7: int, rd: int, rs1: int, rs2: int) -> int:
        return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

    def __encode_i(self, opcode: int, funct3: int, rd: int, rs1: int, imm12: int) -> int:
        return (imm12 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

    def __encode_s(self, opcode: int, funct3: int, rs1: int, rs2: int, imm12: int) -> int:
        imm11_5 = (imm12 >> 5) & 0x7F
        imm4_0 = imm12 & 0x1F
        return (imm11_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (imm4_0 << 7) | opcode

    def __encode_b(self, opcode: int, funct3: int, rs1: int, rs2: int, imm13: int) -> int:
        b12 = (imm13 >> 12) & 0x1
        b10_5 = (imm13 >> 5) & 0x3F
        b4_1 = (imm13 >> 1) & 0xF
        b11 = (imm13 >> 11) & 0x1
        return (b12 << 31) | (b10_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (b4_1 << 8) | (b11 << 7) | opcode

    def __encode_u(self, opcode: int, rd: int, imm20: int) -> int:
        return (imm20 << 12) | (rd << 7) | opcode

    def __encode_j(self, opcode: int, rd: int, imm21: int) -> int:
        j20 = (imm21 >> 20) & 0x1
        j10_1 = (imm21 >> 1) & 0x3FF
        j11 = (imm21 >> 11) & 0x1
        j19_12 = (imm21 >> 12) & 0xFF
        return (j20 << 31) | (j10_1 << 21) | (j11 << 20) | (j19_12 << 12) | (rd << 7) | opcode

    def __parse_mem(self, token: str):
        t = self.__clean(token)
        m = re.fullmatch(r'([+-]?(?:0x[0-9a-f]+|\d+))?\(([^)]+)\)', t)
        if not m:
            raise ValueError(f"期望 imm(rs1) 形式，实际: {token}")
        imm_str, rs1_str = m.group(1), m.group(2)
        imm = 0 if imm_str is None or imm_str == "" else int(imm_str, 0)
        rs1 = self.__parse_reg(rs1_str)
        return rs1, imm

    # ---------- 需要你完善的 4 个解析函数 ----------
    def __parse_add(self, codes: List[str]):
        # add rd, rs1, rs2  (R-type)
        if len(codes) != 3:
            raise ValueError(f"add 操作数数量错误: {codes}")
        rd, rs1, rs2 = (self.__parse_reg(codes[0]),
                        self.__parse_reg(codes[1]),
                        self.__parse_reg(codes[2]))

        opcode = 0b0110011
        funct3 = 0b000
        funct7 = 0b0000000
        inst = self.__encode_r(opcode, funct3, funct7, rd, rs1, rs2)
        return self.__to_hex32(inst)

    def __parse_addi(self, codes: List[str]):
        # addi rd, rs1, imm (I-type)
        if len(codes) != 3:
            raise ValueError(f"addi 操作数数量错误: {codes}")
        rd = self.__parse_reg(codes[0])
        rs1 = self.__parse_reg(codes[1])
        imm = self.__imm12(self.__parse_imm(codes[2]))

        opcode = 0b0010011
        funct3 = 0b000
        inst = self.__encode_i(opcode, funct3, rd, rs1, imm)
        return self.__to_hex32(inst)

    def __parse_lui(self, codes: List[str]):
        # lui rd, imm20 (U-type)
        if len(codes) != 2:
            raise ValueError(f"lui 操作数数量错误: {codes}")
        rd = self.__parse_reg(codes[0])
        imm20 = self.__uimm20(self.__parse_imm(codes[1]))

        opcode = 0b0110111
        inst = self.__encode_u(opcode, rd, imm20)
        return self.__to_hex32(inst)

    def __parse_auipc(self, codes: List[str]):
        if len(codes) != 2:
            raise ValueError(f"auipc 操作数数量错误: {codes}")
        rd = self.__parse_reg(codes[0])
        imm20 = self.__uimm20(self.__parse_imm(codes[1]))
        opcode = 0b0010111
        inst = self.__encode_u(opcode, rd, imm20)
        return self.__to_hex32(inst)

    def __parse_jalr(self, codes: List[str]):
        # jalr 常见两种写法：
        # 1) jalr rd, imm(rs1)
        # 2) jalr rd, rs1, imm
        if len(codes) == 2:
            rd = self.__parse_reg(codes[0])
            rs1, imm_raw = self.__parse_mem(codes[1])
            imm = self.__imm12(imm_raw)

        elif len(codes) == 3:
            rd = self.__parse_reg(codes[0])
            rs1 = self.__parse_reg(codes[1])
            imm = self.__imm12(self.__parse_imm(codes[2]))

        else:
            raise ValueError(f"jalr 操作数数量错误: {codes}")

        opcode = 0b1100111
        funct3 = 0b000
        inst = self.__encode_i(opcode, funct3, rd, rs1, imm)
        return self.__to_hex32(inst)

    def __parse_jal(self, codes: List[str]):
        if len(codes) == 1:
            rd = 1
            target = codes[0]
        elif len(codes) == 2:
            rd = self.__parse_reg(codes[0])
            target = codes[1]
        else:
            raise ValueError(f"jal 操作数数量错误: {codes}")
        imm = self.__parse_imm_or_label(target)
        if self.__clean(target) in self.labels:
            imm = imm - self.cur_pc
        if imm % 2 != 0:
            raise ValueError(f"jal 立即数需要 2 对齐: {imm}")
        imm21 = self.__simm(imm, 21)
        opcode = 0b1101111
        inst = self.__encode_j(opcode, rd, imm21)
        return self.__to_hex32(inst)

    def __parse_branch(self, codes: List[str], funct3: int):
        if len(codes) != 3:
            raise ValueError(f"branch 操作数数量错误: {codes}")
        rs1 = self.__parse_reg(codes[0])
        rs2 = self.__parse_reg(codes[1])
        target = codes[2]
        imm = self.__parse_imm_or_label(target)
        if self.__clean(target) in self.labels:
            imm = imm - self.cur_pc
        if imm % 2 != 0:
            raise ValueError(f"branch 立即数需要 2 对齐: {imm}")
        imm13 = self.__simm(imm, 13)
        opcode = 0b1100011
        inst = self.__encode_b(opcode, funct3, rs1, rs2, imm13)
        return self.__to_hex32(inst)

    def __parse_load(self, codes: List[str], funct3: int):
        if len(codes) != 2:
            raise ValueError(f"load 操作数数量错误: {codes}")
        rd = self.__parse_reg(codes[0])
        rs1, imm_raw = self.__parse_mem(codes[1])
        imm12 = self.__imm12(imm_raw)
        opcode = 0b0000011
        inst = self.__encode_i(opcode, funct3, rd, rs1, imm12)
        return self.__to_hex32(inst)

    def __parse_store(self, codes: List[str], funct3: int):
        if len(codes) != 2:
            raise ValueError(f"store 操作数数量错误: {codes}")
        rs2 = self.__parse_reg(codes[0])
        rs1, imm_raw = self.__parse_mem(codes[1])
        imm12 = self.__imm12(imm_raw)
        opcode = 0b0100011
        inst = self.__encode_s(opcode, funct3, rs1, rs2, imm12)
        return self.__to_hex32(inst)

    def __parse_itype_alu(self, codes: List[str], funct3: int):
        if len(codes) != 3:
            raise ValueError(f"I-type 操作数数量错误: {codes}")
        rd = self.__parse_reg(codes[0])
        rs1 = self.__parse_reg(codes[1])
        imm12 = self.__imm12(self.__parse_imm_or_label(codes[2]))
        opcode = 0b0010011
        inst = self.__encode_i(opcode, funct3, rd, rs1, imm12)
        return self.__to_hex32(inst)

    def __parse_shift_imm(self, codes: List[str], funct3: int, funct7: int):
        if len(codes) != 3:
            raise ValueError(f"shift 操作数数量错误: {codes}")
        rd = self.__parse_reg(codes[0])
        rs1 = self.__parse_reg(codes[1])
        shamt = self.__parse_imm(codes[2])
        if shamt < 0 or shamt > 31:
            raise ValueError(f"shamt 超范围: {shamt}")
        imm12 = ((funct7 & 0x7F) << 5) | (shamt & 0x1F)
        opcode = 0b0010011
        inst = self.__encode_i(opcode, funct3, rd, rs1, imm12)
        return self.__to_hex32(inst)

    def __parse_rtype_alu(self, codes: List[str], funct3: int, funct7: int):
        if len(codes) != 3:
            raise ValueError(f"R-type 操作数数量错误: {codes}")
        rd = self.__parse_reg(codes[0])
        rs1 = self.__parse_reg(codes[1])
        rs2 = self.__parse_reg(codes[2])
        opcode = 0b0110011
        inst = self.__encode_r(opcode, funct3, funct7, rd, rs1, rs2)
        return self.__to_hex32(inst)

    def __parse_ecall(self, codes: List[str]):
        if len(codes) != 0:
            raise ValueError(f"ecall 不需要操作数: {codes}")
        return self.__to_hex32(0x00000073)

    def __parse_ebreak(self, codes: List[str]):
        if len(codes) != 0:
            raise ValueError(f"ebreak 不需要操作数: {codes}")
        return self.__to_hex32(0x00100073)

    def __parse_fence(self, codes: List[str]):
        if len(codes) != 0:
            raise ValueError(f"fence 暂仅支持无操作数形式: {codes}")
        return self.__to_hex32(0x0000000F)

    def __parse_fence_i(self, codes: List[str]):
        if len(codes) != 0:
            raise ValueError(f"fence.i 暂仅支持无操作数形式: {codes}")
        return self.__to_hex32(0x0000100F)

    def __strip_comment(self, line: str) -> str:
        return line.split("#", 1)[0]

    def __parse_line(self, line: str):
        labels = []
        s = line.strip()
        while True:
            m = re.match(r'^([a-zA-Z_][\w\.]*):', s)
            if not m:
                break
            labels.append(m.group(1).lower())
            s = s[m.end():].lstrip()
        if s == "":
            return labels, None
        parts = s.split(None, 1)
        mnemonic = parts[0].lower()
        ops_str = parts[1] if len(parts) > 1 else ""
        ops = [op.strip() for op in ops_str.split(",") if op.strip() != ""]
        return labels, (mnemonic, ops)

    def load_ins_from_file(self, fp: str):
        self.ins = []
        self.fp = fp
        self.labels = {}
        self.cur_pc = 0
        items = []
        pc = 0
        with open(fp,'r') as f:
            for line in f:
                line = self.__strip_comment(line).strip()
                if line == "":
                    continue
                labels, inst = self.__parse_line(line)
                for lb in labels:
                    if lb in self.labels:
                        raise ValueError(f"重复 label: {lb}")
                    self.labels[lb] = pc
                if inst is None:
                    continue
                mnemonic, ops = inst
                items.append((pc, mnemonic, ops))
                pc += 4
        for pc, mnemonic, ops in items:
            if mnemonic not in self.parser:
                raise ValueError(f"未知指令: {mnemonic}")
            self.cur_pc = pc
            self.ins.append(self.parser[mnemonic](ops))

    def save_hex_to_file(self, fp: str):
        """
        保存指令到文件，供 Logisim-Evolution ROM 直接加载。
        - fp 以 .bin 结尾：写二进制(每条指令4字节 little-endian)
        - 否则：写 Logisim-Evolution 的 v2.0 raw 文本格式（推荐，Data Bit Width=32 时每个 word 8 hex）
        """
        def to_u32(ins, idx: int) -> int:
            if ins is None:
                raise ValueError(f"第 {idx} 条指令为空，可能解析函数未返回结果")
            if isinstance(ins, int):
                return ins & 0xFFFFFFFF
            if isinstance(ins, str):
                s = ins.strip().lower()
                if s.startswith("0x"):
                    s = s[2:]
                return int(s, 16) & 0xFFFFFFFF
            raise TypeError(f"不支持的指令类型: {type(ins)}（第 {idx} 条）")

        if fp.lower().endswith(".bin"):
            with open(fp, "wb") as f:
                for i, ins in enumerate(self.ins):
                    val = to_u32(ins, i)
                    f.write(val.to_bytes(4, byteorder="little", signed=False))
        else:
            # Logisim-Evolution: v2.0 raw
            with open(fp, "w", encoding="utf-8") as f:
                f.write("v2.0 raw\n")
                for i, ins in enumerate(self.ins):
                    val = to_u32(ins, i)
                    f.write(f"{val:08x}")
                    f.write("\n")  # 也可以改成空格分隔；换行最直观

    def run(self):
        raise NotImplementedError
    

if __name__ == "__main__":
    mini_rv = MiniRV()
    mini_rv.load_ins_from_file(sys.argv[1])
    mini_rv.save_hex_to_file(sys.argv[2] if len(sys.argv)>=3 else "output.bin")
