# VoxFlow · 本地语音识别原型

当前阶段实现 Windows 本地麦克风识别。程序常驻系统托盘，唤起后只在屏幕下方显示透明背景上的一排控件。开始录音时，蓝色柔光和粒子从胶囊轮廓向外展开；粒子会随声音活动变化，也会对鼠标靠近作出反应。胶囊待机及录音静音时只有轻微的蓝色波面，录音声音增大时起伏更明显。停录后浮层保持展开，最终文字到达时向上扩展；长内容可滚动查看和编辑。界面默认使用英文，识别结果保留原语种。按确认键会将编辑后的结果粘贴到呼出浮层前使用的应用中，下次录音会覆盖本次结果。暂未实现智能编辑、翻译或建议。

## 运行

需要 Windows 和 Python 3.12。首次安装：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe scripts\download_model.py
.\.venv\Scripts\python.exe -m voxflow
```

日常使用可运行 `.\.venv\Scripts\pythonw.exe -m voxflow`，不会弹出终端窗口。

首次启动后可点击托盘图标打开浮层。左侧设置图标和托盘里的 Settings 可打开设置卡片，选择麦克风及文字左、中、右对齐，选择会保存。先聚焦目标应用的输入框，再按 `Ctrl+Shift+Space` 开始录音；再按一次停止，等待最终文本。中央胶囊和右侧麦克风按钮也可操作录音。检查或编辑结果后按左侧确认键，程序会回到之前的应用并粘贴文字；若目标窗口无法重新获得焦点，浮层会保留结果并复制文字，供手动粘贴。按 `Esc` 或右侧关闭按钮隐藏；从托盘菜单退出程序。如全局快捷键被其他程序占用，仍可通过托盘菜单操作。单次录音上限 5 分钟，默认不保存录音。录音中的长文本会跟随最新内容滚动；长录音按短片段识别，停止后合并结果。

也可用音频文件验证识别：

```powershell
.\.venv\Scripts\python.exe -m voxflow --file path\to\speech.wav
```

测试：`.\.venv\Scripts\python.exe -m pytest -q`。

## 当前模型

使用 [SenseVoiceSmall](https://github.com/QwenAudio/SenseVoice) 的 [sherpa-onnx INT8 转换版本](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models)，本地 CPU 推理；模型约 240 MB，首次单独下载，文件不会进入 Git。该模型是离线整段识别；窗口将长录音按约 20 秒分段，缓存已完成片段，只反复识别当前片段来更新临时草稿，并非模型原生流式输出。中英混说质量尚需真实语料评测。模型权重遵循其[模型卡中的许可条款](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)。

## 已知边界

- 需要可用麦克风及录音权限；模型文件下载完成后识别可离线运行。
- 临时草稿会随录音变化；最终文本以停录后的完整识别结果为准。
- 自动输入依赖 Windows 允许程序切回之前的窗口，并使用系统剪贴板粘贴；某些受保护的输入框或权限更高的应用可能拒绝接收。
- 为减少安静环境下的短词误报，整体音量极低的录音会被判为空；麦克风增益过低时可能漏识别。
- `sherpa-onnx` 的 CPU 模型目前未使用 RTX 3060。后续可在相同接口下比较 Qwen3-ASR 等候选。
