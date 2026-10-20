# VoxFlow · 本地语音识别原型

开发交接与代码结构见 [HANDOFF.md](HANDOFF.md)。

VoxFlow 是 Windows 上的本地语音输入工具：按一下快捷键说话，识别出的文字经本地小模型整理（去掉口气词、按改口修改、执行“翻译成英文”“正式一点”等语音指令）后，输入到你正在用的应用里。语音识别和智能编辑都在本机运行，默认不保存录音。界面支持中文和英文，识别结果保留原语种。

## 安装与首次使用

运行安装程序 `VoxFlow-Setup-<版本>.exe`（只含程序本体，装在当前用户目录，不需要管理员权限）。第一次打开会出现新手教程：

1. 选择界面语言。
2. 选择颜色模式（跟随系统 / 浅色 / 深色）和配色主题，右侧实时预览语音浮层。
3. 选择麦克风，对着说话可看到音量条跳动（只在本机计算音量，不录音）。
4. 下载组件：语音识别模型（必需，约 230 MB）、llama.cpp（运行智能编辑）和智能编辑模型。默认勾选推荐项，点“下载所选”才开始；也可以跳过，之后在 设置 › 智能编辑 中下载。
5. 动手试一次。
6. 小技巧。

教程可在 设置 › 关于 › 重新开始教程 再次打开。

