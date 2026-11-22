# D3V firmware workspace

Reverse-engineering workspace for the ADAM Audio D3V firmware 1.7 RC4
(`fw/D3V_MCU+DSP_V1_7_RC4.bin`, Nuvoton M031-class Cortex-M0 application at flash 0x2000
plus an embedded ADAU1701 program/parameter image).
Public repository: github.com/skywalker512/adam-d3v-tweeter-fix (README.md English, README.zh-CN.md Chinese; keep both in step).

## Layout

- `fw/`, `pkg/` factory image and updater. Never modify, never commit (git-ignored, as are `patched/`, `dsp/`,
  `ida/`, the Ghidra dumps and `ref/` documents). A fresh clone gets `fw/` from `python3 kit/fetch.py`.
- `patcher/d3v_patch.py` standalone, standard library only: official download -> patched macOS app / Windows folder.
  Shipped in releases and used by CI to make the release packages; its macOS output is byte-identical to the
  app that was used for the first flash.
- `.github/workflows/build.yml` CI: factory round trip, `test_reloc`, `test_emu`, `test_c`, no-tweeter-gate image
  (SHA-256 pinned), packages on macOS and Windows runners; a tag `v*` publishes a GitHub release.
- `kit/` tooling (Python 3 standard library only; clang + llvm-objcopy from `$D3V_LLVM`, Homebrew LLVM or PATH).
  - `split.py` image -> `build/app.S` (relocatable source) + `build/dsp/*.bin`
  - `build.py` source -> image; `--mod NAME` applies `mods/NAME.patch`, `--params NAME` applies `mods/NAME.params`,
    `--c FUNC` replaces function FUNC by `mods/FUNC.c` compiled with clang -Oz
    `--keep-size` pads each `--c` replacement to the factory length of that function (assembly fails if the
    C code is larger), so nothing after it moves and the image size stays 22124
  - `symbols.txt` function names fed into `split.py`
  - `emu.py`, `machine.py` ARMv6-M interpreter and board model (I2C listener, ADC, pins, flash settings page)
  - `dsp.py` parameter RAM as text (`python3 kit/dsp.py list`)
- `mods/` changes kept as patches against the generated source, never as edited binaries.
- `build/` generated; safe to delete.
- `ghidra/`, `dsp/`, `ref/`, `ida/`, `patched/`, `test/` earlier analysis artefacts.
  `ghidra/scripts/SwitchFix.java` is the jump-table override that makes Ghidra decompile `led_set_state` (0x434c).

## Commands

```
python3 kit/fetch.py            # fw/ from ADAM's official download (fresh clone only)
python3 kit/split.py            # regenerate build/app.S
python3 kit/build.py            # must print: IDENTICAL to the factory 1.7 RC4 image
python3 kit/test_reloc.py       # relocation check, 0 mismatches expected (seconds)
python3 kit/test_emu.py         # emulator + relocation + mod checks, all "ok" expected (~90 s)
python3 kit/test_c.py           # C replacement vs factory routine, all "ok" expected (~40 s)
python3 kit/test_usb_guard.py   # usb-guard mod vs factory in the emulator, all "ok" expected (~4 min)
python3 kit/isr_budget.py [img] # worst-case cycles of the 10 kHz timer handler; must stay <= 153
python3 kit/test_usb_probe.py   # USB listen probe vs the image without it, all "ok" expected (~2 min)
python3 kit/build.py --mod fix-usb-resume-mute --params no-tweeter-gate
```

Run `build.py` and both tests after touching anything in `kit/`. A new mod needs an
emulator check in `test_emu.py` style before anyone considers flashing it.

## Rules

- Never flash a device or launch the updater; that is the user's decision each time.
- Never commit ADAM Audio's firmware, updater, or dumps derived from them (disassembly, decompilation, DSP blocks).
- Only the no-tweeter-gate image goes into releases. `patcher/d3v_patch.py` pins the SHA-256 of every input and of
  the patched image; a change to `mods/no-tweeter-gate.params` needs the same change there and in the workflow.
- One change per flashed image. Images whose size differs from the factory 22124 bytes have never been flashed.
- Do not touch limiter / thermal parameters (p163..p169, p172..p280) without a separate safety analysis.
- Addresses in `kit/analyze.py` and `kit/split.py` are specific to 1.7 RC4; another firmware version needs them re-derived.
- A C replacement must be compared with the factory routine in the emulator (see `kit/test_c.py`). Keep the
  bit-banged I2C routines as factory assembly: their bus speed comes from the unoptimised code, not from a delay.
