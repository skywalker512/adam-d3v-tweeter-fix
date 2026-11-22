Unofficial build of ADAM Audio D3V firmware 1.7 with the tweeter's low-level gate removed
(7 DSP parameter words, 21 bytes, same image size). Not affiliated with ADAM Audio. Use at your own risk.

**Read the [README](https://github.com/skywalker512/adam-d3v-tweeter-fix#readme) before flashing**
([中文说明](https://github.com/skywalker512/adam-d3v-tweeter-fix/blob/main/README.zh-CN.md)).

| File | What it is |
|---|---|
| `D3V-Updater-No-Tweeter-Gate-macOS.zip` | ADAM's updater app with the patched firmware inside, ad-hoc signed. This combination was flashed on a real D3V. |
| `D3V-Updater-No-Tweeter-Gate-Windows.zip` | ADAM's Windows updater program (unmodified) plus the patched firmware, portable folder. **Not tested on a real D3V.** |
| `d3v_patch.py` | Builds either of the above on your own computer from ADAM's official download (Python 3, no other dependencies). |
| `D3V_MCU+DSP_V1_7_RC4_no_tweeter_gate.bin` | The firmware image alone, rebuilt from source by CI. SHA-256 `59f60c30…e98fef`. |
| `SHA256SUMS.txt` | Checksums of all files. |

To go back to the factory firmware, flash with the official updater from
[ADAM Audio](https://www.adam-audio.com/en/news/industry/d3v-firmware-updater/).
