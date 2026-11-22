# ADAM Audio D3V 高音断音修复

[English](README.md) | **简体中文**

这是 ADAM Audio D3V 固件 1.7 的非官方修改版：去掉了小音量下让高音单元静音的那道门限，并附上找出这个问题所用的逆向工具。

> [!WARNING]
> 本项目与 ADAM Audio、Focusrite 无关，也未获其认可。刷入修改固件的风险由你自己承担，并可能使保修失效。修改固件只在**一对**音箱上刷过，效果**只凭听感**判断。

## 问题

小音量下，音乐的安静段落里 D3V 的高音会逐渐消失或突然断掉，低音单元照常出声。ADAM 的 1.7 固件更新日志里写了"改善了极低信号电平下的高音表现"。

但 1.7 的镜像里原因仍然在。DSP（ADAU1701）在高音通路上、音量控制之后，有一张随电平变化的增益表，最低的七个点构成一个向下扩展器（噪声门）：

| 高音频段电平 | 原厂 1.7 增益 | 本修改 |
|---|---|---|
| -90 dBFS | -23.0 dB | 0 dB |
| -87 dBFS | -26.0 dB | 0 dB |
| -84 dBFS | -28.9 dB | 0 dB |
| -81 dBFS | -31.0 dB | 0 dB |
| -78 dBFS | -17.0 dB | 0 dB |
| -75 dBFS | -0.4 dB | 0 dB |
| -72 dBFS | -0.0 dB | 0 dB |
| -69 … -15 dBFS | 0 dB | 不变 |
| -12 … +6 dBFS（限幅） | -0.1 … -13.5 dB | 不变 |

也就是说，经过音量控制之后的高频内容一旦低于约 -75 dBFS，高音单元会被再压低 17 到 31 dB。

## 改了什么

把七个参数字（`p137`..`p143`）设为 1.0。22124 字节的镜像里有 21 个字节不同，大小不变，不改任何代码。高音限幅、低音压缩与限幅、过温保护与原厂逐字节相同。

全部改动就是 [`mods/no-tweeter-gate.params`](mods/no-tweeter-gate.params) 这一个文件。

## 哪些验证过，哪些没有

| | 状态 |
|---|---|
| 工具链能从生成的源码逐字节重建原厂镜像 | 每次推送由 CI 检查 |
| 修改镜像与原厂只差这 21 个字节 | 由 CI 检查 |
| 在 macOS（Apple 芯片）上用补丁版 Updater 刷机 | 在作者的 D3V 上做过一次，过程正常 |
| 高音断音消失 | 作者的听感，没有测量数据 |
| Windows 包 | 固件相同，程序是 ADAM 未改动的 Windows 版。CI 检查过它能启动。**从未用它刷过真机** |
| 长期表现 | 未知。只有一台，2026 年 11 月首次刷入 |

## 下载

