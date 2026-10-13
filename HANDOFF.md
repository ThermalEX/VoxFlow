# VoxFlow 交接说明

更新日期：2026-10-13。当前分支为 `main`，远端为 `https://github.com/ThermalEX/VoxFlow.git`。本文件面向接手开发的 agent；面向使用者的说明见 [README.md](README.md)。先以仓库当前代码和测试结果为准，历史讨论中的构想不等于已实现功能。

## 1. 项目现状

VoxFlow 是 Windows 上的本地语音输入原型，目前完成 **ASR → 预览/编辑 → 确认粘贴** 的闭环。托盘常驻；`Ctrl+Shift+Space`、胶囊或麦克风按钮控制录音。录音时底部透明浮层显示实时草稿、蓝色柔光与随声音变化的粒子；停录后展示最终文字，用户可编辑并确认输入到先前应用。预览高度随文字行数增长，最多占当前屏幕可用高度的一半，超出部分滚动。设置是独立白色窗口，可从托盘或浮层打开。

当前没有智能改写、翻译、意图识别、云端同步或安装包。识别中英混说的质量尚未建立真实语料基准；不要把未来模型或产品方向写成已完成。

## 2. 在新环境运行

要求 Windows 和 Python 3.12。在 PowerShell 中，从仓库根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe scripts\download_model.py
.\.venv\Scripts\python.exe -m voxflow
```

日常后台启动：`.\.venv\Scripts\pythonw.exe -m voxflow`。无麦克风时可运行 `.\.venv\Scripts\python.exe -m voxflow --file path\to\speech.wav` 验证识别。手动麦克风与窗口集成检查：`.\.venv\Scripts\python.exe scripts\smoke_microphone.py`，运行前确认麦克风可用；脚本录制约两秒，不保存音频。

模型为 `models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/` 下的 SenseVoiceSmall INT8 ONNX，约 240 MB。`models/` 不进 Git，新机器需单独下载。`scripts/download_model.py` 固定来源与 SHA-256；模型许可遵循模型目录和 README 中链接的原始许可。当前机器保留已解压模型及附带的测试音频，以便继续运行真实模型测试。

## 3. 代码入口与数据流

| 位置 | 职责 |
| --- | --- |
| `voxflow/__main__.py` | CLI 参数、托盘、全局入口、窗口初始化；`--file` 用于离线音频识别。 |
| `voxflow/window.py` | 底部浮层、录音状态机、异步识别调度、结果预览、确认粘贴、动画与热键。状态主要是 `idle → recording → finalizing → result`。 |
| `voxflow/audio.py` | 线程安全的单声道录音缓冲区；单次录音上限为 300 秒。 |
| `voxflow/scheduler.py` | 按录音会话管理临时与最终识别任务，避免旧任务覆盖新结果。 |
| `voxflow/recognizer.py` | sherpa-onnx SenseVoice 模型、增量分段缓存与文本拼接；模型本身是离线整段识别，不是原生流式模型。 |
| `voxflow/input_target.py` | 记住之前的 Windows 前台窗口；确认时通过剪贴板和 Win32 `SendInput` 粘贴。 |
| `voxflow/settings_window.py`, `voxflow/appearance.py` | 独立设置窗口、字体/字号/对齐/颜色与持久化。设置由 `QSettings("VoxFlow", "VoxFlow")` 存在用户环境中，不在仓库里。 |
| `voxflow/overlay_widgets.py`, `voxflow/particles.py` | 胶囊波面、操作按钮、粒子运动。 |
| `voxflow/ui_icons.py`, `voxflow/assets/icons/` | 离线打包的 Google Material Symbols SVG；保留同目录 `LICENSE` 和来源说明。 |

`sounddevice` 的回调把音频写入 `AudioBuffer`。主窗口通过 `RecognitionScheduler` 约每 1.2 秒提交一次任务，由单独的 `ProcessPoolExecutor` 加载并运行 ASR；识别器把长录音按约 6–10 秒的安静边界分段，已完成片段缓存，临时结果可能修订。停录后请求最终结果并保留可编辑预览。若最终识别为空但已有临时草稿，`apply_transcript()` 会保留草稿供用户确认。

**智能改写数据集（尚未训练、未接入软件）**：`training/rewrite/` 存放口语改写模型的数据集，设计见 `docs/superpowers/specs/2026-10-13-rewrite-dataset-design.md`。两个任务共用 `prompts.py` 里的系统提示：任务 1 清理并执行语音内联指令（口气词、改口与回头编辑、口述格式、翻译、语气改写），任务 2 生成 0–3 条自由改写建议。手写种子在 `seeds/*.jsonl`（约 830 条清理、约 400 条建议），`.\.venv\Scripts\python.exe -m training.rewrite.build_dataset` 校验种子、注入口语噪声并按种子哈希划分，输出到已忽略的 `training/rewrite/build/{train,valid,test}.jsonl`（chat messages 格式），同时打印覆盖报告。用户要求训练阶段使用 4B 及以上的模型；本机 6 GB 显存微调上限约 4B，更大模型需云端训练。

## 4. 验证与操作边界

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

2026-10-13 在当前 Windows 环境运行结果：**49 passed**，包含已下载模型的识别与后台进程测试。清理后还用模型自带的 `test_wavs/en.wav` 执行了 `python -m voxflow --file`，成功输出英文识别文本。测试会验证状态流、浮层、半屏预览、声音驱动胶囊、设置、输入回退和识别分段。自动化测试不能代替真实麦克风、热键、不同 DPI/多屏幕、其他应用输入框的人工验证；本次交接未重做这些人工检查。

使用者应先聚焦目标输入框再唤起浮层。若 Windows 阻止切回目标窗口，`_confirm_text()` 会把文字复制到剪贴板并保留浮层，供手动粘贴。默认不把录音写入磁盘；不要在新功能中无意改变这一点。

## 5. 仓库清理与保留项

已清理根目录下忽略的 `.cache/` 历史截图和临时脚本、`.pytest_cache/`、Python `__pycache__/`、`voxflow.egg-info/`，以及 `models/sensevoice-int8-2024-07-17.tar.bz2` 历史压缩包。该压缩包的 SHA-256 与下载脚本固定值一致，但运行只读取已解压目录，下载脚本也不按该历史文件名查找它；需要时可重新下载。

保留 `.venv/` 以便当前机器直接运行，保留已解压模型目录、许可证和 `test_wavs/`，因为真实模型测试使用这些音频。上述本地依赖均被 `.gitignore` 排除，新克隆不会自带。

## 6. 接手时的建议顺序

1. 先读本文件、`README.md` 和相关模块；执行完整测试，并在可用设备上做一次真实录音到确认粘贴的人工检查。
2. 若修改识别，维持进程外推理、会话隔离和最终结果保留机制；用中英混说的真实录音评估准确率、延迟和内存后再决定是否更换模型。
3. 若推进“智能输入”，先和用户确认下一阶段的具体交互与隐私边界，再在现有 ASR/预览闭环上扩展。不要把先前讨论中的候选方向当成固定需求。
