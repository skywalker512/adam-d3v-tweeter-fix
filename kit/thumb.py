"""Minimal ARMv6-M (Thumb-1) decoder that prints clang/llvm-mc compatible UAL.

Only what the D3V application needs: every instruction decodes to text that
re-assembles to the same bytes, or falls back to a raw `.inst` directive.
Control-flow and PC-relative operands are returned symbolically so the caller
can substitute labels (that is what makes the output relocatable).
"""
from dataclasses import dataclass

REG = ['r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7',
       'r8', 'r9', 'r10', 'r11', 'r12', 'sp', 'lr', 'pc']
COND = ['eq', 'ne', 'hs', 'lo', 'mi', 'pl', 'vs', 'vc', 'hi', 'ls', 'ge', 'lt', 'gt', 'le']
SYSM = {0: 'apsr', 5: 'ipsr', 8: 'msp', 9: 'psp', 16: 'primask', 20: 'control'}
ALU = ['ands', 'eors', 'lsls', 'lsrs', 'asrs', 'adcs', 'sbcs', 'rors',
       'tst', 'rsbs', 'cmp', 'cmn', 'orrs', 'muls', 'bics', 'mvns']


@dataclass
class Ins:
    addr: int
    size: int
    text: str            # '{T}' marks a symbolic operand
    kind: str = 'norm'   # norm | b | bcond | bl | ret | ind | ldrpc | adr | raw
    target: int | None = None


def _reglist(bits, extra=None):
    r = [REG[i] for i in range(8) if bits >> i & 1]
    if extra:
        r.append(extra)
    return '{' + ', '.join(r) + '}'


