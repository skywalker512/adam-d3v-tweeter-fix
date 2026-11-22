#!/usr/bin/env python3
"""End-to-end checks of the emulator, the relocatable source and one real mod.

1. CPU: the firmware's soft-float pow() must give 10^(dB/20) * 2^23 for every volume step.
2. Boot: the bit-banged I2C traffic must replay the DSP image stored in the firmware.
3. Relocation: an image with all code moved must behave identically, event for event.
4. Mod: mods/fix-usb-resume-mute must change exactly one thing - no un-mute on USB resume.
"""
import math, subprocess, sys
from pathlib import Path
from analyze import ROOT, FW
from machine import D3V, pin, decode_i2c
from build import build, LLVM, B

VOLUME_STEP_TO_GAIN = 0x3980


def scenario(image):
    m = D3V(image)

    def click(n):
        for _ in range(n):
            m.inputs[pin('PB4')] = 0; m.run_ms(100)
            m.inputs[pin('PB4')] = 1; m.run_ms(200)
    m.run_ms(4500)                               # power-up, DSP download, volume fade-in
    m.adc[3] = 3000; m.run_ms(500)               # turn the knob up
    click(2); m.run_ms(3000)                     # double click: analog -> USB input
    m.inputs[pin('PF4')] = 1; m.run_ms(3000)     # USB stream becomes active
    mark = len(m.log)
    click(1); m.run_ms(2000)                     # single click: mute
    m.inputs[pin('PF4')] = 0; m.run_ms(2000)     # stream stops
    m.inputs[pin('PF4')] = 1; m.run_ms(3500)     # stream resumes while still muted
    return m, mark


def volume_writes(m, since=0):
    return [x for _, x in decode_i2c(m.log[since:]) if x.startswith('dsp p0 ')]


ok = True
def check(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print('%-4s %s%s' % ('ok' if cond else 'FAIL', name, '  ' + detail if detail else ''))


img = FW.read_bytes()
m, mark = scenario(img)

# 1 --- CPU / soft-float self check
steps = {}
for mode in (0, 1):
    for step in range(1, 29):
        g = m.cpu.call(VOLUME_STEP_TO_GAIN, step, mode)[0]
        db = round(20 * math.log10(g / 2 ** 23))
        steps[mode, step] = db
        if abs(g - 10 ** (db / 20) * 2 ** 23) > 1:
            check('pow() step %d mode %d' % (step, mode), False, hex(g))
check('pow(): 56 volume gains equal 10^(dB/20)*2^23 within 1 LSB', True)
print('     analog dB per step:', ' '.join('%d' % steps[0, s] for s in range(1, 29)))
print('     USB    dB per step:', ' '.join('%d' % steps[1, s] for s in range(1, 29)))

# 2 --- DSP download
i2c = [p for _, p in m.events('i2c')]
segs = [(0x5ccc, 4), (0x5cee, 0x134e), (0x703c, 0x466), (0x5cd0, 0x1a), (0x5cea, 4)]
want = [bytes([0x6c]) + img[a - 0x2000:a - 0x2000 + n] for a, n in segs]
check('boot: 5 DSP download blocks (%d bytes) match the image' % sum(n for _, n in segs), i2c[:5] == want)

# 3 --- relocation
src = (B / 'app.S').read_text()
for label in ('__main:', 'knob_update:', 'main:', 'pow:'):
    assert src.count('\n' + label + '\n') == 1
    src = src.replace('\n' + label + '\n', '\n    nop\n' + label + '\n')
(B / 'moved_code.S').write_text(src)
subprocess.run([LLVM / 'clang', '--target=thumbv6m-none-eabi', '-c', 'moved_code.S', '-o', 'moved_code.o'], cwd=B, check=True)
subprocess.run([LLVM / 'llvm-objcopy', '-O', 'binary', '-j', '.text', 'moved_code.o', 'moved_code.bin'], cwd=B, check=True)
moved = (B / 'moved_code.bin').read_bytes()
m2, _ = scenario(moved)
same = sum(x == y for x, y in zip(img, moved))
check('relocated image (%d of %d bytes differ) produces the identical event log (%d events)'
      % (len(img) - same, len(img), len(m.log)), m.log == m2.log)

# 4 --- the mod
fixed = build(['fix-usb-resume-mute']).read_bytes()
m3, mark3 = scenario(fixed)
check('mod: identical behaviour up to the mute click', m.log[:mark] == m3.log[:mark3])
a, b = volume_writes(m, mark), volume_writes(m3, mark3)
print('     factory after mute:', ', '.join(x[9:] for x in a))
print('     mod     after mute:', ', '.join(x[9:] for x in b))
check('factory un-mutes on USB resume (the bug)', a[-1] != 'dsp p0 = 0x0000000')
check('mod stays muted on USB resume', all(x == 'dsp p0 = 0x0000000' for x in b))
m3.inputs[pin('PB4')] = 0; m3.run_ms(100); m3.inputs[pin('PB4')] = 1; m3.run_ms(2500)
check('mod: un-mute click still restores the volume', volume_writes(m3)[-1] != 'dsp p0 = 0x0000000', volume_writes(m3)[-1])
sys.exit(0 if ok else 1)