- Do not add work to `TMR0_IRQHandler`. `i2c_half_bit_delay` stalls (seen in the emulator) when an interrupt
  between its two SysTick reads takes more than 192 CPU cycles in total; the factory handler's worst path is
  115 cycles + 32 entry/exit by `kit/isr_budget.py`'s cycle model, so only ~38 cycles are spare, and real flash
  wait states are not modelled. Poll from the main loop / `delay_ms` instead (see `mods/delay_ms.c`).
- The DSP instruction set is undocumented: parameters are editable, program words are not understood at bit level.
- Assembly-only builds (factory round trip, `--mod`, `--params`) are byte-identical across LLVM 18..22 (CI uses
  Ubuntu's clang 18). Builds with `--c` depend on the compiler version: the SHA-256 values quoted below for
  `usb-guard` and `usb-probe` are from Homebrew LLVM 22.1.8, clang 18 gives different (untested) code.
  `split.py` emits `.balignw N, 0`, not `.balign N, 0`, because LLVM 18 replaces a 1-byte zero fill by NOPs.

## Device log

- User flashed `patched/D3V Updater (No Tweeter Gate).app` (image sha256 `59f60c30…`, same size as factory,
  21 bytes changed) directly onto their D3V from macOS 27.2.1 (arm64); reported it went through without problems.
  The official updater was not run first. Its arm64 code is byte-identical to the patched app's (only Mach-O
  signature fields differ), so the rollback tool is the same code that just worked.
- Pre-flash listening test (factory firmware of unknown version, system volume 30 % = -29 dB in the USB DAC, knob
  position not recorded): 8 kHz staircase faded gradually into hiss, 500 Hz faded smoothly, no hiss when idle.
  Inconclusive for the gate hypothesis. No post-flash measurement yet.
- The speaker enumerates as USB 08bb:2704 (TI PCM2704-family default ID), full speed, hardware volume 0..-64 dB.
  The MCU is not on USB outside update mode, so the firmware version cannot be read from the host.
- After flashing the no-tweeter-gate image the user reported the tweeter dropout as solved (listening only,
  no measurement).

## USB pop notes

- `ref/pcm2704c_SBFS036B.pdf` (TI datasheet, primary source): SSPND is active low (low = suspend, high =
  operational), asserted after ~5 ms of bus idle, released when the bus is active again. It follows bus suspend,
  not playback; with no audio data the output sits at bipolar zero. In suspend or without supply the outputs
  become 26 kOhm; TI's reference circuits mention the resulting suspend pop.
- PF4 is NOT SSPND (earlier inference, now refuted on the device, see "Real-device USB findings"). It behaves
  like "USB 5 V present". Not traced on the board.
- Emulated factory behaviour in USB input mode: PF4 low -> DSP volume 0 (also straight after power-on);
  PF4 falling -> volume-0 safeload committed 7..32 ms later (30 ms poll) and then the DSP ramp (~85 ms time
  constant); PF4 rising -> volume restored after ~2035 ms. USB events never touch PC0 (speaker mute) or PF3.
  PA3 low -> PC0 = 1 within 20 ms; PA3 high -> PC0 = 0 after 500 ms.
- Candidate fix `usb-guard` = `mods/usb-guard.patch` + `mods/delay_ms.c`, built with
  `python3 kit/build.py --mod usb-guard --c delay_ms --params no-tweeter-gate` (22252 bytes, +128, still 44 flash
  pages like the factory image). Emulator: PC0 = 1 about 4 us after PF4 falls (worst 3.7 ms if a volume
  calculation + I2C write is in progress), held until 1.8 s after PF4 rises, released before the firmware's
  volume restore; everything else identical to factory. NOT flashed. Unknown on hardware: whether PC0 silences
  the pop, whether asserting PC0 clicks, whether PF4 falls before the transient, and whether the bootloader
  accepts a longer image.
  SHELVED: it only triggers on PF4 low, which the user's hub switch never produces (below).

## Real-device USB findings (user's listening tests, no instruments)

- Setup: D3V behind a self-powered GenesysLogic USB hub that is switched between two hosts (not the monitor's
  hub, as first assumed). Every switch gives two pops, loud then quieter, whether or not audio is playing;
  playback resumes right after the second pop, without a 2..3 s silent gap.
- Knob affects the pops, and single-click mute (DSP volume 0) removes them -> the transient enters before the
  DSP volume stage.