**下载**：可下载的内容来自 [Hugging Face](https://huggingface.co/ThermalEX/voxflow-rewrite)，下载源可选“自动 / Hugging Face / 国内镜像（hf-mirror.com）”；“自动”在连不上或太慢时切换到镜像。下载支持断点续传，校验 SHA-256 后才安装，存放在 `%LOCALAPPDATA%\VoxFlow`，重装软件不用重新下载；卸载时会询问是否一并删除。llama.cpp 有两个版本可选：

- **通用版（Vulkan）**：30 MB，NVIDIA / AMD / Intel 显卡都能用，第一次启动约 8 秒，之后与加速版一样快（推荐）。
- **NVIDIA 加速版（CUDA）**：625 MB，仅 NVIDIA 显卡，实测速度与通用版相同。

## 使用

先聚焦目标应用的输入框，按 `Ctrl+Shift+Space` 开始录音，再按一次停止；中央胶囊和右侧麦克风按钮也可操作录音。停录后浮层展示最终文字，可直接编辑；按回车或左侧确认键，程序会回到之前的应用并粘贴文字（编辑时用 `Shift+Enter` 换行）。若目标窗口无法重新获得焦点，浮层会保留结果并复制文字，供手动粘贴。按 `Esc` 或右侧关闭按钮隐藏浮层并丢弃本次内容。结果出来后可点“继续说”或按 `Ctrl+Alt+Shift+Space` 接着已有文字继续口述，新内容会和原文一起再整理一次。单次录音上限 5 分钟。

设置窗口可从托盘或浮层左侧的设置图标打开：

- **常规**：界面语言、麦克风、文字对齐。
- **外观**：颜色模式、配色主题（6 个预设 + 自定义，统一浮层柔光和设置界面的颜色）、文字字体和字号。
- **智能编辑**：开关、模型来源、已安装的模型、下载模型。
- **记忆**：开关、记忆表（搜索、添加、编辑、删除，每条可在“7 天”和“永久”之间转移）、按日期查看保存的原文并手动生成每日总结、清空全部。
- **快捷键**：录音和“继续说”两个全局快捷键可录制更换；被其他程序占用时会提示并保留原来的键。
- **关于**：版本、GitHub 与 Hugging Face 链接、重新开始教程。

## 智能编辑

默认开启。打开 VoxFlow 时会在后台启动本地模型（约 4 秒就绪），停录得到的最终文字交给改写模型整理，以一次修改动画替换原文；鼠标悬停“撤回修改”可预览原文，点击撤回或恢复；下方还会浮动 0–3 个改写建议，点击即采用。模型出错、超时或未就绪时保留原文，不影响正常使用。实时草稿不做改写。

- **VoxFlow 本地模型**：VoxFlow 直接启动 llama.cpp 的 `llama-server.exe` 加载 GGUF 模型（运行时不需要 WSL）。缺少 llama.cpp 或模型时，状态会显示“未安装”，点“去下载”跳到下载列表。也可以选择本机已有的 GGUF 文件。
- **自定义 OpenAI 兼容接口**：填写地址、模型名和可选 API Key，可接 LM Studio、Ollama、llama.cpp server 或云端服务。API Key 以明文保存在本机设置中。

## 记忆

默认关闭，可在新手教程或 设置 › 记忆 中开启。开启后：

- **记住口令**：句首说“记住……”“帮我记一下……”（英文 “remember that …”），浮层去掉口令词，并按配色主题的强调色把这段文字高亮一次；确认后照常粘贴，同时把内容永久记入记忆表。
- **自动提取**：确认发送的文字保存在本机 7 天；浮层关闭、模型空闲时，后台从中找出人名、专有名词、有时间的安排和长期有用的事实，记入记忆表（保留 7 天；来自“记住”口令的永久保留）。安排里说的“周三”“下周一”“11月3日”等由程序按规则换算成具体日期，不交给模型推算。
- **纠正人名和专有名词**：按读音把识别错的同音字改成记住的写法（如记住“张三”后，识别成“张叁”会改回“张三”）；两个字的名字要求第一个字相同，避免把“黎明”这类普通词改成人名。改动包含在修改动画里，可用“撤回修改”还原。
- **按记忆补全**：文字提到已记住的事、却漏了时间地点等细节时，建议栏第一个按钮是“按记忆补全”，点了才生效。
- **每日总结**：在 设置 › 记忆 中选择日期，点“生成总结”，按日程、待办、提到的人和事分点列出。

数据保存在 `%LOCALAPPDATA%\VoxFlow\memory\memory.db`（源码运行时在仓库的 `memory/`，已忽略）。关闭记忆不会删除已有内容，“清空”才会删除。智能编辑使用在线模型时，提取、补全和总结会把文字和记忆发送到所配置的接口，设置页会醒目提示。

## 从源码运行

需要 Windows 和 Python 3.12：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m voxflow
```

从源码运行时，模型和 llama.cpp 都放在仓库目录（`models/`、`runtime/llama.cpp/`、`runtime/models/`），可以在软件里下载，也可以用 `scripts/download_model.py` 下载语音模型。日常使用可运行 `.\.venv\Scripts\pythonw.exe -m voxflow`，不会弹出终端窗口。用音频文件验证识别：`.\.venv\Scripts\python.exe -m voxflow --file path\to\speech.wav`。测试：`.\.venv\Scripts\python.exe -m pytest -q`。

## 打包安装程序

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
winget install JRSoftware.InnoSetup --scope user      # 只需一次
.\.venv\Scripts\python.exe packaging\build.py         # --skip-installer 只生成便携文件夹
```

输出 `dist\VoxFlow\`（便携版）和 `dist\VoxFlow-Setup-<版本>.exe`。安装程序只含程序本体，可选桌面图标和开机启动；安装或卸载前会自动结束正在运行的 VoxFlow。第三方许可见安装目录的 `THIRD_PARTY.txt`。

发布新的 llama.cpp 版本或更新下载清单：`.\.venv\Scripts\python.exe packaging\publish_runtime.py`（需要 `gh` 和 `hf auth login`），它把 llama.cpp 的 Windows 版本转存到 Hugging Face 仓库的 `runtime/`，并更新 `catalog.json` 与内置清单 `voxflow/assets/catalog.json`。上传新的改写模型后，在清单里加一项即可让已安装的软件看到它。

## 当前模型

使用 [SenseVoiceSmall](https://github.com/QwenAudio/SenseVoice) 的 [sherpa-onnx INT8 转换版本](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models)，本地 CPU 推理；模型约 240 MB，首次单独下载，文件不会进入 Git。该模型是离线整段识别；窗口将长录音按约 6–10 秒的安静处分段，缓存已完成片段，只反复识别当前片段来更新临时草稿，并非模型原生流式输出。中英混说质量尚需真实语料评测。模型权重遵循其[模型卡中的许可条款](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)。

智能编辑与记忆使用 VoxFlow 改写模型 v6（基于 Qwen3.5-2B 微调，[Hugging Face](https://huggingface.co/ThermalEX/voxflow-rewrite)），下载列表默认推荐 v6 Q8，v4 仍可下载。下载完成后会自动切换到新模型；设置里的模型列表按“名称 版本 · 量化 · 大小”显示，最新版本排在最前并标“推荐”。

## 已知边界

- 需要可用麦克风及录音权限；模型文件下载完成后识别可离线运行。
- 临时草稿会随录音变化；最终文本以停录后的完整识别结果为准。
- 自动输入依赖 Windows 允许程序切回之前的窗口，并使用系统剪贴板粘贴；某些受保护的输入框或权限更高的应用可能拒绝接收。
- 为减少安静环境下的短词误报，整体音量极低的录音会被判为空；麦克风增益过低时可能漏识别。
- `sherpa-onnx` 的 CPU 模型目前未使用 RTX 3060。后续可在相同接口下比较 Qwen3-ASR 等候选。
