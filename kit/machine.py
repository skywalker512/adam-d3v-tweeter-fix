"""D3V main board model around kit/emu.py: Nuvoton M031 peripherals as far as the
firmware touches them, a bit-banged I2C listener standing in for the ADAU1701,
scriptable ADC channels / input pins, and an event log.

    m = D3V(image_bytes); m.run_ms(3000); m.log
"""
from emu import CPU, Halt

PIN = 0x40004800                       # GPIO pin data: PIN + 0x40*port + 4*pin
SCL, SDA = PIN + 4, PIN + 8            # PA1, PA2
PORTS = 'ABCDEFGH'
TMR0_IRQ = 8


def pin(name):                         # 'PB4' -> register address
    return PIN + 0x40 * PORTS.index(name[1]) + 4 * int(name[2:])


class D3V:
    TICK_INSNS = 300                   # emulated instructions per 100 us timer tick

    def __init__(self, image, settings=b''):
        flash = bytearray(b'\xff' * 0x8000)
        flash[0x2000:0x2000 + len(image)] = image
        flash[0x7e00:0x7e00 + len(settings)] = settings
        self.cpu = c = CPU(flash)
        c.io_read, c.io_write = self.io_read, self.io_write
        self.reg = {}
        self.adc = {0: 0, 1: 0, 2: 0, 3: 2000, 5: 2100, 15: 100}   # knob mid, switches pos 0, ~normal temp, signal present
        self.inputs = {pin('PB4'): 1, pin('PA3'): 1, pin('PF4'): 0, pin('PF5'): 0}
        self.log = []                  # (tick, kind, payload)
        self.tick = 0
        self.irq_on = False
        self.tmr_pending = 0
        self.scl = self.sda = 1
        self.i2c_bits, self.i2c_bytes, self.i2c_active, self.i2c_ack = [], [], False, False

    # ---- peripherals --------------------------------------------------------
    def io_read(self, a, size):
        if PIN <= a < PIN + 0x200:
            if a == SDA and self.i2c_ack:
                return 0                                   # slave ACK
            return self.inputs.get(a, self.reg.get(a, 0))
        if 0x40043000 <= a < 0x40043080:
            return self.adc.get((a - 0x40043000) >> 2, 0)
        if a == 0x40043080: return self.reg.get(a, 0) & ~0x1000
        if a == 0x40043184: return 1                       # ADC calibration done
        if a == 0x40000100: return 1                       # register lock open
        if a == 0x40000250: return 0xFFFF                  # all clocks stable
        if a == 0x40050008: return self.tmr_pending
        if a in (0x4000C010, 0x4000C018, 0x4000C040): return 0
        if a == 0xE000E018:
            load = self.reg.get(0xE000E014, 0xFFFFFF)
            return load - (self.cpu.cycles * 2) % (load + 1)
        return self.reg.get(a, 0)

    def io_write(self, a, v, size):
        if a in (SCL, SDA):
            self.i2c(a, v & 1)
        elif PIN <= a < PIN + 0x200:
            if self.reg.get(a) != v:
                p = (a - PIN) >> 6
                self.log.append((self.tick, 'gpio', 'P%s%d=%d' % (PORTS[p], (a & 0x3f) >> 2, v & 1)))
        elif a == 0xE000E100:
            self.irq_on |= bool(v >> TMR0_IRQ & 1)
        elif a == 0x40050008:
            if v & 1: self.tmr_pending = 0
            return
        elif a == 0x4000C010 and v & 1:
            self.fmc()
        self.reg[a] = v

    def fmc(self):
        cmd, addr = self.reg.get(0x4000C00C, 0), self.reg.get(0x4000C004, 0)
        f = self.cpu.flash
        if cmd == 0x00:
            self.reg[0x4000C008] = int.from_bytes(f[addr:addr + 4], 'little')
        elif cmd == 0x21:
            f[addr:addr + 4] = (self.reg.get(0x4000C008, 0) & int.from_bytes(f[addr:addr + 4], 'little')).to_bytes(4, 'little')
            self.log.append((self.tick, 'flash', 'write %04x=%08x' % (addr, self.reg.get(0x4000C008, 0))))
        elif cmd == 0x22:
            f[addr & ~0x1ff:(addr & ~0x1ff) + 0x200] = b'\xff' * 0x200
            self.log.append((self.tick, 'flash', 'erase %04x' % (addr & ~0x1ff)))

    def i2c(self, a, v):
        if a == SDA:
            if self.scl and self.sda != v:
                if v == 0:                                 # START
                    self.i2c_active, self.i2c_bits, self.i2c_bytes = True, [], []
                elif self.i2c_active:                      # STOP
                    self.i2c_active = False
                    if self.i2c_bytes:
                        self.log.append((self.tick, 'i2c', bytes(self.i2c_bytes)))
            self.sda = v
        else:
            if v and not self.scl and self.i2c_active:     # rising clock edge
                if len(self.i2c_bits) == 8:                # ninth clock: the slave acknowledges
                    self.i2c_bytes.append(int(''.join(map(str, self.i2c_bits)), 2))
                    self.i2c_bits, self.i2c_ack = [], True
                else:
                    self.i2c_bits.append(self.sda)
            elif not v:
                self.i2c_ack = False
            self.scl = v

    # ---- running ------------------------------------------------------------
    def run_ticks(self, n):
        c, step = self.cpu, self.cpu.step
        for _ in range(n):
            for _ in range(self.TICK_INSNS):
                step()
            self.tick += 1
            if self.irq_on and not c.in_irq:
                self.tmr_pending = 1
                c.irq(TMR0_IRQ)

    def run_ms(self, ms):
        self.run_ticks(ms * 10)

    def run_until(self, cond, max_insns=2_000_000):
        """Step until cond() is true; returns the number of instructions executed (None on timeout)."""
        c, n = self.cpu, 0
        while not cond():
            if n >= max_insns:
                return None
            c.step()
            n += 1
            if n % self.TICK_INSNS == 0:
                self.tick += 1
                if self.irq_on and not c.in_irq:
                    self.tmr_pending = 1
                    c.irq(TMR0_IRQ)
        return n

    def events(self, kind):
        return [(t, p) for t, k, p in self.log if k == kind]


