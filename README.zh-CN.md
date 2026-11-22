# ADAM Audio D3V 高音断音修复

[English](README.md) | **简体中文**

ADAM Audio D3V 1.7 固件的非官方补丁：去掉小音量下把高音压静音的噪声门，并附上逆向与构建工具。

- **只改 21 个字节**（DSP 增益表），不动主控代码，镜像大小与原厂 1.7 完全一致。
- **保护完整**：高音限幅、低音压缩与限幅、过温保护与原厂逐字节一致。
- **随时可还原**：用 ADAM 官方 1.7 升级程序再刷一次即可恢复原厂。

> [!WARNING]
> 本项目与 ADAM Audio、Focusrite 无关。刷入修改固件风险自负，可能影响保修。目前仅在**一对**音箱上通过 macOS 实刷，效果**凭听感**确认。

## 为什么会断音

即使升级到官方 1.7 固件，小音量时高音依然容易发闷或断断续续，而低音不受影响。

原厂为了压掉空闲时的底噪，在 DSP（ADAU1701）里给高音加了一条自动衰减规则（噪声门）：只要高频信号弱于约 `-75 dBFS`，就会被当成底噪再压低 17～31 dB（响度瞬间只剩原来的约 1/3 甚至不到 1/8）。

问题在于，这条规则检测的是**经过音量控制之后的信号**——一旦你把音量调小，正常音乐里的轻柔高音也会掉到这个阈值以下，被误当成底噪压掉，听起来就是高音突然发闷或断断续续：

| 高音频段电平 | 原厂 1.7 增益 | 本修改 |
|---|---|---|
| -90 dBFS | -23.0 dB | 0 dB |
| -87 dBFS | -26.0 dB | 0 dB |
| -84 dBFS | -28.9 dB | 0 dB |
| -81 dBFS | -31.0 dB | 0 dB |
| -78 dBFS | -17.0 dB | 0 dB |
| -75 dBFS | -0.4 dB | 0 dB |
| -72 dBFS | < -0.01 dB | 0 dB |
| -69 … -15 dBFS | 0 dB | 不变 |
| -12 … +6 dBFS（限幅） | -0.1 … -13.5 dB | 不变 |

本补丁把这七个 4 字节参数（`p137`..`p143`，共 28 字节；最高字节原厂本就是 `0x00`，实际改 21 字节）设为 `1.0`（`0x00800000`），去掉这段衰减；`-12 … +6 dBFS` 高音过载限幅器保持不变。改动见 [`mods/no-tweeter-gate.params`](mods/no-tweeter-gate.params)。

## 下载

