#!/usr/bin/env python3
"""Staircase tones for checking the D3V tweeter gate by ear / spectrum app.

Each file: mono, 48 kHz, 24-bit. Level starts at -21 dBFS and drops 3 dB every
5 s down to -81 dBFS (21 steps, 105 s). Level at time t: -21 - 3*floor(t/5) dBFS.
  gate_test_8k.wav   -> tweeter band (goes through the gate)
  gate_test_500.wav  -> woofer band (control, no gate)
"""
import math, struct, wave

FS, STEP_S, START_DB, STEPS = 48000, 5, -21, 21

def make(path, freq):
    frames = bytearray()
    n_step = FS * STEP_S
    fade = int(FS * 0.01)
    amp_prev = 10 ** (START_DB / 20)
    for s in range(STEPS):
        amp = 10 ** ((START_DB - 3 * s) / 20)
        for i in range(n_step):
            a = amp_prev + (amp - amp_prev) * i / fade if i < fade else amp
            n = s * n_step + i
            v = int(round(a * math.sin(2 * math.pi * freq * n / FS) * 8388607))
            frames += struct.pack('<i', v)[:3]
        amp_prev = amp
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(3); w.setframerate(FS)
        w.writeframes(bytes(frames))

make('gate_test_8k.wav', 8000)
make('gate_test_500.wav', 500)
