# ADAM Audio D3V tweeter dropout fix

**English** | [简体中文](README.zh-CN.md)

An unofficial modification of the ADAM Audio D3V firmware 1.7 that removes the gate which
silences the tweeters at low listening levels, together with the reverse-engineering toolkit
that was used to find it.

> [!WARNING]
> This is not an ADAM Audio product and is not endorsed by ADAM Audio or Focusrite. Flashing
> modified firmware is at your own risk and may void your warranty. The modified firmware has
> been flashed on **one** speaker pair, and the result was judged **by ear only**.

## The problem

At low volume the D3V tweeters fade out or cut out during quiet passages, while the woofers keep
playing. ADAM's firmware 1.7 lists "Improved tweeter behavior with very low signal levels" in its
change log.

The 1.7 image still contains the cause. The DSP (an ADAU1701) runs a level-dependent gain table
on the tweeter path, after the volume control. Its lowest seven points form a downward expander:

| Tweeter-band level | Factory 1.7 gain | This mod |
|---|---|---|
| -90 dBFS | -23.0 dB | 0 dB |
| -87 dBFS | -26.0 dB | 0 dB |
| -84 dBFS | -28.9 dB | 0 dB |
| -81 dBFS | -31.0 dB | 0 dB |
| -78 dBFS | -17.0 dB | 0 dB |
| -75 dBFS | -0.4 dB | 0 dB |
| -72 dBFS | -0.0 dB | 0 dB |
| -69 … -15 dBFS | 0 dB | unchanged |
| -12 … +6 dBFS (limiter) | -0.1 … -13.5 dB | unchanged |

So once the high-frequency content after the volume control drops below about -75 dBFS, the
tweeter is turned down by another 17 to 31 dB.

## The change

Seven parameter words (`p137`..`p143`) are set to 1.0. That is 21 changed bytes in a 22124-byte
image; the size does not change. No code is touched. The tweeter limiter, the woofer compressor
and limiter and the thermal protection are byte-identical to the factory image.

The whole change is [`mods/no-tweeter-gate.params`](mods/no-tweeter-gate.params).

## What is verified and what is not

| | Status |
|---|---|
| The toolkit rebuilds the factory image byte for byte from generated source | Checked by CI on every push |
| Modified image differs from factory in exactly those 21 bytes | Checked by CI |
| Flashing from macOS (Apple Silicon) with the patched updater | Done once, on the author's D3V, no problems |
| Tweeter dropout gone | The author's listening impression. No measurement |
| Windows package | Same firmware, ADAM's unmodified Windows program. CI checks that it starts. **Never used to flash a real D3V** |
| Long-term behaviour | Unknown. One unit, first flashed in November 2026 |

## Download

