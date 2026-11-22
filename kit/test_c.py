#!/usr/bin/env python3
"""Check a C replacement (mods/adc_to_switch3.c) against the factory routine:
every possible 12-bit ADC reading through direct calls, then the same boot + switch
scenario on both images comparing everything the firmware sends to the DSP."""
import sys
from analyze import FW
from build import build
from machine import D3V, decode_i2c

FUNC = 0x28f0                                   # same address in both images: nothing before it moved


def run(image):
    m = D3V(image)
    m.run_ms(4500)
    table = [m.cpu.call(FUNC, v)[0] for v in list(range(4096)) + [0xFFFF, 0x12345, 0xFFFFFFFF]]
    for ch in (0, 1, 2):                        # DESK, POSITION, ROOM: sweep each switch through its positions
        for v in (2000, 3500, 1200, 2800, 500):
            m.adc[ch] = v
            m.run_ms(200)
    return table, [x for _, x in decode_i2c(m.log) if x.startswith('dsp')]


fa, fb = run(FW.read_bytes())
ca, cb = run(build(cfuncs=['adc_to_switch3']).read_bytes())
print('%-4s direct calls: %d inputs, %d differences' % ('ok' if fa == ca else 'FAIL', len(fa), sum(x != y for x, y in zip(fa, ca))))
print('%-4s scenario: %d DSP writes, identical: %s' % ('ok' if fb == cb else 'FAIL', len(fb), fb == cb))
print('     switch writes seen:', ', '.join(x[4:] for x in fb if x.split()[1] in ('p19', 'p40', 'p51'))[:300])
sys.exit(0 if fa == ca and fb == cb else 1)
