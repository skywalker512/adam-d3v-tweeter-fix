"""Pure-Python ARMv6-M interpreter, just big enough to run the D3V application.

No dependencies.  Peripherals are supplied by the caller through io_read/io_write.
Correctness is checked by kit/test_emu.py: the firmware's own soft-float pow()
must reproduce Python's math.pow for every volume step, and the bit-banged I2C
stream must replay the DSP image stored in the firmware byte for byte.
"""
import struct

M = 0xFFFFFFFF


class Halt(Exception):
    pass


class CPU:
    def __init__(self, flash: bytearray, ram_size=0x2000, vectors=0x2000):
        self.flash, self.ram = flash, bytearray(ram_size)
        self.r = [0] * 16
        self.n = self.z = self.c = self.v = 0
        self.primask = 0
        self.in_irq = 0
        self.cycles = 0
        self.vectors = vectors
        self.io_read = lambda a, size: 0
        self.io_write = lambda a, v, size: None
        self.r[13] = self.rd(vectors, 4)
        self.r[15] = self.rd(vectors + 4, 4) & ~1
        self.tbl = [self.sh, self.sh, self.sh, self.addsub, self.imm8, self.imm8, self.imm8, self.imm8,
                    self.alu_misc, self.ldr_lit, self.ldst_reg, self.ldst_reg, self.ldst_imm, self.ldst_imm,
                    self.ldst_imm, self.ldst_imm, self.ldst_h, self.ldst_h, self.ldst_sp, self.ldst_sp,
                    self.adr, self.add_sp, self.misc, self.misc, self.stm, self.ldm, self.bcond, self.bcond,
                    self.b, self.bad, self.wide, self.bad]

    # ---- memory -------------------------------------------------------------
    def rd(self, a, size):
        if a < len(self.flash):
            return int.from_bytes(self.flash[a:a + size], 'little')
        o = a - 0x20000000
        if 0 <= o < len(self.ram):
            return int.from_bytes(self.ram[o:o + size], 'little')
        return self.io_read(a, size) & ((1 << 8 * size) - 1)

    def wr(self, a, v, size):
        o = a - 0x20000000
        if 0 <= o < len(self.ram):
            self.ram[o:o + size] = (v & ((1 << 8 * size) - 1)).to_bytes(size, 'little')
        elif a < len(self.flash):
            raise Halt('write to flash %08x at pc %08x' % (a, self.r[15]))
        else:
            self.io_write(a, v & ((1 << 8 * size) - 1), size)

    # ---- helpers ------------------------------------------------------------
    def nz(self, x):
        self.n, self.z = x >> 31, x == 0
        return x

    def add(self, x, y, c):
        s = x + y + c
        r = s & M
        self.c = s >> 32
        self.v = (~(x ^ y) & (x ^ r)) >> 31 & 1
        return self.nz(r)

    def branch(self, t):
        if t >= 0xFFFFFFF0:                       # EXC_RETURN
            sp = self.r[13]
            f = struct.unpack("<8I",
                              b''.join(self.rd(sp + 4 * i, 4).to_bytes(4, 'little') for i in range(8)))
            self.r[0:4] = f[0:4]
            self.r[12], self.r[14], self.r[15] = f[4], f[5], f[6] & ~1
            x = f[7]
            self.n, self.z, self.c, self.v = x >> 31, x >> 30 & 1, x >> 29 & 1, x >> 28 & 1
            self.r[13] = sp + 32
            self.in_irq = 0
        else:
            self.r[15] = t & ~1

    def irq(self, num):
        """Take external interrupt `num` (exception 16+num) if possible."""
        if self.in_irq or self.primask:
            return False
        sp = self.r[13] - 32
        xpsr = self.n << 31 | self.z << 30 | self.c << 29 | self.v << 28 | 1 << 24
        for i, v in enumerate(self.r[0:4] + [self.r[12], self.r[14], self.r[15], xpsr]):
            self.wr(sp + 4 * i, v, 4)
        self.r[13], self.r[14] = sp, 0xFFFFFFF9
        self.r[15] = self.rd(self.vectors + 4 * (16 + num), 4) & ~1
        self.in_irq = 1
        return True

    def call(self, addr, *args, limit=5_000_000):
        """Run one firmware function to completion (AAPCS, r0..r3 args)."""
        saved = (self.r[:], self.n, self.z, self.c, self.v)
        self.r[0:len(args)] = [a & M for a in args]
        self.r[14], self.r[15] = 0xDEAD0001, addr & ~1
        n = 0
        while self.r[15] != 0xDEAD0000:
            self.step()
            n += 1
            if n > limit:
                raise Halt('call %x did not return' % addr)
        out = self.r[0], self.r[1]
        self.r, (self.n, self.z, self.c, self.v) = saved[0], saved[1:]
        return out

    def step(self):
        pc = self.r[15]
        h = self.flash[pc] | self.flash[pc + 1] << 8
        self.r[15] = pc + 2
        self.cycles += 1
        self.tbl[h >> 11](h, pc)

    def bad(self, h, pc):
        raise Halt('undefined instruction %04x at %08x' % (h, pc))

    # ---- instruction groups -------------------------------------------------
    def sh(self, h, pc):
        r, op, n, x = self.r, h >> 11, h >> 6 & 31, self.r[h >> 3 & 7]
        if op == 0:
            if n:
                self.c = x >> (32 - n) & 1
                x = x << n & M
        elif op == 1:
            n = n or 32
            self.c = x >> (n - 1) & 1
            x = x >> n
        else:
            n = n or 32
            s = x - (1 << 32) if x >> 31 else x
            self.c = s >> (n - 1) & 1
            x = (s >> n) & M
        r[h & 7] = self.nz(x)

    def addsub(self, h, pc):
        r = self.r
        y = (h >> 6 & 7) if h >> 10 & 1 else r[h >> 6 & 7]
        x = r[h >> 3 & 7]
        r[h & 7] = self.add(x, ~y & M, 1) if h >> 9 & 1 else self.add(x, y, 0)

    def imm8(self, h, pc):
        r, op, d, i = self.r, h >> 11 & 3, h >> 8 & 7, h & 0xff
        if op == 0:
            r[d] = self.nz(i)
        elif op == 1:
            self.add(r[d], ~i & M, 1)
        elif op == 2:
            r[d] = self.add(r[d], i, 0)
        else:
            r[d] = self.add(r[d], ~i & M, 1)

    def alu_misc(self, h, pc):
        r = self.r
        if h >> 10 == 0x10:
            op, d = h >> 6 & 15, h & 7
            x, y = r[d], r[h >> 3 & 7]
            if op == 0: r[d] = self.nz(x & y)
            elif op == 1: r[d] = self.nz(x ^ y)
            elif op in (2, 3, 4, 7):
                n = y & 0xff
                if op == 2:
                    if n:
                        self.c = x >> (32 - n) & 1 if n <= 32 else 0
                        x = x << n & M if n < 32 else 0
                elif op == 3:
                    if n:
                        self.c = x >> (n - 1) & 1 if n <= 32 else 0
                        x = x >> n if n < 32 else 0
                elif op == 4:
                    if n:
                        s = x - (1 << 32) if x >> 31 else x
                        n = min(n, 32)
                        self.c = s >> (n - 1) & 1
                        x = (s >> n) & M
                else:
                    if n:
                        n &= 31
                        x = (x >> n | x << (32 - n)) & M if n else x
                        self.c = x >> 31
                r[d] = self.nz(x)
            elif op == 5: r[d] = self.add(x, y, self.c)
            elif op == 6: r[d] = self.add(x, ~y & M, self.c)
            elif op == 8: self.nz(x & y)
            elif op == 9: r[d] = self.add(~y & M, 0, 1)
            elif op == 10: self.add(x, ~y & M, 1)
            elif op == 11: self.add(x, y, 0)
            elif op == 12: r[d] = self.nz(x | y)
            elif op == 13: r[d] = self.nz(x * y & M)
            elif op == 14: r[d] = self.nz(x & ~y & M)
            else: r[d] = self.nz(~y & M)
            return
        op, m, d = h >> 8 & 3, h >> 3 & 15, (h >> 4 & 8) | (h & 7)
        y = pc + 4 if m == 15 else r[m]
        if op == 3:
            if h & 0x80:
                r[14] = (pc + 2) | 1
            self.branch(y)
        elif op == 1:
            self.add(pc + 4 if d == 15 else r[d], ~y & M, 1)
        else:
            x = (((pc + 4 if d == 15 else r[d]) + y) if op == 0 else y) & M
            if d == 15:
                self.branch(x)
            else:
                r[d] = x

    def ldr_lit(self, h, pc):
        self.r[h >> 8 & 7] = self.rd(((pc + 4) & ~3) + (h & 0xff) * 4, 4)

    def ldst_reg(self, h, pc):
        r, op = self.r, h >> 9 & 7
        a, t = (r[h >> 3 & 7] + r[h >> 6 & 7]) & M, h & 7
        if op == 0: self.wr(a, r[t], 4)
        elif op == 1: self.wr(a, r[t], 2)
        elif op == 2: self.wr(a, r[t], 1)
        elif op == 3:
            v = self.rd(a, 1); r[t] = v | 0xFFFFFF00 if v & 0x80 else v
        elif op == 4: r[t] = self.rd(a, 4)
        elif op == 5: r[t] = self.rd(a, 2)
        elif op == 6: r[t] = self.rd(a, 1)
        else:
            v = self.rd(a, 2); r[t] = v | 0xFFFF0000 if v & 0x8000 else v

    def ldst_imm(self, h, pc):
        r, b, i = self.r, h >> 12 & 1, h >> 6 & 31
        size = 1 if b else 4
        a = (r[h >> 3 & 7] + i * size) & M
        if h >> 11 & 1:
            r[h & 7] = self.rd(a, size)
        else:
            self.wr(a, r[h & 7], size)

    def ldst_h(self, h, pc):
        r = self.r
        a = (r[h >> 3 & 7] + (h >> 6 & 31) * 2) & M
        if h >> 11 & 1:
            r[h & 7] = self.rd(a, 2)
        else:
            self.wr(a, r[h & 7], 2)

    def ldst_sp(self, h, pc):
        a = self.r[13] + (h & 0xff) * 4
        if h >> 11 & 1:
            self.r[h >> 8 & 7] = self.rd(a, 4)
        else:
            self.wr(a, self.r[h >> 8 & 7], 4)

    def adr(self, h, pc):
        self.r[h >> 8 & 7] = ((pc + 4) & ~3) + (h & 0xff) * 4

    def add_sp(self, h, pc):
        self.r[h >> 8 & 7] = (self.r[13] + (h & 0xff) * 4) & M

    def misc(self, h, pc):
        r, top = self.r, h >> 8
        if top == 0xB0:
            r[13] = (r[13] + (-(h & 0x7f) * 4 if h & 0x80 else (h & 0x7f) * 4)) & M
        elif top == 0xB2:
            x, op = r[h >> 3 & 7], h >> 6 & 3
            if op == 0: x &= 0xffff; x |= 0xFFFF0000 if x & 0x8000 else 0
            elif op == 1: x &= 0xff; x |= 0xFFFFFF00 if x & 0x80 else 0
            elif op == 2: x &= 0xffff
            else: x &= 0xff
            r[h & 7] = x
        elif top in (0xB4, 0xB5):
            regs = [i for i in range(8) if h >> i & 1] + ([14] if h & 0x100 else [])
            sp = r[13] - 4 * len(regs)
            for k, i in enumerate(regs):
                self.wr(sp + 4 * k, r[i], 4)
            r[13] = sp
        elif top in (0xBC, 0xBD):
            sp = r[13]
            for i in range(8):
                if h >> i & 1:
                    r[i] = self.rd(sp, 4); sp += 4
            if h & 0x100:
                t = self.rd(sp, 4); sp += 4
                r[13] = sp
                self.branch(t)
            else:
                r[13] = sp
        elif h in (0xB662, 0xB672):
            self.primask = h >> 4 & 1
        elif top == 0xBA:
            x, op = r[h >> 3 & 7], h >> 6 & 3
            if op == 0: x = int.from_bytes(x.to_bytes(4, 'little'), 'big')
            elif op == 1: x = (x & 0xff00ff00) >> 8 | (x & 0x00ff00ff) << 8
            else:
                x = (x & 0xff) << 8 | (x >> 8 & 0xff); x |= 0xFFFF0000 if x & 0x8000 else 0
            r[h & 7] = x
        elif top == 0xBF and not h & 0xf:
            pass
        else:
            raise Halt('unsupported %04x at %08x' % (h, pc))

    def stm(self, h, pc):
        r, n = self.r, h >> 8 & 7
        a = r[n]
        for i in range(8):
            if h >> i & 1:
                self.wr(a, r[i], 4); a += 4
        r[n] = a

    def ldm(self, h, pc):
        r, n = self.r, h >> 8 & 7
        a = r[n]
        for i in range(8):
            if h >> i & 1:
                r[i] = self.rd(a, 4); a += 4
        if not h >> n & 1:
            r[n] = a

    def bcond(self, h, pc):
        c = h >> 8 & 15
        if c >= 14:
            raise Halt('svc/udf %04x at %08x' % (h, pc))
        n, z, cc, v = self.n, self.z, self.c, self.v
        t = (z, not z, cc, not cc, n, not n, v, not v, cc and not z, not cc or z,
             n == v, n != v, not z and n == v, z or n != v)[c]
        if t:
            o = h & 0xff
            self.r[15] = pc + 4 + ((o - 0x100 if o & 0x80 else o) << 1)

    def b(self, h, pc):
        o = h & 0x7ff
        self.r[15] = pc + 4 + ((o - 0x800 if o & 0x400 else o) << 1)

    def wide(self, h, pc):
        h2 = self.flash[pc + 2] | self.flash[pc + 3] << 8
        self.r[15] = pc + 4
        if h2 & 0xD000 == 0xD000:
            s = h >> 10 & 1
            i1, i2 = 1 - ((h2 >> 13 & 1) ^ s), 1 - ((h2 >> 11 & 1) ^ s)
            off = s << 24 | i1 << 23 | i2 << 22 | (h & 0x3ff) << 12 | (h2 & 0x7ff) << 1
            self.r[14] = (pc + 4) | 1
            self.r[15] = (pc + 4 + (off - (1 << 25) if s else off)) & M
        elif h == 0xF3EF:
            sysm = h2 & 0xff
            self.r[h2 >> 8 & 15] = {8: self.r[13], 16: self.primask}.get(sysm, 0)
        elif h & 0xFFF0 == 0xF380:
            if h2 & 0xff == 8: self.r[13] = self.r[h & 15]
            elif h2 & 0xff == 16: self.primask = self.r[h & 15] & 1
        else:
            raise Halt('unsupported wide %04x %04x at %08x' % (h, h2, pc))
