#!/usr/bin/env python3
"""Emulator checks for the usb-guard mod (mods/usb-guard.patch + mods/delay_ms.c).

What can be shown here: the firmware's reaction to the DAC's suspend flag (PF4) and that nothing
else changes.  What cannot: whether muting through PC0 actually silences the pop on the real board.
"""
import sys
from analyze import FW
from build import build
from machine import D3V, pin, decode_i2c
from isr_budget import worst, LIMIT
from analyze import Image, BASE

PF4, PA3, PC0, PB4 = pin('PF4'), pin('PA3'), pin('PC0'), pin('PB4')
USB = b'\x01\x00\x00\x00'            # settings word: input = USB
ok = True


def check(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print('%-4s %s%s' % ('ok' if cond else 'FAIL', name, '  ' + str(detail) if detail else ''))


def events(m, since=0, pc0=True):
    """DSP writes and pin changes, without timestamps and without LED pins."""
    out = []
    for _, x in decode_i2c(m.log[since:]):
        if x.startswith('led') or (not pc0 and 'PC0' in x):
            continue
        out.append(x)
    return out


def volume_on(m):
    return not [x for x in events(m) if x.startswith('dsp p0 ')][-1].endswith('0000000')


def click(m, n=1, hold=100):
    for _ in range(n):
        m.inputs[PB4] = 0; m.run_ms(hold)
        m.inputs[PB4] = 1; m.run_ms(200)


def tour(image):
    """Everything except USB dropouts: must be identical on factory and mod."""
    m = D3V(image)
    m.inputs[PF4] = 1
    m.run_ms(4500); m.adc[3] = 3000; m.run_ms(400)
    click(m, 2); m.run_ms(3500)                       # -> USB input, host present
    click(m, 1); m.run_ms(1500); click(m, 1); m.run_ms(1500)      # mute, un-mute
    m.inputs[PA3] = 0; m.run_ms(1200); m.inputs[PA3] = 1; m.run_ms(1500)   # headphone in, out
    m.adc[2] = 2000; m.run_ms(300)                    # a rear switch
    click(m, 1, hold=2600); m.run_ms(3500)            # long press: standby (LED sequence takes ~3 s)
    check_state.append(m.cpu.ram[0xc4])
    click(m, 1); m.run_ms(6500)                       # power on again
    check_state.append(m.cpu.ram[0xc4])
    click(m, 2); m.run_ms(3000)                       # back to analog
    m.inputs[PF4] = 0; m.run_ms(500); m.inputs[PF4] = 1; m.run_ms(500)     # USB flag is irrelevant on analog
    return events(m)


check_state = []
factory = FW.read_bytes()
mod = build(mods=['usb-guard'], cfuncs=['delay_ms']).read_bytes()
im = Image(build(mods=['usb-guard'], cfuncs=['delay_ms']))
t, _ = worst(im, im.u32(BASE + 4 * 24) & ~1)
check('timer interrupt untouched: worst case %d cycles (limit %d)' % (t, LIMIT), t == 115)

a, b = tour(factory), tour(mod)
check('tour really went through standby and back on both images', check_state == [1, 2, 1, 2], check_state)
check('no USB dropout: %d DSP writes / pin changes identical to factory' % len(a), a == b,
      '' if a == b else next((x, y) for x, y in zip(a, b) if x != y))

# ---- reaction time to the suspend flag, sampled at many phases ---------------------------
m = D3V(mod, settings=USB); m.inputs[PF4] = 1; m.run_ms(6500)
f = D3V(factory, settings=USB); f.inputs[PF4] = 1; f.run_ms(6500)
check('USB mode, host present: PC0 released after power-up on both', m.reg.get(PC0) == 0 and f.reg.get(PC0) == 0)
lat = []
for k in range(30):
    m.adc[3] = 2000 + 150 * (k % 5)                   # a knob move: I2C traffic within the next 30 ms
    m.run_ticks(11 * k)                               # so the fall lands before, inside and after it
    m.inputs[PF4] = 0
    lat.append(m.run_until(lambda: m.reg.get(PC0) == 1))
    m.run_ms(40); m.inputs[PF4] = 1; m.run_ms(3100)
    if m.reg.get(PC0) != 0:
        check('release after dropout %d' % k, False)
med, top = sorted(lat)[len(lat) // 2], max(lat)
check('suspend flag -> PC0=1 over %d phases: median %d instructions (~%.0f us), worst %d (~%.1f ms, fall during a '
      'volume calculation + I2C write)' % (len(lat), med, med * 2 / 48, top, top * 2 / 48000),
      None not in lat and med < 500 and top < 150000)
m.adc[3] = 2000; m.run_ms(300)

# ---- one dropout in detail --------------------------------------------------------------
def dropout(d, low_ms, wait_ms=3000):
    n, t0 = len(d.log), d.tick
    d.inputs[PF4] = 0; d.run_ms(low_ms); t1 = d.tick
    d.inputs[PF4] = 1; d.run_ms(wait_ms)
    out = []
    for t, x in decode_i2c(d.log[n:]):
        if 'PC0' in x or x.startswith('dsp p0 '):
            out.append((round((t - t0) / 10), round((t - t1) / 10), x.replace('dsp ', '').replace('gpio ', '')))
    return out

m.run_ms(500); f.run_ms(500)
print('     400 ms dropout   (ms after fall / ms after rise)')
ef, em = dropout(f, 400), dropout(m, 400)
print('       factory:', '; '.join('%s @%d/%d' % (x, a, b) for a, b, x in ef))
print('       mod    :', '; '.join('%s @%d/%d' % (x, a, b) for a, b, x in em))
rel = [b for a, b, x in em if x == 'PC0=0']
vol = [b for a, b, x in em if x.startswith('p0') and not x.endswith('0000000')]
check('mod: muted within 1 ms of the fall, released 1.8 s after the rise, before the volume comes back',
      em and em[0][2] == 'PC0=1' and em[0][0] <= 1 and rel and 1750 <= rel[0] <= 1850 and vol and vol[0] > rel[0], (rel, vol))
check('mod: DSP volume commands during the dropout are the factory ones',
      [x for _, _, x in em if x.startswith('p0')] == [x for _, _, x in ef if x.startswith('p0')])

print('     3 ms glitch, shorter than the 30 ms poll')
ef, em = dropout(f, 3), dropout(m, 3)
print('       factory:', '; '.join('%s @%d/%d' % (x, a, b) for a, b, x in ef) or 'no reaction at all')
print('       mod    :', '; '.join('%s @%d/%d' % (x, a, b) for a, b, x in em))
check('mod: glitch still mutes for 1.8 s', [(x, 1750 <= b <= 1850 or x == 'PC0=1') for _, b, x in em if 'PC0' in x] == [('PC0=1', True), ('PC0=0', True)])

# ---- interplay with the other users of PC0 ----------------------------------------------
m.inputs[PF4] = 0; m.run_ms(300); m.inputs[PA3] = 0; m.run_ms(600); m.inputs[PF4] = 1; m.run_ms(2600)
check('headphone inserted during a dropout: loudspeakers stay muted afterwards', m.reg.get(PC0) == 1)
m.inputs[PA3] = 1; m.run_ms(1500)
check('headphone removed: loudspeakers back', m.reg.get(PC0) == 0)
m.inputs[PF4] = 0; m.run_ms(1500); click(m, 2); m.run_ms(2500)   # clicks are ignored during the firmware's 1 s wait
check('switch to analog while the host is away: loudspeakers back, volume restored',
      m.reg.get(PC0) == 0 and m.cpu.ram[0xdc] == 0 and volume_on(m))
click(m, 2); m.run_ms(2500)
check('back to USB with no host: muted', m.reg.get(PC0) == 1)
click(m, 1, hold=2600); m.run_ms(3500); st = [m.cpu.ram[0xc4]]
click(m, 1); m.run_ms(7000); st.append(m.cpu.ram[0xc4])
check('standby and power-on with no host: still muted', m.reg.get(PC0) == 1 and st == [1, 2], st)
m.inputs[PF4] = 1; m.run_ms(2600)
check('host appears: loudspeakers back, volume restored', m.reg.get(PC0) == 0 and volume_on(m))
sys.exit(0 if ok else 1)
