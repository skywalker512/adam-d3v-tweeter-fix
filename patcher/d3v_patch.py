#!/usr/bin/env python3
"""Build the "No Tweeter Gate" D3V updater from ADAM Audio's official firmware updater.

    python3 d3v_patch.py                 # updater for this computer (macOS or Windows)
    python3 d3v_patch.py mac|win|firmware
    python3 d3v_patch.py win --official adam-audio-d3v-...-windows.zip   # use a file you downloaded
    python3 d3v_patch.py mac --firmware build/other.bin                  # embed another image (kit users)

Downloads the official package from ADAM Audio, checks it against known SHA-256 values, changes
seven ADAU1701 parameter words in firmware 1.7 (21 bytes differ, size unchanged) and puts the
result into a copy of the official updater.  Nothing is flashed: you run the updater yourself.
Python 3.8+, standard library only.  The mac target needs macOS (hdiutil, codesign).
"""
import argparse, hashlib, lzma, shutil, struct, subprocess, sys, tempfile, urllib.request, zipfile
from pathlib import Path

BASE_URL = 'https://fael-downloads-prod.focusrite.com/customer/prod/downloads/'
OFFICIAL = {   # target: (zip name, sha256 of the zip)
    'mac': ('adam-audio-d3v-desktop-monitor-firmware-update-macos.zip',
            '731bda8d624b411f93b6ced56752c6df9335d8372dd990671e31ebd258e1a36c'),
    'win': ('adam-audio-d3v-desktop-monitor-firmware-update-windows.zip',
            '4641af5460b07d4eaec6ab93b41df7e95cf8dfe88b2345e2735be392fde24343'),
}
FW_NAME = 'D3V_MCU+DSP_V1_7_RC4.bin'
FW_SIZE = 22124
FACTORY_SHA = 'f2486dae4ef2399db12fcb255eeab227e1533bf1eed96c9a2eaa3ef822388a38'
PATCHED_SHA = '59f60c30c9853a5c77bace00026e78ab91851aa39a294e77aee5959e39e98fef'
WIN_EXE = ('D3V Updater.exe', 7864320, 'e0027f9dfcf157764d7dfce08622f3a952c17cc466e3d81578c55ae00d4a7021')
MAC_EXE_SHA = 'ae377bd1383d4859a547042d9987b63445ed06023fbb683adce5a63b045267e6'
VARIANT = 'No Tweeter Gate'

# Tweeter dynamics table of the ADAU1701 program, lowest seven points (-90 .. -72 dBFS input).
# Factory values attenuate by up to 31 dB (downward expander); unity makes the table flat.
PARAM_BASE = 0x503E                      # file offset of parameter word p0
UNITY = 0x00800000                       # 1.0 in 5.23 fixed point
GATE = {137: 0x00090FCC, 138: 0x00066A4D, 139: 0x00049B92, 140: 0x0003A013,
        141: 0x0012149A, 142: 0x00799DAE, 143: 0x007FFF48}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_firmware(fw):
    """Factory 1.7 image -> no-tweeter-gate image.  Refuses anything but the known factory image."""
    if len(fw) != FW_SIZE or sha(fw) != FACTORY_SHA:
        sys.exit('ERROR: not the factory 1.7 firmware (sha256 %s)' % sha(fw))
    out = bytearray(fw)
    for i, factory in GATE.items():
        off = PARAM_BASE + 4 * i
        assert int.from_bytes(fw[off:off + 4], 'big') == factory, 'p%d is not the factory value' % i
        out[off:off + 4] = UNITY.to_bytes(4, 'big')
    out = bytes(out)
    assert len(out) == FW_SIZE and sha(out) == PATCHED_SHA
    return out


def fetch(target, cache):
    """Official zip for `target`, downloaded into `cache` unless a verified copy is already there."""
    name, want = OFFICIAL[target]
    path = Path(cache) / name
    if not (path.exists() and sha(path.read_bytes()) == want):
        path.parent.mkdir(parents=True, exist_ok=True)
        print('downloading', BASE_URL + name)
        try:
            with urllib.request.urlopen(BASE_URL + name, timeout=60) as r:
                path.write_bytes(r.read())
        except OSError as e:               # e.g. a Python without CA certificates: let curl try
            print('  urllib failed (%s), trying curl' % e)
            subprocess.run(['curl', '-fsSL', '-o', str(path), BASE_URL + name], check=True)
        if sha(path.read_bytes()) != want:
            sys.exit('ERROR: %s has sha256 %s, expected %s.\nADAM Audio may have published a new updater; '
                     'this tool only knows updater 1.0.0 / firmware 1.7.' % (path, sha(path.read_bytes()), want))
    return path


