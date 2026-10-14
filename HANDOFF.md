# VoxFlow 交接说明

更新日期：2026-10-14。主分支为 `main`（开发分支 `feature/rewrite-dataset` 尚未合并），远端为 `https://github.com/ThermalEX/VoxFlow.git`。本文件面向接手开发的 agent；面向使用者的说明见 [README.md](README.md)；改写模型的实验结果、问题与结论汇总在 [docs/research-log.md](docs/research-log.md)（写论文用，每次训练/评估后追加）。先以仓库当前代码和测试结果为准，历史讨论中的构想不等于已实现功能。

## 1. 项目现状

VoxFlow 是 Windows 上的本地语音输入原型，目前完成 **ASR → 预览/编辑 → 确认粘贴** 的闭环。托盘常驻；`Ctrl+Shift+Space`（可在设置 › 快捷键中更换）、胶囊或麦克风按钮控制录音，`Ctrl+Alt+Shift+Space` 或“继续说”按钮接着已有文字继续口述。录音时底部透明浮层显示实时草稿、蓝色柔光与随声音变化的粒子；停录后展示最终文字，用户可编辑并确认输入到先前应用。预览高度随文字行数增长，最多占当前屏幕可用高度的一半，超出部分滚动。设置是独立白色窗口，可从托盘或浮层打开。

已有智能编辑（本地微调模型整理口语、执行语音指令、给出改写建议，默认开启）、中英双语界面、可自定义的全局快捷键与“继续说”。尚无意图识别、云端同步。识别中英混说的质量尚未建立真实语料基准；不要把未来模型或产品方向写成已完成。

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
| `voxflow/smart_editing.py` | 智能编辑控制：最终文字提交改写、修改动画、撤回/悬停预览、建议按钮、过期结果丢弃、本地服务启停。 |
| `voxflow/rewriter.py`, `voxflow/rewrite_prompts.py` | OpenAI 兼容接口客户端与 `rewrite/*` 设置；两个任务的系统提示（训练与服务共用）。 |
| `voxflow/local_server.py` | 无窗口启动 `runtime/llama.cpp/llama-server.exe` 加载 GGUF 模型；用 Windows 作业对象保证 VoxFlow 退出或崩溃时服务一并结束。 |
| `training/rewrite/export_gguf.py`, `training/rewrite/serve.py` | 在 WSL 训练环境中合并 LoRA 并转 GGUF（Q8/bf16，Q4 用 `llama-quantize.exe`）；`serve.py` 是 WSL 下的备用 Python 服务，软件不再使用。 |
| `voxflow/edit_diff.py` | 原文与改写结果的按字/按词差异及动画帧 HTML。 |

`sounddevice` 的回调把音频写入 `AudioBuffer`。主窗口通过 `RecognitionScheduler` 约每 1.2 秒提交一次任务，由单独的 `ProcessPoolExecutor` 加载并运行 ASR；识别器把长录音按约 6–10 秒的安静边界分段，已完成片段缓存，临时结果可能修订。停录后请求最终结果并保留可编辑预览。若最终识别为空但已有临时草稿，`apply_transcript()` 会保留草稿供用户确认。

**智能改写数据集（尚未训练、未接入软件）**：`training/rewrite/` 存放口语改写模型的数据集，设计见 `docs/superpowers/specs/2026-10-13-rewrite-dataset-design.md`。两个任务共用 `prompts.py` 里的系统提示：任务 1 清理并执行语音内联指令（口气词、改口与回头编辑、口述格式、翻译、语气改写），任务 2 生成 0–3 条自由改写建议。手写种子在 `seeds/*.jsonl`（约 830 条清理、约 400 条建议），`.\.venv\Scripts\python.exe -m training.rewrite.build_dataset` 校验种子、注入口语噪声并按种子哈希划分，输出到已忽略的 `training/rewrite/build/{train,valid,test}.jsonl`（chat messages 格式），同时打印覆盖报告。模型候选：智能编辑 Qwen3.5 2B / 4B，语音识别 Qwen3-ASR 0.6B / 1.7B（替换 SenseVoice 前先用真实录音评估）。本机 6 GB 显存微调上限约 4B。

**首次训练结果（2026-10-13，Qwen3.5-2B，bf16 LoRA，2 轮，RTX 3060 6 GB 上约 32 分钟，峰值显存 4.4 GB）**：训练在 WSL 环境 `~/voxflow-train`（`bash training/rewrite/setup_wsl.sh` 创建）中用 `python -m training.rewrite.train` 运行，`python -m training.rewrite.evaluate` 评估；适配器与报告在已忽略的 `training/rewrite/runs/`。测试集（88 条清理、44 条建议）上微调前→后：清理完全一致率 21.6%→54.5%，字符错误率 0.74→0.21，指令残留 31.9%→0%，反例保留 81%→87.5%（目标 95% 未达），翻译 chrF 39.5→60.2，建议条数与参考一致 18%→82%、规则合规 93%→100%，短句延迟中位数 1.14 s（HF generate，未量化）。已知错误：时间推算（“两点到三点半”→“14:00到13:30”）、个别带理由修正、混说里的中文词被翻译、“然后”被当作口气词删除。风格改写与翻译的完全一致率不代表质量，需人工评审。