- Plug in the headphone jack (PC0 = 1): no pop from the loudspeakers, both pops audible in the headphones.
  So PC0 does block it for the speakers, and the headphone output is fed from the same upstream path.
- Muted, then USB-C cable unplugged and replugged: sound comes back by itself with the mute LED still on. This
  is the `usb_active_restore_volume` bug (`mods/fix-usb-resume-mute.patch`) seen on hardware.
  Muted, then hub switched away and back: stays muted. (User's wording: "重新插拔 usb 是可以重新出声的，但是切换
  kvm 不行"; an earlier run of this test was spoiled by NetEase Music not restarting its stream.)
  -> PF4 goes low on cable removal but not on the hub switch.
- The device's descriptor is TI's datasheet example ROM (vendor string "Vendor strings are placed here.",
  bus-powered, 250 mA; macOS reports 250 mA allocated) with only the product string changed. The datasheet allows
  ROM descriptors only with PSEL = HOST = high, so the PCM2704C is strapped bus-powered: it lives on the cable's
  5 V. On a self-powered hub it therefore stays powered while the bus goes idle and must enter suspend (26 kOhm
  outputs, TI's "pop-noise level for suspend"), while PF4 does not move. Hence PF4 tracks the 5 V, not SSPND.
- Consequence: the MCU has no input that changes on a host switch / bus suspend with 5 V present (the firmware
  reads only PF4, PA3, the button and the ADC channels). No MCU-only mod can react to it automatically. The 2 s
  restore delay and any PF4-based guard only cover cable removal or hubs that cut 5 V.
- Working workaround confirmed by the user once: single-click mute before switching the hub, click again after.

## DSP readback route for the hub-switch pop (researched, nothing built)

Idea: the MCU polls the ADAU1701 data capture register for the pre-volume input sample and asserts PC0 when
it sees the pop. Facts collected:

- ADI (datasheet p.38, EngineerZone threads 64734 and 103324): write `(progCount << 2) | regSel` (regSel 0b10 =
  accumulator) to 0x081A, wait >= 2 sample frames, read 3 bytes. No program change needed, reading registers is
  click-free, the value is one raw sample (no level detection). The program-counter index normally comes from
  SigmaStudio's `trap.dat`, which we do not have; candidates from `dsp/disasm.txt`: step 0x00D/0x018 (input x
  slewed volume, L/R), inputs are data 0x0000/0x0001.
- The firmware has no I2C read routine, but `i2c_send_byte` already reads SDA for the ACK. Its cost in the
  emulator's cycle model is 660 cycles per byte (~1.5 us per bit at 48 MHz, not measured on hardware), so one
  readback is ~0.1..0.2 ms.
- ADAU1701 analog-in to analog-out latency is ~1 ms at 48 kHz (EngineerZone 66439/65466); the DAC share
  (roughly half, not in the current datasheet) is the only head start the MCU gets.
- Step-input simulation through the real biquads (woofer bq02+bq14+bq15, tweeter bq00+bq01): muting 1 ms after
  the edge removes only ~6 dB of the woofer drive energy and none of the tweeter's; 2..3 ms: ~3 dB. So reacting
  after the edge is useless; only pre-empting inside the DAC delay would work.
- Unknown and not measurable without instruments or a diagnostic flash: real I2C speed, how fast PC0 silences
  the amplifier, pop amplitude at the DSP input relative to music (needed for a single-sample threshold),
  the capture index. Main-loop housekeeping (up to ~3.7 ms during a volume calculation) breaks the timing.
- TI application note "Usage and Notice for USB Interface Audio Products" section 8 / Q20: the suspend pop of
  the PCM2704 family is a known property (output impedance changes to 26 kOhm); TI's fixes are analog networks.
  E2E thread 1044131: Vout jumps at the same moment SSPND asserts, so SSPND gives no advance warning either.

## Why the Apple USB-C headphone adapter does not pop on the same hub

- macOS logs: two Apple USB-C to 3.5 mm adapters (05ac:110a) sat on the same GenesysLogic hub as the D3V and
  were removed / re-enumerated together with it at the hub switches of 13:16, 13:17 and 13:32 on 2026-11-22.
  The user reports no pop from them. So both DACs see the same USB event; the difference is the analog output.
- PCM2704C: single supply, output biased at mid-supply behind a DC blocking capacitor; in suspend the output
  becomes 26 kOhm to ground and the capacitor discharges (TI application note section 8, Q20).
- Apple adapter: Cirrus Logic 46L06 per teardowns (cabledo, 52audio); no public datasheet. Ground-referenced
  capless output with de-pop sequencing is an inference: the connector-sized board has no room for the >= 220 uF
  per channel a capacitor-coupled 32 Ohm drive needs, and Cirrus/TI/Maxim documents describe that architecture
  as removing the capacitor charge/discharge pop.
- Possible workaround not yet tried by the user in this form: Apple adapter on the hub -> D3V analog input
  (green LED), D3V's own USB unused. What the adapters were plugged into earlier is not known.

## Can the MCU listen to the USB bus? (answered by the probe below: no)

- The MCU has its own USB device port: the updater uses hidapi with PID 0x3f00, and the macOS kernel log of the
  flash on 2026-11-22 shows, on one port without re-plugging: 12:37:56 `08bb/2704 ADAM Audio D3V` enumerated,
  12:37:58 it is lost and `0416/3f00 WPM USB` (Nuvoton HID ISP bootloader) enumerates, 12:38:12 after the flash
  `WPM USB` goes away and `08bb/2704` is back. So the part is an M032-class (USBD) chip and both chips share the
  USB-C socket; the bootloader can take the bus away from the PCM2704.
- The 1.7 RC4 application never touches USBD (no 0x400C0000 access), never writes GPA_MFP, and leaves PA12..PA14
  unconfigured. `gpio_init`: outputs PA0, PB12..14, PC0, PF2, PF3, PF15; inputs PF4, PF5, PA3 (quasi), PB4 (quasi).
  PF5 is not USB: high for 3.5 s (timer handler) makes main re-send the volume.
- Unknown board fact that decides everything: USB switch IC (MCU pins off the bus in normal mode -> cannot
  listen) or D+/D- wired in parallel with the PCM2704 gated some other way (MCU pins on the bus -> can listen).
  Not decidable from the image or from host logs.
- If on the bus: Nuvoton's TRM says the USBD block flags suspend after 3 ms without bus activity and has a SOF
  interrupt; the PCM2704 suspends after ~5 ms, so the MCU would know ~2 ms BEFORE the pop and could assert PC0.
  Not known: whether USBD reports bus state with the D+ pull-up off (listen-only), whether enabling the PHY
  disturbs the PCM2704, and the main loop's worst-case 3.7 ms latency could use up the margin.
- Ways to find out: open the speaker and look for a switch IC at the USB socket, or flash a probe build that
  enables USBD without pull-up and shows SOF/suspend on the LED (size-changed image, never flashed before).

## Brick-risk facts (checked in the image, bootloader itself never seen)

- The application cannot enter update mode by itself: no SCB AIRCR / SYS_IPRST0 reset, no FMC boot-select;
  FMC is used only by `settings_save` (APUEN, rolling 4-byte writes 0x7E00..0x7FFF, erase of page 0x7E00) and the
  settings read. Flash is 32 KB: bootloader below 0x2000 (not in the update image, no backup exists), application
  0x2000..0x7DFF (24064 bytes max), settings page 0x7E00.
- Update mode is therefore entered by the bootloader (knob held at power-on); kernel log 2026-11-22 12:37:56..58
  shows the PCM2704 enumerating first and `0416/3f00 WPM USB` replacing it ~3 s later.
- A longer image changes only the byte count and the number of ISP packets (22124 -> 396, 22252 -> 398); the
  512-byte page count stays 44 up to 22528 bytes. Whether the bootloader has any length assumption is unknown.
- Before flashing any new-code image, flash a functionally identical image with a different length first
  (current no-tweeter-gate image plus inert padding) to separate "bootloader accepts another size" from
  "the new code works".
- Bootloader guess: a modified copy of Nuvoton's public ISP_HID sample (OpenNuvoton/M031BSP SampleCode/ISP/ISP_HID,
  `isp_user.c`). Matches: USB ID 0416:3F00, HID transport, command 0xA0 with start field 0 and a length field.
  In the public code CMD_UPDATE_APROM erases the whole application area regardless of length, then writes
  `TotalLen` bytes taken from the packet; nothing depends on a fixed size. Differences here (application at
  0x2000, ~3 s before it takes the bus) show it was modified, and those modifications are unknown.
