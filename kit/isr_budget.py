#!/usr/bin/env python3
"""Worst-case Cortex-M0 cycle count of the 10 kHz timer interrupt handler.

Why it matters: i2c_half_bit_delay (0x41e8) samples SysTick twice, about 7 cycles apart, and
loops if the difference exceeds 192 counts (SysTick runs from the CPU clock).  Inside the loop it
adds the reload value and tries again, which only terminates on a 32-bit wrap coincidence.  A timer
interrupt landing between the two samples makes the difference 16 (entry) + handler + 16 (exit) + 7.
So the handler has to stay at or below 192 - 7 - 32 = 153 cycles or bit-banged I2C can stall.

    python3 kit/isr_budget.py [image.bin]
"""
import sys
from analyze import Image, BASE, FW
from thumb import decode

LIMIT = 192 - 7 - 32


def cost(i, taken=False):
    t = i.text.split()[0]
    if i.kind == 'ldrpc' or t.startswith(('ldr', 'str')):
        return 2
    if t == 'push':
        return 1 + i.text.count('r') + i.text.count('lr')
    if t == 'pop':
        return (4 if 'pc' in i.text else 1) + i.text.count('r') + ('pc' in i.text)
    if t in ('stm', 'ldm'):
        return 1 + i.text.count('r') - 1
    if i.kind == 'b':
        return 3
    if i.kind == 'bcond':
        return 3 if taken else 1
    if i.kind == 'bl':
        return 4
    if t in ('bx', 'blx') or i.kind == 'ind':
        return 3
    if t in ('mrs', 'msr'):
        return 4
    return 1


def worst(im, a, seen=()):
    """Longest path from a to the function return, in cycles, with the path."""
    total, path = 0, []
    while True:
        if a in seen:
            raise SystemExit('loop at %04x: no static bound' % a)
        seen += (a,)
        i = decode(im.u16, a)
        if i.kind == 'ret':
            return total + cost(i), path + [a]
        if i.kind == 'b':
            total += cost(i); path.append(a); a = i.target; continue
        if i.kind == 'bcond':
            t1, p1 = worst(im, i.target, seen)
            t2, p2 = worst(im, a + 2, seen)
            if t1 + 3 >= t2 + 1:
                return total + 3 + t1, path + [a] + p1
            return total + 1 + t2, path + [a] + p2
        if i.kind == 'bl':
            t, _ = worst(im, i.target)
            total += cost(i) + t; path.append(a); a += 4; continue
        if i.kind in ('ind', 'raw'):
            raise SystemExit('cannot bound %s at %04x' % (i.text, a))
        total += cost(i); path.append(a); a += i.size


if __name__ == '__main__':
    args = [x for x in sys.argv[1:] if not x.startswith('-')]
    im = Image(args[0] if args else FW)
    handler = im.u32(BASE + 4 * 24) & ~1
    t, path = worst(im, handler)
    print('TMR0 handler at 0x%04x: worst case %d cycles over %d instructions (limit %d, margin %d)'
          % (handler, t, len(path), LIMIT, LIMIT - t))
    sys.exit(0 if t <= LIMIT else 1)
