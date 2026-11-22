#!/usr/bin/env python3
"""8 kHz staircase with a constant 500 Hz pilot, meant to be recorded with a phone.

Mono, 48 kHz, 24-bit, 96 s:
   0..4 s    pilot only            (8 kHz noise floor of the recording)
   4..88 s   pilot + 8 kHz, -21 dBFS falling 3 dB every 4 s down to -81 dBFS (21 steps)
  88..92 s   pilot only
  92..96 s   digital silence
The pilot (500 Hz, -30 dBFS) goes through the woofer and never changes, so the ratio
8 kHz / 500 Hz per step cancels the phone's automatic gain.
"""
import math, struct, wave

FS, STEP_S, START_DB, STEPS, PILOT_DB = 48000, 4, -21, 21, -30
pilot = 10 ** (PILOT_DB / 20)
frames = bytearray()
total = FS * 96
fade = int(FS * 0.01)
for n in range(total):
    t = n / FS
    p = pilot if t < 92 else 0.0
    k = int((t - 4) // STEP_S)
    a = 10 ** ((START_DB - 3 * k) / 20) if 0 <= k < STEPS else 0.0
    edge = min(n % (FS * STEP_S), fade) / fade            # 10 ms ramp at each step start
    prev = 10 ** ((START_DB - 3 * (k - 1)) / 20) if 1 <= k < STEPS else (0.0 if k <= 0 else 10 ** ((START_DB - 3 * (STEPS - 1)) / 20) if k == STEPS else 0.0)
    a = prev + (a - prev) * edge
    v = p * math.sin(2 * math.pi * 500 * t) + a * math.sin(2 * math.pi * 8000 * t)
    frames += struct.pack('<i', int(round(v * 8388607)))[:3]
with wave.open('gate_test_8k_pilot.wav', 'wb') as w:
    w.setnchannels(1); w.setsampwidth(3); w.setframerate(FS)
    w.writeframes(bytes(frames))