**智能编辑数据流**：`apply_transcript("final")` 调用 `SmartEditor.begin()`；启用且接口就绪时，单线程 `ThreadPoolExecutor` 调用 `RewriteClient.clean()`，由 `_poll` → `SmartEditor.poll()` 收取。只有会话号一致、仍在结果模式且用户未编辑时才应用：播放约 0.8 s 修改动画后显示整理结果，再请求 `suggest()` 显示建议。本地模型服务就绪前（llama-server 约 4 s）结果会排队等待；服务异常退出时状态栏提示并保留原文。2026-10-13 改为原生 llama-server 后端到端（注入文字、未用麦克风）：清理 0.23–0.25 s，建议约 2.4 s 后出现（含 1.2 s 延迟）。测试集上 GGUF Q8 与原 PyTorch 版质量一致（完全一致率 54.5%、字符错误率 0.21），短句延迟 0.14 s；Q4_K_M 略降（53.4%、0.24）。已知问题：模型偶有补充原文没有的理由。（原默认字体 Segoe UI 无中文字形会回退为宋体，2026-10-14 默认改为“微软雅黑 UI”。）

**第二版（2026-10-14，v2）**：种子加入 1269 条中含约 40 条姓名样本（中文全名英译为“名 姓”，如王书涵 → Shuhan Wang；小李 → Xiao Li、王总 → Mr. Wang），同样设置重训，验证损失 0.2234→0.2027。旧版归档在 `training/rewrite/runs/archive/qwen3.5-2b-v1/`（设置下拉中显示为“旧版”）。新测试集（93 条清理、45 条建议）上 GGUF Q8 v1→v2：完全一致率 51.6%→51.6%，字符错误率 0.230→0.222，反例保留 87.5%→87.5%，新增数字 3.2%→2.2%，翻译 chrF 59.3→60.8，延迟 0.14 s 不变。姓名抽查 6 条翻译中 v1 有 3 条为“姓 名”顺序，v2 顺序全对，但“张晓雨”拼成 Zhaoyu Zhang（拼音错误）。训练时显存只差一点就满，同时开模拟器等占显存程序会导致 OOM，可用 `--resume` 从检查点续训。

**第三版（2026-10-14，v3，当前默认）**：再加 52 条姓名种子（晓/欣/睿/梓等常见名字用字，曾/单/解/查/乐/翟/仇/区等多音字姓，司马/诸葛/上官复姓，Jia'an 这类隔音符号），种子 1321 条，验证损失 0.2027→0.1975。v2 归档在 `runs/archive/qwen3.5-2b-v2/`。用 12 个训练中未出现的名字抽查：v2 拼对 5 个，v3 拼对 9 个（错例：贾欣然→Xinyan、欧阳睿→Ruoyu、余皓轩→Haokuan）。新测试集（96 条清理、46 条建议）v2→v3：完全一致率 50.0%→52.1%，字符错误率 0.220→0.244，反例保留 87.5% 不变，新增数字 2.1%→3.1%，建议规则合规 97.8%→100%，翻译 chrF 62.6→62.9。逐条看两版各有 16 条明显更好/更差，v3 退步集中在隐含理由改口（“外婆说她来我们家，那就在我们家吃”未改写）和“第一句太冲了，删了”这类删除指令；这两类是下一轮数据要补的方向。

**界面语言与默认开启（2026-10-13）**：`voxflow/i18n.py` 维护中英文字符串表，`tr(key)` 取当前语言；设置项 `ui/language`（system/en/zh，默认跟随系统），切换后设置窗口、浮层状态、按钮和托盘菜单即时更新（浮层状态按 key 保存，`VoxFlowWindow.show_status`）。智能编辑默认开启并随应用启动本地模型；旧版本保存的“关闭”会被 `rewriter.migrate_settings` 一次性改为开启。设置页显示本地模型状态（启动中/已就绪/缺少文件/已停止），连接测试与错误提示按类型本地化。测试固定英文界面（`VOXFLOW_LANG=en`）且默认不开启智能编辑，避免启动真实 llama-server。

**设置窗口（2026-10-13 重做）**：参照 ChatGPT 设置的布局——左侧导航（常规/外观/智能编辑），右侧页面由“小节标题 + 圆角卡片 + 行（左标题说明、右控件）”组成；组件在 `voxflow/settings_widgets.py`（`ToggleSwitch`、`SettingRow`、`SettingsCard`、带勾选标记与圆角弹出列表的下拉框），配色在 `voxflow/settings_theme.py`，跟随 Windows 深浅色并随系统切换实时更新（测试可用 `VOXFLOW_THEME` 覆盖）。本地模型用下拉列表选择，由 `voxflow/model_catalog.py` 扫描 `training/rewrite/runs/*/gguf/*.gguf` 与 `runtime/models/*.gguf`，Q8 排第一并标“推荐”，末项“浏览…”；自定义接口的模型名可点“刷新”从 `/models` 拉取。

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
