"""Interface language: English and Simplified Chinese strings, chosen in settings or from the system locale."""

import os

from PySide6.QtCore import QLocale

LANGUAGE_CHOICES = (("system", None), ("en", "English"), ("zh", "简体中文"))
_current = "en"

STRINGS: dict[str, tuple[str, str]] = {
    # Overlay status
    "status.loading": ("Loading local speech model…", "正在加载本地语音模型…"),
    "status.press_hotkey": ("Press Ctrl+Shift+Space to speak", "按 Ctrl+Shift+Space 开始说话"),
    "status.mic_unavailable": ("Microphone unavailable: {error}", "麦克风不可用：{error}"),
    "status.asr_missing": ("Speech model missing. Run: python scripts/download_model.py",
                           "缺少语音模型，请运行：python scripts/download_model.py"),
    "status.asr_start_failed": ("Could not start recognition: {error}", "无法启动识别：{error}"),
    "status.listening": ("Listening · live transcription", "正在聆听 · 实时转写"),
    "status.mic_start_failed": ("Could not start microphone: {error}", "无法启动麦克风：{error}"),
    "status.finalizing": ("Finalizing transcript…", "正在生成最终文字…"),
    "status.too_short": ("Recording was too short. Try again.", "录音太短，请再试一次。"),
    "status.asr_load_failed": ("Could not load speech model: {error}", "无法加载语音模型：{error}"),
    "status.transcription_failed": ("Transcription failed: {error}", "识别失败：{error}"),
    "status.recording_notice": ("Recording notice: {notice}", "录音提示：{notice}"),
    "status.draft_saved": ("Live draft saved · edit or confirm", "已保留实时草稿 · 可编辑或确认"),
    "status.ready": ("Transcript ready · edit or confirm", "文字已就绪 · 可编辑或确认"),
    "status.no_speech": ("No speech detected. Try again.", "没有检测到语音，请再试一次。"),
    "status.listening_draft": ("Listening · draft may change", "正在聆听 · 草稿可能变化"),
    "status.paste_failed": ("Could not focus the previous input · text copied for manual paste",
                            "无法切回之前的输入框 · 文字已复制，可手动粘贴"),
    "status.shortcut_unavailable": ("Shortcut unavailable · click the microphone", "快捷键不可用 · 请点击麦克风按钮"),
    "status.polishing": ("Polishing…", "正在整理…"),
    "status.polished": ("Polished · hover Undo edits to see the original", "已整理 · 悬停“撤回修改”可查看原文"),
    "status.no_edits": ("Transcript ready · no edits needed", "文字已就绪 · 无需修改"),
    "status.waiting_model": ("Waiting for the local model · you can confirm the original now",
                             "正在等待本地模型 · 现在也可以直接确认原文"),
    "status.smart_failed": ("Smart editing unavailable · kept the original ({reason})",
                            "智能编辑暂不可用 · 已保留原文（{reason}）"),
    "status.local_failed": ("Local model unavailable · kept the original", "本地模型不可用 · 已保留原文"),
    "status.suggestion_applied": ("Suggestion applied · Undo edits returns to the original",
                                  "已采用建议 · “撤回修改”可回到原文"),
    # Overlay buttons and tooltips
    "button.undo_edits": ("Undo edits", "撤回修改"),
    "button.restore_edits": ("Restore edits", "恢复修改"),
    "button.start_recording": ("Start recording", "开始录音"),
    "button.stop_recording": ("Stop recording", "停止录音"),
    "button.transcribing": ("Transcribing…", "正在识别…"),
    "button.record_again": ("Record again", "再录一次"),
    "tip.open_settings": ("Open settings", "打开设置"),
    "tip.confirm": ("Confirm and insert text", "确认并输入文字"),
    "tip.start_voice": ("Start voice input", "开始语音输入"),
    "tip.toggle_voice": ("Start or stop voice input", "开始或停止语音输入"),
    "tip.shortcut": ("Shortcut: Ctrl+Shift+Space", "快捷键：Ctrl+Shift+Space"),
    "tip.hide": ("Hide overlay", "隐藏浮层"),
    # Tray
    "tray.tooltip": ("VoxFlow · Ctrl+Shift+Space to speak", "VoxFlow · 按 Ctrl+Shift+Space 说话"),
    "tray.show": ("Show VoxFlow", "显示 VoxFlow"),
    "tray.start": ("Start voice input", "开始语音输入"),
    "tray.settings": ("Settings", "设置"),
    "tray.quit": ("Quit", "退出"),
    "tray.shortcut_title": ("VoxFlow shortcut unavailable", "VoxFlow 快捷键不可用"),
    "tray.shortcut_body": ("Ctrl+Shift+Space is in use. Open VoxFlow from the tray.",
                           "Ctrl+Shift+Space 已被占用，请从托盘打开 VoxFlow。"),
    # Settings window
    "settings.title": ("VoxFlow Settings", "VoxFlow 设置"),
    "settings.eyebrow": ("PREFERENCES", "偏好设置"),
    "settings.categories": ("Settings categories", "设置分类"),
    "category.personalization": ("Personalization", "个性化"),
    "category.app": ("App settings", "应用设置"),
    "category.smart": ("Smart editing", "智能编辑"),
    "page.personalization.desc": ("Changes appear in the voice overlay immediately.", "修改会立即显示在语音浮层上。"),
    "field.font": ("Transcript font", "文字字体"),
    "field.text_size": ("Text size", "字号"),
    "field.background": ("Background glow", "背景柔光"),
    "field.capsule": ("Capsule glow", "胶囊柔光"),
    "button.restore_appearance": ("Restore appearance defaults", "恢复默认外观"),
    "button.change_color": ("{color}    Change…", "{color}    更改…"),
    "page.app.desc": ("Choose how VoxFlow listens and displays speech.", "选择 VoxFlow 如何收音和显示文字。"),
    "field.language": ("Interface language", "界面语言"),
    "language.system": ("Follow system", "跟随系统"),
    "field.microphone": ("Microphone", "麦克风"),
    "field.alignment": ("Transcript alignment", "文字对齐"),
    "align.left": ("Left", "左对齐"),
    "align.center": ("Center", "居中"),
    "align.right": ("Right", "右对齐"),
    "page.app.note": ("Confirm inserts the final text into the last active app.",
                      "确认后会把最终文字输入到之前使用的应用。"),
    "page.smart.desc": ("Polish the final transcript with a rewrite model. The original stays one click away.",
                        "用改写模型整理最终文字，原文随时可以撤回。"),
    "smart.enable": ("Polish final transcripts and suggest rewrites", "整理最终文字并给出改写建议"),
    "field.model_source": ("Model source", "模型来源"),
    "source.local": ("VoxFlow local model", "VoxFlow 本地模型"),
    "source.custom": ("Custom OpenAI-compatible endpoint", "自定义 OpenAI 兼容接口"),
    "field.endpoint": ("Endpoint", "接口地址"),
    "field.model": ("Model", "模型名"),
    "field.api_key": ("API key", "API Key"),
    "placeholder.model": ("Model name", "模型名称"),
    "placeholder.optional": ("Optional", "可选"),
    "field.server_path": ("llama-server", "llama-server 程序"),
    "field.model_path": ("Model file (GGUF)", "模型文件（GGUF）"),
    "field.model_status": ("Status", "状态"),
    "button.test": ("Test connection", "测试连接"),
    "test.testing": ("Testing…", "正在测试…"),
    "test.connected": ("Connected · {model}", "已连接 · {model}"),
    "test.failed": ("Not connected · {reason}", "未连接 · {reason}"),
    "test.unavailable": ("Connection test is unavailable", "无法进行连接测试"),
    # Settings layout
    "settings.heading": ("Settings", "设置"),
    "category.general": ("General", "常规"),
    "category.appearance": ("Appearance", "外观"),
    "section.language": ("Language", "语言"),
    "section.input": ("Input", "输入"),
    "section.text": ("Text", "文字"),
    "section.glow": ("Glow", "柔光"),
    "section.reset": ("Reset", "重置"),
    "section.model": ("Model", "模型"),
    "section.advanced": ("Advanced", "高级"),
    "desc.language": ("Applies immediately to the overlay, settings and tray.", "切换后立即应用到浮层、设置和托盘菜单。"),
    "desc.microphone": ("Device used for voice input.", "语音输入使用的设备。"),
    "desc.alignment": ("How the transcript lines up in the overlay.", "浮层中文字的对齐方式。"),
    "desc.font": ("Font of the transcript in the overlay.", "浮层中识别文字的字体。"),
    "desc.text_size": ("Size of the transcript text.", "识别文字的大小。"),
    "desc.background": ("Soft glow behind the overlay.", "浮层背后柔光的颜色。"),
    "desc.capsule": ("Glow of the voice capsule.", "语音胶囊的颜色。"),
    "field.restore": ("Restore defaults", "恢复默认外观"),
    "desc.restore": ("Font, size and colors go back to their defaults.", "字体、字号和颜色恢复为默认值。"),
    "button.restore": ("Restore", "恢复"),
    "field.smart_enable": ("Polish transcripts", "整理文字"),
    "desc.smart_enable": ("Remove fillers, apply spoken edits and instructions, then suggest rewrites. "
                          "The local model loads when VoxFlow starts.",
                          "去掉口气词，按改口和语音指令修改，并给出改写建议。VoxFlow 启动时自动加载本地模型。"),
    "desc.model_source": ("Run VoxFlow's model on this PC, or use any OpenAI-compatible service.",
                          "在本机运行 VoxFlow 模型，或使用任意 OpenAI 兼容服务。"),
    "field.local_model": ("Model", "模型"),
    "desc.local_model": ("GGUF models found on this PC.", "本机找到的 GGUF 模型。"),
    "desc.endpoint": ("Base URL, usually ending in /v1.", "接口地址，通常以 /v1 结尾。"),
    "desc.custom_model": ("Pick one from the service or type a name.", "从服务获取列表，或直接输入模型名。"),
    "desc.api_key": ("Leave empty if the service does not need one.", "服务不需要时留空。"),
    "desc.server_path": ("llama-server.exe from the llama.cpp Windows release.", "llama.cpp Windows 版中的 llama-server.exe。"),
    "button.browse": ("Browse…", "浏览…"),
    "button.refresh": ("Refresh", "刷新"),
    "dialog.choose_model": ("Choose a GGUF model", "选择 GGUF 模型"),
    "dialog.choose_server": ("Choose llama-server.exe", "选择 llama-server.exe"),
    "filter.gguf": ("GGUF models (*.gguf)", "GGUF 模型 (*.gguf)"),
    "filter.exe": ("Programs (*.exe)", "程序 (*.exe)"),
    "models.refreshed": ("{count} models found", "找到 {count} 个模型"),
    "models.refresh_failed": ("Could not list models · {reason}", "无法获取模型列表 · {reason}"),
    # Local model state
    "model.off": ("Off · turn on smart editing to start it", "未启动 · 开启智能编辑后会自动启动"),
    "model.custom": ("Custom endpoint · use Test connection to check it", "自定义接口 · 可点击“测试连接”检查"),
    "model.starting": ("Starting…", "正在启动…"),
    "model.ready": ("Ready", "已就绪"),
    "model.missing_server": ("llama-server not found: {path}", "找不到 llama-server：{path}"),
    "model.missing_model": ("Model file not found: {path}", "找不到模型文件：{path}"),
    "model.failed": ("Stopped · {detail}", "已停止 · {detail}"),
    # Local model dropdown
    "model.choice.q8": ("Q8 · {size} · Recommended", "Q8 · {size} · 推荐"),
    "model.choice.q4": ("Q4 · {size} · Less GPU memory", "Q4 · {size} · 更省显存"),
    "model.choice.bf16": ("BF16 · {size} · Full precision", "BF16 · {size} · 全精度"),
    "model.choice.other": ("{name} · {size}", "{name} · {size}"),
    "model.choice.missing": ("{name} (not found)", "{name}（未找到）"),
    "model.browse": ("Browse…", "浏览…"),
    # Errors shown to the user
    "error.unreachable": ("the model server is not reachable", "无法连接模型服务"),
    "error.timeout": ("the model did not answer in time", "模型响应超时"),
    "error.http": ("the server returned HTTP {code}", "服务返回 HTTP {code}"),
    "error.bad_response": ("the server sent an unexpected response", "返回内容无法识别"),
    "error.empty": ("the model returned no text", "模型没有返回文字"),
    "error.truncated": ("the rewrite was cut off", "改写结果被截断"),
    "error.disabled": ("smart editing is off", "智能编辑已关闭"),
    "error.starting": ("the local model is still starting", "本地模型仍在启动"),
    "error.missing_server": ("llama-server not found: {path}", "找不到 llama-server：{path}"),
    "error.missing_model": ("model file not found: {path}", "找不到模型文件：{path}"),
    "error.local_failed": ("the local model stopped · {detail}", "本地模型已停止 · {detail}"),
    "error.other": ("{detail}", "{detail}"),
}


def system_language() -> str:
    override = os.environ.get("VOXFLOW_LANG", "")
    if override in ("en", "zh"):
        return override
    return "zh" if QLocale.system().name().lower().startswith("zh") else "en"


def resolve(choice: str) -> str:
    return choice if choice in ("en", "zh") else system_language()


def set_language(code: str) -> None:
    global _current
    _current = "zh" if code == "zh" else "en"


def language() -> str:
    return _current


def tr(key: str, **values) -> str:
    english, chinese = STRINGS[key]
    text = chinese if _current == "zh" else english
    return text.format(**values) if values else text


def describe_error(error: Exception) -> str:
    """Turn a RewriteError (or anything else) into a short sentence in the interface language."""
    kind = getattr(error, "kind", "other")
    values = {"code": getattr(error, "code", ""), "path": getattr(error, "path", ""), "detail": str(error)}
    key = f"error.{kind}"
    return tr(key if key in STRINGS else "error.other", **values)
