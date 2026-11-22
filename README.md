# ADAM Audio D3V tweeter dropout fix

**English** | [简体中文](README.zh-CN.md)

Unofficial patch for ADAM Audio D3V firmware 1.7 that removes the low-volume tweeter noise gate,
plus the reverse-engineering toolkit used to find it.

- **21 changed bytes** in the DSP gain table — no MCU code changes, same binary size as factory 1.7.
- **Protection intact:** tweeter limiter, woofer compressor/limiter, and thermal protection are untouched.
- **Reversible:** flash ADAM's official 1.7 updater at any time to restore stock firmware.

> [!WARNING]
> Unofficial and not affiliated with ADAM Audio or Focusrite. Flash at your own risk (may void
> warranty). Tested so far on **one** speaker pair via macOS, judged **by ear only**.

## Why it happens

Even on official firmware 1.7, the D3V tweeters can fade or cut out during quiet passages at low
volume while the woofers keep playing.

To hide idle hiss, the factory ADAU1701 DSP puts an automatic attenuation rule (a noise gate) on
the tweeter path: whenever the high-frequency signal falls below roughly `-75 dBFS`, the DSP treats
it as noise and cuts it by another 17–31 dB (dropping perceived loudness to about 1/3 or under 1/8).

Because this check runs **after** the volume control, turning the volume down pushes quiet highs in
normal music below that threshold too, so the DSP mistakes them for noise and suddenly muffles or
cuts out the tweeters:

| Tweeter-band level | Factory 1.7 gain | This mod |
|---|---|---|
| -90 dBFS | -23.0 dB | 0 dB |
| -87 dBFS | -26.0 dB | 0 dB |
| -84 dBFS | -28.9 dB | 0 dB |
| -81 dBFS | -31.0 dB | 0 dB |
| -78 dBFS | -17.0 dB | 0 dB |
| -75 dBFS | -0.4 dB | 0 dB |
| -72 dBFS | < -0.01 dB | 0 dB |
| -69 … -15 dBFS | 0 dB | unchanged |
| -12 … +6 dBFS (limiter) | -0.1 … -13.5 dB | unchanged |

This patch removes that attenuation by setting those seven 4-byte parameters (`p137`..`p143`, 28
bytes total; 21 bytes change since each high byte is already `0x00`) to `1.0` (`0x00800000`). The
`-12 … +6 dBFS` overload limiter is kept byte-identical to factory. See
[`mods/no-tweeter-gate.params`](mods/no-tweeter-gate.params).

## Download