def decode_i2c(log):
    """Collapse ADAU1701 safeload traffic into readable (tick, text) lines."""
    out, data, addr, led = [], {}, {}, 0
    for t, k, p in log:
        if k == 'gpio' and p[:4] in ('PB12', 'PB13', 'PB14'):
            led += 1                                      # LED pins: summarised, PWM would flood the log
            continue
        if led:
            out.append((t, 'led: %d pin changes' % led)); led = 0
        if k != 'i2c':
            out.append((t, '%s %s' % (k, p)))
            continue
        reg = p[1] << 8 | p[2] if len(p) >= 3 else None
        if reg is not None and 0x810 <= reg <= 0x814 and len(p) == 8:
            data[reg - 0x810] = int.from_bytes(p[4:8], 'big')
        elif reg is not None and 0x815 <= reg <= 0x819 and len(p) == 5:
            addr[reg - 0x815] = p[3] << 8 | p[4]
        elif reg == 0x81c and p[3:] == b'\x00\x3c':
            for s in sorted(addr):
                out.append((t, 'dsp p%d = 0x%07x' % (addr[s], data.get(s, 0))))
            data, addr = {}, {}
        elif reg == 0x81c:
            out.append((t, 'dsp core control = 0x%04x' % int.from_bytes(p[3:], 'big')))
        else:
            out.append((t, 'dsp block write @0x%04x, %d bytes' % (reg, len(p) - 3)))
    if led:
        out.append((log[-1][0], 'led: %d pin changes' % led))
    return out