def decode(u16, addr):
    """u16(addr) -> halfword.  Returns Ins."""
    h = u16(addr)
    top5 = h >> 11
    if top5 in (0x1d, 0x1e, 0x1f):
        h2 = u16(addr + 2)
        if top5 == 0x1e and (h2 & 0xD000) == 0xD000:
            s = h >> 10 & 1
            i1 = 1 - ((h2 >> 13 & 1) ^ s)
            i2 = 1 - ((h2 >> 11 & 1) ^ s)
            off = s << 24 | i1 << 23 | i2 << 22 | (h & 0x3ff) << 12 | (h2 & 0x7ff) << 1
            if s:
                off -= 1 << 25
            return Ins(addr, 4, 'bl {T}', 'bl', addr + 4 + off)
        if h == 0xF3EF and h2 & 0xF000 == 0x8000 and (h2 & 0xff) in SYSM:
            return Ins(addr, 4, 'mrs %s, %s' % (REG[h2 >> 8 & 15], SYSM[h2 & 0xff]))
        if h & 0xFFF0 == 0xF380 and h2 & 0xFF00 == 0x8800 and (h2 & 0xff) in SYSM:
            return Ins(addr, 4, 'msr %s, %s' % (SYSM[h2 & 0xff], REG[h & 15]))
        return Ins(addr, 4, '.inst.w 0x%04x%04x' % (h, h2), 'raw')

    rd, rm, rn3 = h & 7, h >> 3 & 7, h >> 6 & 7
    imm5 = h >> 6 & 31
    raw = Ins(addr, 2, '.inst.n 0x%04x' % h, 'raw')

    def I(text, kind='norm', target=None):
        return Ins(addr, 2, text, kind, target)

    if top5 < 3:
        if top5 == 0 and imm5 == 0:
            return I('movs %s, %s' % (REG[rd], REG[rm]))
        return I('%s %s, %s, #%d' % (['lsls', 'lsrs', 'asrs'][top5], REG[rd], REG[rm], imm5 or 32))
    if top5 == 3:
        op = 'subs' if h >> 9 & 1 else 'adds'
        if h >> 10 & 1:
            return I('%s %s, %s, #%d' % (op, REG[rd], REG[rm], rn3))
        return I('%s %s, %s, %s' % (op, REG[rd], REG[rm], REG[rn3]))
    if top5 < 8:
        return I('%s %s, #%d' % (['movs', 'cmp', 'adds', 'subs'][top5 - 4], REG[h >> 8 & 7], h & 0xff))
    if h >> 10 == 0x10:
        op = h >> 6 & 15
        if op == 9:
            return I('rsbs %s, %s, #0' % (REG[rd], REG[rm]))
        if op == 13:
            return I('muls %s, %s, %s' % (REG[rd], REG[rm], REG[rd]))
        return I('%s %s, %s' % (ALU[op], REG[rd], REG[rm]))
    if h >> 10 == 0x11:
        op = h >> 8 & 3
        hm = h >> 3 & 15
        hd = (h >> 4 & 8) | rd
        if op == 3:
            if h & 7:
                return raw
            if h & 0x80:
                return I('blx %s' % REG[hm], 'ind')
            return I('bx %s' % REG[hm], 'ret' if hm == 14 else 'ind')
        if hd == 15 or hm == 15 or (op == 1 and hd < 8 and hm < 8):
            return Ins(addr, 2, raw.text, 'ind' if hd == 15 and op != 1 else 'raw')
        return I('%s %s, %s' % (['add', 'cmp', 'mov'][op], REG[hd], REG[hm]))
    if top5 == 9:
        return I('ldr %s, {T}' % REG[h >> 8 & 7], 'ldrpc', ((addr + 4) & ~3) + (h & 0xff) * 4)
    if h >> 12 == 5:
        op = ['str', 'strh', 'strb', 'ldrsb', 'ldr', 'ldrh', 'ldrb', 'ldrsh'][h >> 9 & 7]
        return I('%s %s, [%s, %s]' % (op, REG[rd], REG[rm], REG[rn3]))
    if h >> 13 == 3:
        b, l = h >> 12 & 1, h >> 11 & 1
        op = ('ldr' if l else 'str') + ('b' if b else '')
        return I('%s %s, [%s, #%d]' % (op, REG[rd], REG[rm], imm5 if b else imm5 * 4))
    if h >> 12 == 8:
        return I('%s %s, [%s, #%d]' % ('ldrh' if h >> 11 & 1 else 'strh', REG[rd], REG[rm], imm5 * 2))
    if h >> 12 == 9:
        return I('%s %s, [sp, #%d]' % ('ldr' if h >> 11 & 1 else 'str', REG[h >> 8 & 7], (h & 0xff) * 4))
    if h >> 12 == 10:
        if h >> 11 & 1:
            return I('add %s, sp, #%d' % (REG[h >> 8 & 7], (h & 0xff) * 4))
        return I('adr %s, {T}' % REG[h >> 8 & 7], 'adr', ((addr + 4) & ~3) + (h & 0xff) * 4)
    if h >> 12 == 11:
        if h >> 8 == 0xB0:
            return I('%s sp, #%d' % ('sub' if h & 0x80 else 'add', (h & 0x7f) * 4))
        if h >> 8 == 0xB2:
            return I('%s %s, %s' % (['sxth', 'sxtb', 'uxth', 'uxtb'][h >> 6 & 3], REG[rd], REG[rm]))
        if h >> 9 == 0x5A and h & 0x1ff:
            return I('push ' + _reglist(h & 0xff, 'lr' if h & 0x100 else None))
        if h >> 9 == 0x5E and h & 0x1ff:
            return I('pop ' + _reglist(h & 0xff, 'pc' if h & 0x100 else None), 'ret' if h & 0x100 else 'norm')
        if h in (0xB662, 0xB672):
            return I('cpsid i' if h & 0x10 else 'cpsie i')
        if h >> 8 == 0xBA and (h >> 6 & 3) != 2:
            return I('%s %s, %s' % (['rev', 'rev16', '', 'revsh'][h >> 6 & 3], REG[rd], REG[rm]))
        if h >> 8 == 0xBE:
            return I('bkpt #%d' % (h & 0xff))
        if h >> 8 == 0xBF and h & 0xf == 0 and (h >> 4 & 15) < 5:
            return I(['nop', 'yield', 'wfe', 'wfi', 'sev'][h >> 4 & 15])
        return raw
    if h >> 12 == 12:
        rn = h >> 8 & 7
        if not h & 0xff:
            return raw
        if h >> 11 & 1:
            wb = '' if h >> rn & 1 else '!'
            return I('ldm %s%s, %s' % (REG[rn], wb, _reglist(h & 0xff)))
        return I('stm %s!, %s' % (REG[rn], _reglist(h & 0xff)))
    if h >> 12 == 13:
        c = h >> 8 & 15
        if c == 15:
            return I('svc #%d' % (h & 0xff))
        if c == 14:
            return raw
        off = h & 0xff
        if off & 0x80:
            off -= 0x100
        return I('b%s {T}' % COND[c], 'bcond', addr + 4 + off * 2)
    if top5 == 0x1c:
        off = h & 0x7ff
        if off & 0x400:
            off -= 0x800
        return I('b {T}', 'b', addr + 4 + off * 2)
    return raw