def member(path, suffix):
    """Bytes of the installer inside the official zip (or of `path` itself if it already is one)."""
    path = Path(path)
    if path.name.lower().endswith(suffix):
        return path.read_bytes()
    with zipfile.ZipFile(path) as z:
        return z.read(next(n for n in z.namelist() if n.lower().endswith(suffix)))


def nsis_files(setup, wanted):
    """Pull files out of a solid-LZMA NSIS installer.  wanted: {name: (size, sha256)} -> {name: bytes}.
    Each file is stored as <u32 length><data>, so known size + hash is enough to find it."""
    i = setup.find(b'\xef\xbe\xad\xdeNullsoftInst')
    if i < 0:
        sys.exit('ERROR: not an NSIS installer')
    p = i + 24                                               # past the first header: LZMA props + dictionary size
    prop, dict_size = setup[p], struct.unpack_from('<I', setup, p + 1)[0]
    flt = {'id': lzma.FILTER_LZMA1, 'dict_size': dict_size, 'lc': prop % 9, 'lp': prop // 9 % 5, 'pb': prop // 45}
    data = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[flt]).decompress(setup[p + 5:])
    found = {}
    for name, (size, digest) in wanted.items():
        j = -1
        while name not in found:
            j = data.find(struct.pack('<I', size), j + 1)
            if j < 0:
                sys.exit('ERROR: %s (sha256 %s) not found in the installer' % (name, digest))
            if sha(data[j + 4:j + 4 + size]) == digest:
                found[name] = data[j + 4:j + 4 + size]
    return found


def build_win(official, image, out):
    files = nsis_files(member(official, '-setup.exe'), {WIN_EXE[0]: WIN_EXE[1:], FW_NAME: (FW_SIZE, FACTORY_SHA)})
    dst = out / ('D3V Updater (%s)' % VARIANT)
    shutil.rmtree(dst, ignore_errors=True)
    (dst / 'resources' / 'firmware').mkdir(parents=True)
    (dst / WIN_EXE[0]).write_bytes(files[WIN_EXE[0]])          # unmodified, keeps ADAM's signature
    (dst / 'resources' / 'firmware' / FW_NAME).write_bytes(image or patch_firmware(files[FW_NAME]))
    return dst


def build_mac(official, image, out):
    if sys.platform != 'darwin':
        sys.exit('ERROR: the mac updater can only be built on macOS (needs hdiutil and codesign)')
    run = lambda *a: subprocess.run(a, check=True, capture_output=True)
    dst = out / ('D3V Updater (%s).app' % VARIANT)
    shutil.rmtree(dst, ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        dmg, mnt = Path(tmp) / 'official.dmg', Path(tmp) / 'mnt'
        dmg.write_bytes(member(official, '.dmg'))
        run('hdiutil', 'attach', '-nobrowse', '-readonly', '-mountpoint', str(mnt), str(dmg))
        try:
            run('ditto', str(mnt / 'D3V Updater.app'), str(dst))
        finally:
            run('hdiutil', 'detach', str(mnt))
    if sha((dst / 'Contents/MacOS/D3V Updater').read_bytes()) != MAC_EXE_SHA:
        sys.exit('ERROR: unexpected updater executable in the DMG')
    fw = dst / 'Contents/Resources/resources/firmware' / FW_NAME
    fw.write_bytes(image or patch_firmware(fw.read_bytes()))
    # The changed resource breaks ADAM's signature seal; replace it by an ad-hoc one so the app starts.
    run('codesign', '--force', '--deep', '--sign', '-', str(dst))
    run('codesign', '--verify', '--deep', '--strict', str(dst))
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('target', nargs='?', choices=['mac', 'win', 'firmware'],
                    default={'darwin': 'mac', 'win32': 'win'}.get(sys.platform, 'firmware'))
    ap.add_argument('--official', help='official zip / .dmg / -setup.exe you already downloaded')
    ap.add_argument('--firmware', help='embed this image instead of the built-in patch (not checked!)')
    ap.add_argument('-o', '--out', default='out', help='output directory (default: ./out)')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    image = Path(a.firmware).read_bytes() if a.firmware else None
    if a.target == 'firmware':
        setup = member(a.official or fetch('win', out / 'official'), '-setup.exe')
        dst = out / FW_NAME.replace('.bin', '_no_tweeter_gate.bin')
        dst.write_bytes(patch_firmware(nsis_files(setup, {FW_NAME: (FW_SIZE, FACTORY_SHA)})[FW_NAME]))
    else:
        official = a.official or fetch(a.target, out / 'official')
        dst = (build_mac if a.target == 'mac' else build_win)(official, image, out)
    print('firmware inside: %s' % ('custom image, sha256 ' + sha(image) if image else
                                   'no-tweeter-gate, sha256 ' + PATCHED_SHA))
    print('created: %s' % dst.resolve())
    if a.target != 'firmware':
        print('Nothing has been flashed. Read the flashing steps in the README before you start the updater.')


if __name__ == '__main__':
    main()
