#!/usr/bin/env python3
"""Get the factory firmware image that everything else in kit/ starts from.

    python3 kit/fetch.py      -> fw/D3V_MCU+DSP_V1_7_RC4.bin

The image is ADAM Audio's and is not part of this repository.  It is taken out of the official
Windows updater package (downloaded into build/official/, SHA-256 checked).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'patcher'))
from d3v_patch import FACTORY_SHA, FW_NAME, FW_SIZE, fetch, member, nsis_files, sha

fw = ROOT / 'fw' / FW_NAME
if fw.exists():
    if sha(fw.read_bytes()) != FACTORY_SHA:
        sys.exit('ERROR: %s is not the factory 1.7 RC4 image' % fw)
    print('%s already present, sha256 ok' % fw)
else:
    setup = member(fetch('win', ROOT / 'build' / 'official'), '-setup.exe')
    fw.parent.mkdir(exist_ok=True)
    fw.write_bytes(nsis_files(setup, {FW_NAME: (FW_SIZE, FACTORY_SHA)})[FW_NAME])
    print('wrote %s, sha256 ok' % fw)
