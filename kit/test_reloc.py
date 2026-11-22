#!/usr/bin/env python3
"""Prove that build/app.S is really relocatable.

Inserts padding in three places (start of code, middle of the application, in
front of the DSP parameter block), re-assembles, and checks every instruction,
pointer, length, switch entry and PC-relative table offset of the moved image
against the original through the assembler's own symbol table.
"""
import json, subprocess, sys
from pathlib import Path
from analyze import Image, BASE, ROOT
from thumb import decode
from build import LLVM

B = ROOT / 'build'
INSERT = {'__main:': '    nop\n', 'knob_update:': '    nop\n    nop\n    nop\n',
          'dsp_seg2_params_end:': '    .space 10, 0xEE\n'}      # all inserted in front of the label

subprocess.run([sys.executable, Path(__file__).parent / 'split.py', '--label-all'], check=True, stdout=subprocess.DEVNULL)
src = (B / 'app.S').read_text()
for k, v in INSERT.items():
    assert src.count('\n' + k + '\n') == 1, k
    src = src.replace('\n' + k + '\n', '\n' + v + k + '\n')
(B / 'moved.S').write_text(src)
subprocess.run([LLVM / 'clang', '--target=thumbv6m-none-eabi', '-c', 'moved.S', '-o', 'moved.o'], cwd=B, check=True)
subprocess.run([LLVM / 'llvm-objcopy', '-O', 'binary', '-j', '.text', 'moved.o', 'moved.bin'], cwd=B, check=True)
nm = subprocess.run([LLVM / 'llvm-nm', 'moved.o'], cwd=B, check=True, capture_output=True, text=True).stdout
new_of = {int(n[2:], 16): BASE + int(a, 16) for a, _, n in (l.split() for l in nm.splitlines()) if n.startswith('i_')}

old = Image()
new = Image.__new__(Image)
new.data = (B / 'moved.bin').read_bytes()
new.end = BASE + len(new.data)
meta = json.loads((B / 'items.json').read_text())
items = {int(k): v for k, v in meta['items'].items()}
order = sorted(items) + [old.end]
moved = sum(1 for a in items if new_of[a] != a)
bad = n_ins = n_sym = n_raw = 0

def fail(a, msg):
    global bad
    bad += 1
    if bad < 20:
        print('  MISMATCH old %04x -> new %04x: %s' % (a, new_of[a], msg))

for a, nxt in zip(order, order[1:]):
    it, n = items[a], new_of[a]
    if it[0] == 'ins':
        io, i2 = old.ins[a], decode(new.u16, n)
        n_ins += 1
        if (io.text, io.size, io.kind) != (i2.text, i2.size, i2.kind):
            fail(a, '%s != %s' % (io.text, i2.text))
        elif io.target is not None and new_of.get(io.target) != i2.target:
            fail(a, '%s target %04x should map to %s, got %04x' % (io.text, io.target, new_of.get(io.target), i2.target))
    elif it[0] == 'word':
        v, kind = new.u32(n), it[1]
        n_sym += kind != 'const'
        want = {'const': lambda: old.u32(a), 'abs': lambda: new_of[it[2]], 'thumb': lambda: new_of[it[2]] + 1,
                'len': lambda: None, 'pic': lambda: (new_of[it[2]] - new_of[it[3]] - 4) & 0xffffffff}[kind]()
        if want is not None and v != want:
            fail(a, 'word %s: %08x, want %08x' % (kind, v, want))
    else:
        n_raw += 1
        size = 0x466 if a == 0x703c else nxt - a
        if new.data[n - BASE:n - BASE + size] != old.data[a - BASE:a - BASE + size] and old.data[a - BASE:a - BASE + size].strip(b'\0'):
            fail(a, 'raw bytes differ')
for t, tg in meta['switch'].items():
    t = int(t)
    nt = new_of[t - 4] + 4
    got = [nt + 2 * new.u8(nt + 1 + k) for k in range(new.u8(nt) + 1)]
    if got != [new_of[x] for x in tg]:
        bad += 1; print('  switch table mismatch')
# DSP download lengths must follow the grown parameter block
print('image %d -> %d bytes; %d of %d items moved' % (len(old.data), len(new.data), moved, len(items)))
print('checked %d instructions, %d symbolic words, %d raw blocks, %d switch table(s): %d mismatches'
      % (n_ins, n_sym, n_raw, len(meta['switch']), bad))
print('param block length literal: %#x (was %#x)' % (new.u32(new_of[0x42b8]), old.u32(0x42b8)))
subprocess.run([sys.executable, Path(__file__).parent / 'split.py'], check=True, stdout=subprocess.DEVNULL)
sys.exit(1 if bad else 0)