- For a length-only test image pad with 0xFF in a multiple of 4 bytes: erased flash is 0xFF, so the flash
  contents end up identical to the unpadded image; only the length field and packet count differ.
  `kit/build.py` already refuses images that would reach the settings page at 0x7E00.

## Switch IC vs parallel wiring: evidence from the flash log (Gemini's observation, re-checked)

- Kernel log 2026-11-22: entering update mode logs `hardware connection lost` for the PCM2704 (12:37:58).
  Leaving it does NOT: 12:38:11.526..12:38:12.072 eleven `transaction error` on `WPM USB` endpoint 0x81, then
  `destroying WPM USB: reset API call` and `08bb/2704` enumerates. So D+ never dropped when the MCU reset.
- That fits a USB switch IC with the PCM2704 powered and pulling D+ up behind it, and does not fit parallel
  wiring: there the PCM2704 would have to be unpowered during the update (otherwise two devices answer at
  address 0) and its power-up would leave D+ low far longer than the 2.5 us disconnect threshold.
  Conclusion: the MCU's USB pins are most likely NOT on the bus in normal operation. Not proven.
- Dead code usable for same-size mods (reachable only from `Hard_Fault_Handler`): `_printf_core` 0x3df8..0x40cc
  (724 bytes), `stackDump` 0x5abc..0x5b64 (168), `printf` 0x3c34 (32), `fputc` 0x426e (18). A mod placed inside
  that region keeps the image at 22124 bytes and every other byte unchanged; the HardFault print is lost.
