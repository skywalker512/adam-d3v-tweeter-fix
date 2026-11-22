#!/usr/bin/env python3
"""ADAU1701 parameter RAM as text.

    python3 kit/dsp.py list [params.bin]        # all 281 words with region names
    apply(blob, 'mods/NAME.params')             # used by build.py --params NAME

A .params file has one assignment per line:   p137 = 1.0      (linear, 5.23)
                                               p7   = -3dB
                                               p171 = 0x12     (raw 28-bit word)
Region names come from tracing the DSP program; they are inferred, not vendor names.
"""
import math, re, sys
from pathlib import Path

HEADER = 2                       # download block starts with the 16-bit parameter RAM address
REGIONS = [(0, 3, 'master volume L/R: target, slew'), (4, 5, 'input polarity (+1 analog, -1 USB)'),
           (6, 6, 'L/R swap'), (7, 8, 'output trim'), (9, 51, 'POSITION / DESK / ROOM EQ + switch index (p19, p40, p51)'),
           (52, 136, 'crossover + driver EQ biquads'), (137, 169, 'tweeter dynamics table, -90..+6 dBFS in 3 dB steps'),
           (170, 171, 'tweeter dynamics hold, decay'), (172, 201, 'woofer clip detectors (thresholds p183, p198)'),
           (202, 241, 'woofer RMS compressor table'), (242, 245, 'woofer RMS timing'),
           (246, 278, 'woofer peak limiter table'), (279, 280, 'woofer peak hold, decay')]


def get(blob, i):
    v = int.from_bytes(blob[HEADER + 4 * i:HEADER + 4 * i + 4], 'big')
    return v, ((v & 0x0FFFFFFF) - (1 << 28 if v & 0x08000000 else 0)) / 2 ** 23


def parse(text):
    text = text.strip()
    if text.lower().startswith('0x'):
        return int(text, 16)
    x = 10 ** (float(text[:-2]) / 20) if text.lower().endswith('db') else float(text)
    if not -16 <= x < 16:
        raise ValueError('outside the 5.23 range: ' + text)
    return round(x * 2 ** 23) & 0x0FFFFFFF


def apply(blob, path):
    blob = bytearray(blob)
    for line in Path(path).read_text().splitlines():
        line = line.split('#')[0].strip()
        if not line:
            continue
        m = re.fullmatch(r'p(\d+)\s*=\s*(\S+)', line)
        if not m or not 0 <= int(m.group(1)) < (len(blob) - HEADER) // 4:
            raise SystemExit('%s: cannot parse %r' % (path, line))
        i = int(m.group(1))
        blob[HEADER + 4 * i:HEADER + 4 * i + 4] = parse(m.group(2)).to_bytes(4, 'big')
    return bytes(blob)


if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    blob = Path(sys.argv[2] if len(sys.argv) > 2 else root / 'build' / 'dsp' / 'seg2_params.bin').read_bytes()
    for lo, hi, name in REGIONS:
        print('# ' + name)
        for i in range(lo, hi + 1):
            raw, x = get(blob, i)
            db = '%8.2f dB' % (20 * math.log10(abs(x))) if x else '     -inf'
            print('p%-3d = 0x%08x  %+12.7f %s' % (i, raw, x, db))