到 [最新 Release](https://github.com/skywalker512/adam-d3v-tweeter-fix/releases/latest) 下载。

| 文件 | 用途 |
|---|---|
| `D3V-Updater-No-Tweeter-Gate-macOS.zip` | macOS 版 Updater（Intel 和 Apple 芯片） |
| `D3V-Updater-No-Tweeter-Gate-Windows.zip` | Windows 10/11 x64 版 Updater，免安装 |
| `d3v_patch.py` | 在你自己的电脑上，用 ADAM 官方下载包生成同样的 Updater |

现成的 Updater 就是 ADAM 的升级程序，里面的固件文件换成了修改版。

## 刷机步骤

1. 拔掉 D3V 的电源适配器。用 USB-C 线把音箱直接连到电脑，不要经过 Hub。
2. 打开 Updater（见下面对应系统的说明）。
3. 按住音量旋钮不放，插回电源，等指示灯变成紫色呼吸后松手。
4. 按 Updater 里的提示操作，过程中不要拔线或断电。结束时指示灯绿色闪三次，音箱自动重启。

**macOS。** 改了固件文件后 ADAM 的签名就失效了，所以这个 app 用的是临时（ad-hoc）签名。首次打开会被系统拦下：到"系统设置 → 隐私与安全性"里点"仍要打开"，或者执行 `xattr -dr com.apple.quarantine "D3V Updater (No Tweeter Gate).app"`。用 `d3v_patch.py` 在本机生成的 app 不会被拦。

**Windows。** 解压整个文件夹，运行里面的 `D3V Updater.exe`，`resources` 文件夹必须留在它旁边。SmartScreen 可能提示"未知发布者"（ADAM 只给安装包签了名，没有给这个程序签名）。程序需要 Microsoft Edge WebView2 运行时，Windows 11 自带；如果窗口一片空白，请从微软官网安装该运行时。

## 恢复原厂

用 [ADAM Audio 官方 Updater](https://www.adam-audio.com/en/news/industry/d3v-firmware-updater/) 按同样的步骤再刷一次，得到的就是原厂 1.7 固件。

如果刷机失败或刷完不启动，重复上面的步骤即可。升级模式（紫灯）由独立的引导程序提供，刷机不会覆盖它。这一点是从固件镜像分析得出的，引导程序本身没有读出来看过。

## 副作用

- 这道门原本也盖住了底噪。修改后，耳朵贴近高音单元时可能听到来自音源或 USB DAC 的轻微沙沙声。
- 预计没有其他变化。自动待机和各项保护不使用被改动的表项。这一点没有在真机上测量过。

## 自己生成 Updater

不想运行现成的包，可以用 `d3v_patch.py` 在本机完成同样的事。只需要 Python 3.8 或更新版本，没有其他依赖。

```
python3 d3v_patch.py          # macOS：生成 out/D3V Updater (No Tweeter Gate).app
py d3v_patch.py               # Windows：生成 out\D3V Updater (No Tweeter Gate)\
```

它会下载 ADAM 官方 Updater 1.0.0，校验 SHA-256，修改那 21 个字节，校验结果的 SHA-256（`59f60c30…e98fef`），再放进 Updater 的副本里。它不会和音箱通信。用 `--official 文件` 可以指定你自己下载的官方包。

## 从源码构建固件

[`kit/`](kit) 里的工具把原厂镜像转成可重定位的汇编源码，重新汇编，并在带板级模型的 ARMv6-M 仿真器里运行。需要 Python 3 和 LLVM（`brew install llvm` 或 `apt install clang llvm`）。

```
python3 kit/fetch.py                             # 从 ADAM 的下载包取出原厂镜像并校验 SHA-256
python3 kit/split.py                             # 镜像 -> build/app.S
python3 kit/build.py                             # 必须输出：IDENTICAL to the factory 1.7 RC4 image
python3 kit/test_reloc.py                        # 重定位检查
python3 kit/test_emu.py                          # 仿真器检查
python3 kit/build.py --params no-tweeter-gate    # -> build/no-tweeter-gate.bin
python3 kit/dsp.py list                          # 以文本列出 DSP 参数
```

[`mods/`](mods) 里还有其他实验，都以针对生成源码的补丁形式保存。它们都不在 Release 里，也不建议刷入：

| 修改 | 状态 |
|---|---|
| `fix-usb-resume-mute` | 静音状态下重新插 USB 时保持静音。只在仿真器里验证过 |
| `usb-guard` + `delay_ms.c` | USB 供电消失时硬件静音。只在仿真器里验证过，已搁置 |
| `usb-probe` + `_printf_core.c` | 诊断用：单片机能否看到 USB 数据？刷过一次，答案是不能 |

[`AGENTS.md`](AGENTS.md) 是实验记录：硬件事实、修改固件的规则、试过的各条路线。

## 另一个发现：USB 爆音

电脑休眠或 KVM/Hub 切换主机时 D3V 会爆音。调查的结论是单片机固件修不了：

- USB DAC 是 TI 的 PCM2704C。总线空闲时它进入挂起并关闭输出，TI 的文档写明了这个系列在挂起时的爆音。
- 从听感测试看，单片机只对"USB 5 V 是否存在"有反应。带电源的 Hub 切换主机或电脑休眠时 5 V 还在，固件不会知道。探测固件表明，正常工作时单片机也看不到 USB 数据线。
- 变通办法：切换前单击旋钮静音，或者改用 D3V 的模拟输入。

## 法律声明

本仓库中的工具、补丁和文档采用 [MIT 许可证](LICENSE)。仓库里不包含 ADAM Audio 的固件或软件，工具会从 ADAM Audio 的服务器下载。Release 里的包含有 ADAM Audio 的升级程序及其固件的修改版，它们的权利归 ADAM Audio GmbH 所有。"ADAM Audio"和"D3V"是其所有者的商标。如果你是权利人并希望移除某些内容，请提 issue。
