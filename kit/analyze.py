"""Recursive-descent analysis of the D3V MCU application image."""
import struct
from pathlib import Path
from thumb import decode

ROOT = Path(__file__).resolve().parent.parent
FW = ROOT / 'fw' / 'D3V_MCU+DSP_V1_7_RC4.bin'
BASE = 0x2000
SWITCH8 = 0x3c82          # __ARM_common_switch8_thumb: byte table follows the BL
NORETURN = {0x20c8}         # __rt_entry -> main never returns; a literal pool follows the BL
REGION_TABLE = (0x7538, 0x7558)   # Keil scatter-load table: {src, dst, len, handler} x N


class Image:
    def __init__(self, path=FW):
        self.data = Path(path).read_bytes()
        self.end = BASE + len(self.data)
        self.ins = {}          # addr -> Ins
        self.switch = {}       # table addr -> (count, [targets])
        self.lit = {}          # literal word addr -> set(referencing ins addr)
        self.adr = set()       # adr targets
        self.code_ptr_words = set()   # addresses of 32-bit words that hold code pointers
        self.analyze()

    def u8(self, a): return self.data[a - BASE]
    def u16(self, a): return struct.unpack_from('<H', self.data, a - BASE)[0]
    def u32(self, a): return struct.unpack_from('<I', self.data, a - BASE)[0]
    def inimg(self, a): return BASE <= a < self.end

    def analyze(self):
        work = []
        for i in range(1, 48):
            v = self.u32(BASE + 4 * i)
            if v & 1 and self.inimg(v):
                work.append(v - 1)
                self.code_ptr_words.add(BASE + 4 * i)
        for a in range(REGION_TABLE[0] + 12, REGION_TABLE[1], 16):
            work.append(self.u32(a) & ~1)
            self.code_ptr_words.add(a)
        while work:
            a = work.pop()
            while self.inimg(a) and a not in self.ins:
                i = decode(self.u16, a)
                self.ins[a] = i
                if i.kind == 'ldrpc':
                    self.lit.setdefault(i.target, set()).add(a)
                    v = self.u32(i.target)
                    if v & 1 and BASE + 0xc0 <= v < 0x5c3c:
                        work.append(v - 1)
                        self.code_ptr_words.add(i.target)
                elif i.kind == 'adr':
                    self.adr.add(i.target)
                elif i.kind in ('b', 'bcond'):
                    work.append(i.target)
                elif i.kind == 'bl':
                    if i.target == SWITCH8:
                        t = a + 4
                        n = self.u8(t)
                        tg = [t + 2 * self.u8(t + 1 + k) for k in range(n + 1)]
                        self.switch[t] = (n, tg)
                        work.extend(tg)
                        work.append(SWITCH8)
                        break
                    work.append(i.target)
                    if i.target in NORETURN:
                        break
                if i.kind in ('b', 'ret', 'ind') and not (i.kind == 'ind' and i.text.startswith('blx')):
                    break
                a += i.size

    def code_bytes(self):
        s = set()
        for a, i in self.ins.items():
            s.update(range(a, a + i.size))
        return s


if __name__ == '__main__':
    import re
    im = Image()
    cb = im.code_bytes()
    print('instructions: %d, code bytes: %d, raw fallbacks: %d' %
          (len(im.ins), len(cb), sum(i.kind == 'raw' for i in im.ins.values())))
    for i in sorted(im.ins.values(), key=lambda x: x.addr):
        if i.kind == 'raw' or i.text.startswith('.inst'):
            print('  raw %04x %s' % (i.addr, i.text))
    # overlap check
    prev = None
    for a in sorted(im.ins):
        if prev and prev.addr + prev.size > a:
            print('  OVERLAP %04x/%04x' % (prev.addr, a))
        prev = im.ins[a]
    gh = set()
    for l in open(ROOT / 'ghidra' / 'disasm.txt'):
        m = re.match(r'^([0-9a-f]{8})  ', l)
        if m: gh.add(int(m.group(1), 16))
    mine = set(im.ins)
    print('ghidra-only instr addrs: %d  mine-only: %d' % (len(gh - mine), len(mine - gh)))
    print('  ghidra-only:', ' '.join('%04x' % a for a in sorted(gh - mine)[:40]))
    mo = sorted(mine - gh)
    runs, s = [], None
    for a in mo:
        if s is None or a - e > 4: 
            if s is not None: runs.append((s, e))
            s = a
        e = a
    if s is not None: runs.append((s, e))
    print('  mine-only runs:', ' '.join('%04x-%04x' % r for r in runs))
    print('switch tables:', {hex(k): (v[0], [hex(x) for x in v[1]]) for k, v in im.switch.items()})
    print('literal words: %d' % len(im.lit))
    for a in sorted(im.lit):
        v = im.u32(a)
        if im.inimg(v) or im.inimg(v - 1):
            kind = 'CODE' if a in im.code_ptr_words else ('code?' if (v & 1 and (v - 1) in im.ins) else ('incode' if v in cb else 'data'))
            print('  lit %04x = %08x %s  refs=%s' % (a, v, kind, ','.join('%04x' % r for r in sorted(im.lit[a]))))
    # non-code gaps
    gaps, s = [], None
    for a in range(BASE, im.end):
        if a not in cb and a not in {x + k for x in im.lit for k in range(4)}:
            if s is None: s = a
        elif s is not None:
            gaps.append((s, a)); s = None
    if s is not None: gaps.append((s, im.end))
    print('unclassified gaps:')
    for s, e in gaps:
        print('  %04x-%04x %5d  %s' % (s, e, e - s, im.data[s - BASE:min(e, s + 24) - BASE].hex()))