- If a probe is ever flashed, prefer reading PA14/PA13 (USB_D+/D- on M032) as plain GPIO with the internal
  pull-down and showing the level on the LED while the user plugs/unplugs the USB cable. A USBD listen-only
  probe is ambiguous: "hears nothing" could also mean the block does not report without the pull-up.

## USB listen probe (built, emulator-checked, flashed once: slow blink)

- `python3 kit/build.py --mod usb-probe --c _printf_core --params no-tweeter-gate --keep-size` ->
  `build/usb-probe+no-tweeter-gate+_printf_core.bin`, 22124 bytes, sha256 `b4faa184…`. Against the image the user
  runs now it differs in 684 bytes: 0x3df8..0x40c7 (old `_printf_core`) and the call at 0x46d2.
- At mains power-on, after `gpio_init`, for 10 s: USBD clock on, `SE0 = 0`, `ATTR = 0x6D0` (transceiver +
  controller on, D+ pull-up off), poll `USBD_FN`. LED toggles every 100 ms if the frame number advances (host's
  1 ms SOF heard), every 500 ms if not. Then ATTR/SE0/clock/LED pins are restored and start-up continues.
- Why USBD and not plain GPIO: M031BSP `gpio_reg.h` has no PUSEL (no internal pull-down) and `sys.h` has no USB
  pin multiplexing for PA13/PA14, so the D+/D- pins cannot be read as GPIO in a defined way.
- Result is one-sided: fast blink proves the MCU is on the bus; slow blink means either a switch IC or that
  USBD does not update FN without the pull-up. The HardFault report prints nothing with this image.
- Emulator (`kit/test_usb_probe.py`): write order and restore checked, LED pattern for a faked frame counter,
  108 DSP/pin events after the probe identical to the image without it. The emulator has no USB model.
- Packaged 2026-11-22 as `patched/D3V Updater (USB Probe).app` (copy of the No Tweeter Gate app with the firmware
  resource replaced, ad-hoc re-signed, `codesign --verify` passes; arm64 code identical to the app that flashed
  successfully). Raw image also at `patched/D3V_MCU+DSP_V1_7_RC4_usb_probe.bin`. The No Tweeter Gate app is
  untouched (firmware sha256 `59f60c30…`) and is the rollback. Flashing is the user's step; result not yet known.
- RESULT 2026-11-22: user flashed the USB Probe app (kernel log: `WPM USB` 18:50:00..18:50:11 on hub port
  02123000, then `08bb/2704` enumerated at 18:50:11.382 and stayed enumerated through the 10 s probe window) and
  reported SLOW blink = frame number did not advance. So the equal-size image with new code flashes and boots,
  the listen-only PHY did not disturb the PCM2704, and the MCU did not hear SOFs. Leaving update mode again showed
  no disconnect (transaction errors, `reset API call`, audio device back 9 ms later). Together with that log
  pattern the working conclusion is: USB switch IC, MCU off the bus in normal operation, no firmware route to
  detect bus suspend. Residual doubt: USBD might not update FN without the D+ pull-up. Probe image is temporary:
  flash `patched/D3V Updater (No Tweeter Gate).app` back.