Get the files from the [latest release](https://github.com/skywalker512/adam-d3v-tweeter-fix/releases/latest).

| File | Use |
|---|---|
| `D3V-Updater-No-Tweeter-Gate-macOS.zip` | Updater app for macOS (Intel and Apple Silicon) |
| `D3V-Updater-No-Tweeter-Gate-Windows.zip` | Updater for Windows 10/11 x64, no installation |
| `d3v_patch.py` | Makes the same updaters on your own computer from ADAM's official download |

The ready-made updaters are ADAM's updater program with the modified firmware file inside.

## Flashing

1. Unplug the D3V's power supply. Connect the speaker to the computer with USB-C, directly, not
   through a hub.
2. Start the updater (see the notes for your system below).
3. Hold the volume knob down, plug the power supply back in, and release the knob when the LED
   pulses purple.
4. Follow the instructions in the updater. Do not unplug anything while it runs. At the end the
   LED flashes green three times and the speaker restarts.

**macOS.** The app carries an ad-hoc signature, because changing the firmware file invalidates
ADAM's. macOS blocks it on first start: open System Settings → Privacy & Security and choose
"Open Anyway", or run `xattr -dr com.apple.quarantine "D3V Updater (No Tweeter Gate).app"`.
An app you build yourself with `d3v_patch.py` is not blocked.

**Windows.** Unzip the whole folder and start `D3V Updater.exe` inside it; the `resources`
folder must stay next to it. SmartScreen may warn about an unknown publisher (ADAM signs only
its installer, not this program). The program needs the Microsoft Edge WebView2 runtime, which
Windows 11 includes; if the window stays empty, install that runtime from Microsoft.

## Going back

Flash again with the official updater from
[ADAM Audio](https://www.adam-audio.com/en/news/industry/d3v-firmware-updater/). The steps are
the same and the result is the factory 1.7 firmware.

If an update fails or the speaker does not start afterwards, repeat the steps above. Update mode
(purple LED) belongs to a separate bootloader that the update does not overwrite. This is
concluded from the firmware image; the bootloader itself was not examined.

## Side effects

- The gate also hid noise. With the mod, very quiet hiss from the source or the USB DAC can be
  audible with your ear close to the tweeter.
- Nothing else is expected to change. Auto standby and the protection circuits do not use the
  changed table entries. This has not been measured on hardware.

## Build the updater yourself

If you prefer not to run a prebuilt package, `d3v_patch.py` does the same on your computer. It
needs Python 3.8 or newer and nothing else.

```
python3 d3v_patch.py          # macOS: creates out/D3V Updater (No Tweeter Gate).app
py d3v_patch.py               # Windows: creates out\D3V Updater (No Tweeter Gate)\
```

It downloads ADAM's official updater 1.0.0, checks its SHA-256, changes the 21 bytes, checks the
SHA-256 of the result (`59f60c30…e98fef`) and puts it into a copy of the updater. It never
talks to the speaker. `--official FILE` uses a package you downloaded yourself.

## Build the firmware from source

The toolkit in [`kit/`](kit) turns the factory image into relocatable assembly, rebuilds it, and
runs it in an ARMv6-M emulator with a model of the board. It needs Python 3 and LLVM
(`brew install llvm`, or `apt install clang llvm`).

```
python3 kit/fetch.py                             # factory image from ADAM's download, SHA-256 checked
python3 kit/split.py                             # image -> build/app.S
python3 kit/build.py                             # must print: IDENTICAL to the factory 1.7 RC4 image
python3 kit/test_reloc.py                        # relocation check
python3 kit/test_emu.py                          # emulator checks
python3 kit/build.py --params no-tweeter-gate    # -> build/no-tweeter-gate.bin
python3 kit/dsp.py list                          # DSP parameters as text
```

[`mods/`](mods) holds further experiments as patches against the generated source. None of them
is in a release, and they are not recommended for flashing:

| Mod | State |
|---|---|
| `fix-usb-resume-mute` | Keeps the speaker muted when USB is re-plugged while muted. Emulator only |
| `usb-guard` + `delay_ms.c` | Hardware mute when USB power disappears. Emulator only, shelved |
| `usb-probe` + `_printf_core.c` | Diagnostic: can the MCU see USB traffic? Flashed once; the answer was no |

[`AGENTS.md`](AGENTS.md) is the lab notebook: hardware facts, rules for changing the firmware,
and what was tried.

## Other finding: the USB pop

The D3V pops when the USB host goes to sleep or a KVM/hub switches hosts. This was investigated
and cannot be fixed in the MCU firmware:

- The USB DAC is a TI PCM2704C. When the bus goes idle it suspends and switches its outputs off,
  and TI documents the resulting pop for this chip family.
- In listening tests the MCU reacts only to USB 5 V being present. A host switch on a powered hub or a sleeping
  computer leaves 5 V on, so the firmware never learns about it. A probe build showed that the
  MCU cannot see the USB data lines in normal operation either.
- Workarounds: click the knob to mute before switching, or feed the D3V through its analog
  input.

## Legal

The tools, patches and documentation in this repository are under the [MIT license](LICENSE).
The repository contains no ADAM Audio firmware or software; the tools download it from ADAM
Audio's server. Release packages contain ADAM Audio's updater and a modified copy of its
firmware, which remain the property of ADAM Audio GmbH. "ADAM Audio" and "D3V" are trademarks
of their owner. If you are the rights holder and want something removed, please open an issue.