Get the files from the [latest release](https://github.com/skywalker512/adam-d3v-tweeter-fix/releases/latest).
Most users only need the `.zip` for their OS — the patched firmware is already bundled inside.

| File | Use |
|---|---|
| `D3V-Updater-No-Tweeter-Gate-macOS.zip` | **macOS** (Intel & Apple Silicon) pre-patched updater |
| `D3V-Updater-No-Tweeter-Gate-Windows.zip` | **Windows 10/11 x64** pre-patched portable updater |
| `d3v_patch.py` | Optional: build the same updaters locally from ADAM's official package |
| `D3V_MCU+DSP_V1_7_RC4_no_tweeter_gate.bin` | Optional: raw patched firmware image |
| `SHA256SUMS.txt` | Optional: SHA-256 checksums |

## How to flash

1. Unplug the D3V's power cable and connect USB-C directly to your computer (no USB hub).
2. Launch the patched updater.
3. **Hold the volume knob**, plug power back in, and release when the LED pulses **purple**.
4. Follow the updater prompts without unplugging (about 10–15 s). The LED flashes green three times
   and restarts automatically.

- **macOS:** Unzip to get `D3V Updater (No Tweeter Gate).app`. Because it is ad-hoc signed, allow it
  in **System Settings → Privacy & Security → Open Anyway**, or run:
  `xattr -dr com.apple.quarantine "D3V Updater (No Tweeter Gate).app"`
- **Windows:** Extract the full zip first, then run `D3V Updater.exe` (do not launch it from inside
  the zip preview). SmartScreen may warn about an unknown publisher. If the window opens blank,
  install the Microsoft Edge WebView2 runtime (preinstalled on Windows 11).

## Rollback

Run the official updater from
[ADAM Audio](https://www.adam-audio.com/en/news/industry/d3v-firmware-updater/) with the same
purple-LED steps to return to stock 1.7. If a flash fails, repeat the purple-LED steps — update mode
lives in a separate bootloader that flashing does not overwrite (inferred from the firmware image;
the bootloader itself was not read out).

## Side effects

- **Close-up idle hiss:** Without the gate, faint hiss from the USB DAC or source can be audible
  with your ear close to the tweeter in a quiet room.
- **Auto standby and driver protection are unaffected** based on firmware analysis (not measured with
  test instruments).

## Verification status

| Item | Status |
|---|---|
| Factory 1.7 rebuilt byte-for-byte from disassembled source | Verified by CI on every push |
| Patched image differs in only those 21 bytes | Verified by CI |
| macOS (Apple Silicon) flash & dropout fix | Tested once on the author's pair, verified by ear |
| Windows package | Pre-patched with the same firmware; launches in CI, **not yet live-flashed** |
| Long-term behaviour | Unknown (one pair, first flashed Nov 2026) |

---

## Developers & DIY build

### Build the updater yourself

[`patcher/d3v_patch.py`](patcher/d3v_patch.py) (also in Releases as `d3v_patch.py`) builds the same
updaters locally using Python 3.8+ with no extra dependencies:

```bash
python3 patcher/d3v_patch.py  # macOS -> out/D3V Updater (No Tweeter Gate).app
py patcher\d3v_patch.py       # Windows -> out\D3V Updater (No Tweeter Gate)\
```
*(Omit `patcher/` if downloaded standalone from Releases.)*

It downloads ADAM's official Updater 1.0.0 (which bundles factory firmware 1.7), checks SHA-256,
patches the 21 bytes (result SHA-256 `59f60c30…e98fef`), and repackages it without talking to the
speaker. Use `--official FILE` for a local official download.

### Build firmware from source

[`kit/`](kit) disassembles the factory image to relocatable ARMv6-M assembly, rebuilds it, and runs
board-level emulator tests (requires Python 3 and LLVM):

```bash
python3 kit/fetch.py                             # extract factory image (SHA-256 checked)
python3 kit/split.py                             # image -> build/app.S
python3 kit/build.py                             # must match factory 1.7 RC4 byte-for-byte
python3 kit/test_reloc.py                        # relocation check
python3 kit/test_emu.py                          # emulator checks
python3 kit/build.py --params no-tweeter-gate    # -> build/no-tweeter-gate.bin
python3 kit/dsp.py list                          # dump DSP parameters
```

Experimental patches in [`mods/`](mods) (not in releases, not recommended for flashing):

| Mod | Status |
|---|---|
| `fix-usb-resume-mute` | Keep mute state across USB replug (emulator only) |
| `usb-guard` + `delay_ms.c` | Hardware mute on USB 5 V loss (emulator only, shelved) |
| `usb-probe` + `_printf_core.c` | Diagnostic: can the MCU listen to USB? Flashed once — no |

Full hardware notes and experiments: [`AGENTS.md`](AGENTS.md).

### Other finding: USB sleep / KVM pop

The D3V pops when a USB host sleeps or a powered KVM/hub switches hosts. MCU firmware cannot fix
this:

- The USB DAC (TI PCM2704C) suspends when the bus goes idle and switches off its outputs — a known
  TI-documented pop.
- The MCU only senses USB 5 V, which stays high on host sleep or powered hub switches, and a
  diagnostic probe confirmed the MCU cannot see the USB data lines during normal operation.
- **Workarounds:** Click the knob to mute before switching hosts, or use the TRS analog input.

## Legal

Tools, patches, and docs are [MIT licensed](LICENSE). No ADAM Audio binaries are stored in this
repository; scripts fetch them from ADAM Audio's server. Release archives contain ADAM Audio's
updater and a modified firmware copy, which remain the property of ADAM Audio GmbH. "ADAM Audio"
and "D3V" are trademarks of their respective owners. Rights holders may open an issue for removal.
