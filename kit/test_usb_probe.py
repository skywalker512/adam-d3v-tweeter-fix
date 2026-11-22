#!/usr/bin/env python3
"""Emulator checks for the USB listen probe (mods/usb-probe.patch + mods/_printf_core.c, --keep-size).

What can be shown here: same image size, only the probe region and one call differ, the probe writes the
USBD registers in a safe order and restores them, the LED pattern follows the frame counter, and after the
probe the firmware behaves exactly like the image without it.  What cannot: anything about the real USBD
block or the board wiring; the emulator has no USB model.
"""
import sys
from build import build
from machine import D3V, pin, decode_i2c

PB4, PF4 = pin('PB4'), pin('PF4')
LED = ('PB12', 'PB13', 'PB14')
USB_REGS = {0x40000208: 'CLK_APBCLK0', 0x400C0010: 'USBD_ATTR', 0x400C0090: 'USBD_SE0'}
ok = True


def check(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print('%-4s %s%s' % ('ok' if cond else 'FAIL', name, '  ' + str(detail) if detail else ''))


class Probed(D3V):
    """D3V that records writes to the registers the probe touches and can fake a running frame counter."""
    def __init__(self, image, bus_alive=False):
        self.writes, self.bus_alive = [], bus_alive
        super().__init__(image)
        self.reg[0x400C0010] = 0x40                    # reset values: ATTR bit 6, SE0 = 1 (drive SE0)
        self.reg[0x400C0090] = 1

    def io_read(self, a, size):
        if a == 0x400C008C:
            return (self.cpu.cycles // 600) & 0x7FF if self.bus_alive else 0
        return super().io_read(a, size)

    def io_write(self, a, v, size):
        if a in USB_REGS:
            self.writes.append((USB_REGS[a], v))
        super().io_write(a, v, size)


def led_changes(m, upto):
    return sum(1 for t, kind, x in m.log if kind == 'gpio' and x.startswith('PB12=') and t < upto)


def events(m):
    return [x for _, x in decode_i2c(m.log) if not x.startswith('led')]


def tour(m, lead_ms):
    m.inputs[PF4] = 1
    m.run_ms(lead_ms + 4500); m.adc[3] = 3000; m.run_ms(400)
    for _ in range(2):                                 # double click: USB input
        m.inputs[PB4] = 0; m.run_ms(100); m.inputs[PB4] = 1; m.run_ms(200)
    m.run_ms(3500)
    m.inputs[PB4] = 0; m.run_ms(100); m.inputs[PB4] = 1; m.run_ms(1500)   # mute
    m.inputs[PF4] = 0; m.run_ms(1500); m.inputs[PF4] = 1; m.run_ms(3000)  # cable out, in
    return events(m)


base = build(params=['no-tweeter-gate']).read_bytes()
probe = build(mods=['usb-probe'], params=['no-tweeter-gate'], cfuncs=['_printf_core'], keep_size=True).read_bytes()

diff = [i for i in range(len(base)) if base[i] != probe[i]]
check('same size as the flashed image', len(probe) == len(base) == 22124, len(probe))
check('only the _printf_core region and one call differ',
      all(0x1df8 <= i < 0x20cc or 0x26d2 <= i < 0x26d6 for i in diff), '%d bytes' % len(diff))

for alive in (False, True):
    m = Probed(probe, alive)
    m.run_ms(10500)
    n = led_changes(m, 100000)
    w = m.writes
    name = 'bus alive' if alive else 'bus silent'
    check('%s: LED level changes in the first 10 s (fast = about 100, slow = about 20)' % name,
          95 <= n <= 101 if alive else 18 <= n <= 22, n)
    check('%s: SE0 released before the transceiver is enabled' % name,
          w.index(('USBD_SE0', 0)) < w.index(('USBD_ATTR', 0x6D0)), w)
    check('%s: D+ pull-up never enabled' % name, all(not (v & 0x100) for r, v in w if r == 'USBD_ATTR'))
    check('%s: registers restored' % name,
          m.reg[0x400C0010] == 0x40 and m.reg[0x400C0090] == 1 and not m.reg.get(0x40000208, 0) >> 27 & 1,
          [hex(m.reg.get(a, 0)) for a in USB_REGS])

ref = tour(D3V(base), 0)
new = tour(Probed(probe), 10000)
check('after the probe: DSP writes and pin changes identical to the image without it', ref == new,
      '%d events' % len(ref))
m = D3V(probe)                                          # HardFault path must still return
check('HardFault report path returns', m.cpu.call(0x3c34, 0x2000, 1, 2, 3)[0] == 0)
sys.exit(0 if ok else 1)