前往 [最新 Release](https://github.com/skywalker512/adam-d3v-tweeter-fix/releases/latest) 下载。大多数用户只需下载对应系统的 `.zip`——里面已内置补丁固件。

| 文件 | 用途 |
|---|---|
| `D3V-Updater-No-Tweeter-Gate-macOS.zip` | **macOS**（Intel / Apple 芯片）预打补丁刷机 App |
| `D3V-Updater-No-Tweeter-Gate-Windows.zip` | **Windows 10/11 x64** 预打补丁免安装刷机包 |
| `d3v_patch.py` | 可选：本地从 ADAM 官方包自行生成刷机包 |
| `D3V_MCU+DSP_V1_7_RC4_no_tweeter_gate.bin` | 可选：补丁后的裸固件镜像 |
| `SHA256SUMS.txt` | 可选：SHA-256 校验值 |

## 刷机步骤

1. 拔掉 D3V 电源线，用 USB-C **直连电脑**（不要经过 Hub）。
2. 打开对应系统的补丁版 Updater。
3. **按住音量旋钮不放**，插回电源，等指示灯**紫色呼吸**后松手。
4. 按界面提示刷写，勿断电或拔线（约 10～15 秒）。结束后绿灯闪三次并自动重启。

- **macOS**：解压得 `D3V Updater (No Tweeter Gate).app`。因是临时签名，首次打开请到 **系统设置 → 隐私与安全性 → 仍要打开**，或执行：
  `xattr -dr com.apple.quarantine "D3V Updater (No Tweeter Gate).app"`
- **Windows**：先完整解压整个 `.zip`，再运行 `D3V Updater.exe`（别在压缩包预览里直接双击）。SmartScreen 可能提示未知发布者；若窗口空白，请安装微软 WebView2 运行时（Win11 自带）。

## 恢复原厂

用 [ADAM Audio 官方 Updater](https://www.adam-audio.com/en/news/industry/d3v-firmware-updater/) 按同样紫灯步骤再刷一次即可还原 1.7。若刷机中断或无法启动，重复紫灯步骤重刷即可（升级模式位于独立 Bootloader，刷机不会覆盖；该结论由固件镜像推得，未读出 Bootloader 本身）。

## 副作用

- **贴耳底噪略增**：去掉噪声门后，安静环境下贴近高音单元可能听到轻微沙沙声。
- **自动待机与音箱保护功能不受影响**：按固件分析，这些功能不会用到被改动的小音量参数（未做仪器实测）。

## 验证情况

| 项目 | 状态 |
|---|---|
| 工具链从源码逐字节重建原厂 1.7 | 每次推送由 CI 验证 |
| 补丁镜像与原厂仅差 21 字节 | 由 CI 验证 |
| macOS（Apple 芯片）实刷与效果 | 作者一对音箱实刷通过，听感确认断音消失 |
| Windows 刷机包 | 已内置同一份补丁固件，CI 已验证可启动，**尚未实机刷过** |
| 长期稳定性 | 未知（仅一对，2026 年 11 月首次刷入） |

---

## 开发者与自行构建

### 本地自行生成 Updater

仓库里的 [`patcher/d3v_patch.py`](patcher/d3v_patch.py)（Release 也附独立版 `d3v_patch.py`）只需 Python 3.8+ 即可本地构建：

```bash
python3 patcher/d3v_patch.py  # macOS -> out/D3V Updater (No Tweeter Gate).app
py patcher\d3v_patch.py       # Windows -> out\D3V Updater (No Tweeter Gate)\
```
*（从 Release 单独下载的 `d3v_patch.py` 去掉 `patcher/` 即可。）*

脚本会下载 ADAM 官方 Updater 1.0.0（内置原厂 1.7 固件），校验 SHA-256，修改 21 字节并校验结果（`59f60c30…e98fef`），再打包副本，不与音箱通信。可用 `--official 文件` 指定本地官方包。

### 从源码重建固件

[`kit/`](kit) 可将原厂镜像反汇编为可重定位 ARMv6-M 汇编、重新构建并做板级仿真测试（需 Python 3 与 LLVM）：

```bash
python3 kit/fetch.py                             # 提取原厂镜像（校验 SHA-256）
python3 kit/split.py                             # 镜像 -> build/app.S
python3 kit/build.py                             # 须与原厂 1.7 RC4 逐字节一致
python3 kit/test_reloc.py                        # 重定位校验
python3 kit/test_emu.py                          # 仿真器测试
python3 kit/build.py --params no-tweeter-gate    # -> build/no-tweeter-gate.bin
python3 kit/dsp.py list                          # 导出 DSP 参数
```

[`mods/`](mods) 中的其他实验补丁（未进 Release，不建议刷入）：

| 修改 | 状态 |
|---|---|
| `fix-usb-resume-mute` | 静音时重插 USB 保持静音（仅仿真器） |
| `usb-guard` + `delay_ms.c` | USB 5 V 断开时硬静音（仅仿真器，已搁置） |
| `usb-probe` + `_printf_core.c` | 诊断 MCU 能否监听 USB（实刷一次：不能） |

详细记录见 [`AGENTS.md`](AGENTS.md)。

### 另一个发现：USB 休眠 / KVM 切换爆音

电脑休眠或 KVM/Hub 切换主机时的爆音，纯 MCU 固件无法解决：

- USB DAC（TI PCM2704C）在总线空闲挂起时会关断输出，TI 文档已说明该系列的挂起爆音特性。
- MCU 只检测 USB 5 V，休眠或独立供电 Hub 切换时 5 V 不断，且探测固件确认 MCU 平时看不到 USB 数据线。
- **规避方法**：切换前单击旋钮静音，或改用 TRS 模拟输入。

## 法律声明

工具、补丁与文档采用 [MIT 许可证](LICENSE)。仓库不含 ADAM Audio 二进制文件，脚本从其官网下载。Release 包内含 ADAM Audio 升级程序与修改后的固件副本，权利归 ADAM Audio GmbH 所有。“ADAM Audio”与“D3V”为其各自商标；权利人如需移除请提 issue。
