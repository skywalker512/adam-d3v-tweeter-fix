#!/usr/bin/env python3
"""Assemble build/app.S into a flashable image.

    python3 kit/build.py                      # must reproduce the factory image byte for byte
    python3 kit/build.py --mod NAME [...]     # apply mods/NAME.patch (code) first
    python3 kit/build.py --params NAME [...]  # apply mods/NAME.params (DSP parameter RAM)
    python3 kit/build.py --c FUNC [...]       # replace function FUNC by mods/FUNC.c (clang -Oz)
                                              # -> build/NAME[+NAME...].bin
"""
import hashlib, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def llvm_dir():
    """Directory with clang + llvm-objcopy that can target ARM: $D3V_LLVM, Homebrew LLVM, or PATH."""
    for d in (os.environ.get('D3V_LLVM'), '/opt/homebrew/opt/llvm/bin', '/usr/local/opt/llvm/bin'):
        if d and (Path(d) / 'llvm-objcopy').exists():
            return Path(d)
    found = shutil.which('llvm-objcopy')
    if not found:
        sys.exit('ERROR: clang / llvm-objcopy not found (brew install llvm, apt install clang llvm, or set D3V_LLVM)')
    return Path(found).parent


LLVM = llvm_dir()
B = ROOT / 'build'
REF = ROOT / 'fw' / 'D3V_MCU+DSP_V1_7_RC4.bin'


DROP = ('.syntax', '.eabi_attribute', '.cpu', '.file', '.text', '.globl', '.type', '.fnstart', '.size',
        '.cantunwind', '.fnend', '.ident', '.section', '.addrsig', '.code', '.save', '.setfp', '.pad', '.movsp')


def splice_c(text, name, keep_size=False):
    """Replace function `name` (label up to the next function label) by compiled mods/name.c.
    keep_size pads the replacement to the original length so that nothing after it moves."""
    asm = subprocess.run([LLVM / 'clang', '--target=thumbv6m-none-eabi', '-Oz', '-ffreestanding', '-S', '-o', '-',
                          str(ROOT / 'mods' / (name + '.c'))], check=True, capture_output=True, text=True).stdout
    body = [l.replace('.L', '.L%s_' % name) for l in asm.splitlines()
            if l.strip() and not l.strip().startswith(DROP)]
    lines = text.split('\n')
    s = lines.index(name + ':')
    e = next(i for i in range(s + 1, len(lines))
             if re.fullmatch(r'(?!loc_|lit_|adr_|pic_|switch_|dat_)\w+:', lines[i]))
    while lines[e - 1].strip().startswith('.balign'):
        e -= 1
    assert any(l.startswith(name + ':') for l in body), 'mods/%s.c must define %s()' % (name, name)
    pad = []
    if keep_size:
        at = lambda rows: next(int(m.group(1), 16) for m in (re.search(r'@ ([0-9a-f]{4})\b', l) for l in rows) if m)
        size = at(lines[e:]) - at(lines[s:])
        body = ['__c_start_%s:' % name] + body
        pad = ['    .space %d - (. - __c_start_%s)   @ keep the factory length; fails to assemble if the C code is larger'
               % (size, name)]
    return '\n'.join(lines[:s] + ['    .balign 4                @ C: mods/%s.c' % name] + body + pad + lines[e:])


def build(mods=(), out=None, params=(), cfuncs=(), keep_size=False):
    src, cwd = B / 'app.S', B
    if mods or params or cfuncs:
        cwd = B / '+'.join(list(mods) + list(params) + list(cfuncs))   # own directory so .incbin sees its own dsp/
        shutil.rmtree(cwd, ignore_errors=True)
        shutil.copytree(B / 'dsp', cwd / 'dsp')
        src = cwd / 'app.S'
        shutil.copy(B / 'app.S', src)
        for m in mods:
            subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(src), str(ROOT / 'mods' / (m + '.patch'))], check=True)
        for f in cfuncs:
            src.write_text(splice_c(src.read_text(), f, keep_size))
        if params:
            from dsp import apply
            blob = (cwd / 'dsp' / 'seg2_params.bin').read_bytes()
            for p in params:
                blob = apply(blob, ROOT / 'mods' / (p + '.params'))
            (cwd / 'dsp' / 'seg2_params.bin').write_bytes(blob)
    out = Path(out) if out else (B / (cwd.name + '.bin') if cwd != B else B / 'app.bin')
    subprocess.run([LLVM / 'clang', '--target=thumbv6m-none-eabi', '-c', 'app.S', '-o', 'app.o'], cwd=cwd, check=True)
    subprocess.run([LLVM / 'llvm-objcopy', '-O', 'binary', '-j', '.text', 'app.o', str(out)], cwd=cwd, check=True)
    return out


if __name__ == '__main__':
    a = sys.argv[1:]
    mods = [a[i + 1] for i, x in enumerate(a) if x == '--mod']
    params = [a[i + 1] for i, x in enumerate(a) if x == '--params']
    cfuncs = [a[i + 1] for i, x in enumerate(a) if x == '--c']
    out = build(mods, a[a.index('-o') + 1] if '-o' in a else None, params, cfuncs, '--keep-size' in a)
    new, ref = out.read_bytes(), REF.read_bytes()
    print('%s: %d bytes, sha256 %s' % (out, len(new), hashlib.sha256(new).hexdigest()))
    if new == ref:
        print('IDENTICAL to the factory 1.7 RC4 image')
    else:
        n = sum(x != y for x, y in zip(new, ref))
        print('differs from factory: size %+d bytes, %d bytes changed in the common part' % (len(new) - len(ref), n))
        if len(new) > 0x7e00 - 0x2000:
            sys.exit('ERROR: image runs into the settings page at 0x7E00')
        if not (mods or params or cfuncs):
            sys.exit(1)
