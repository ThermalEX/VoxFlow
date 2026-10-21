"""Interface language: English and Simplified Chinese strings, chosen in settings or from the system locale."""

import os

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

LANGUAGE_CHOICES = (("system", None), ("en", "English"), ("zh", "简体中文"))
_current = "en"

STRINGS: dict[str, tuple[str, str]] = {
    # Overlay status
    "status.loading": ("Loading local speech model…", "正在加载本地语音模型…"),
    "status.press_hotkey": ("Press {hotkey} to speak", "按 {hotkey} 开始说话"),
    "status.mic_unavailable": ("Microphone unavailable: {error}", "麦克风不可用：{error}"),
    "status.asr_missing": ("Speech model missing. Run: python scripts/download_model.py",
                           "缺少语音模型，请运行：python scripts/download_model.py"),
    "status.asr_needed": ("Download the speech recognition model first · click here",
                          "需要先下载语音识别模型 · 点击这里下载"),
    "status.asr_start_failed": ("Could not start recognition: {error}", "无法启动识别：{error}"),
    "status.listening": ("Listening · live transcription", "正在聆听 · 实时转写"),
    "status.continuing": ("Listening · continuing your text", "正在聆听 · 接着已有文字继续"),
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
    "status.shortcut_unavailable": ("{hotkey} is taken · change it in Settings › Shortcuts or click the microphone",
                                    "{hotkey} 已被占用 · 可在 设置 › 快捷键 中更换，或点击麦克风按钮"),
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
    "status.will_remember": ("Remembering…", "正在记住…"),
    "status.remembered": ("Remembered · see Settings › Memory", "已记住 · 可在 设置 › 记忆 中查看"),
    "status.memory_off": ("Memory is off, so nothing was remembered · turn it on in Settings › Memory",
                          "记忆未开启，这次没有记住 · 可在 设置 › 记忆 中打开"),
    # Overlay buttons and tooltips
    "button.continue": ("Continue", "继续说"),
    "suggestion.memory_fill": ("Fill from memory", "按记忆补全"),
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
    "tip.shortcut": ("Shortcut: {hotkey}", "快捷键：{hotkey}"),
    "tip.continue": ("Keep dictating after this text · {hotkey}", "接着这段文字继续说 · {hotkey}"),
    "tip.hide": ("Hide overlay", "隐藏浮层"),
    # Tray
    "tray.tooltip": ("VoxFlow · {hotkey} to speak", "VoxFlow · 按 {hotkey} 说话"),
    "tray.show": ("Show VoxFlow", "显示 VoxFlow"),
    "tray.start": ("Start voice input", "开始语音输入"),
    "tray.settings": ("Settings", "设置"),
    "tray.quit": ("Quit", "退出"),
    "tray.shortcut_title": ("VoxFlow shortcut unavailable", "VoxFlow 快捷键不可用"),
    "tray.shortcut_body": ("{hotkey} is in use. Pick another in Settings › Shortcuts, or open VoxFlow from the tray.",
                           "{hotkey} 已被占用。可在 设置 › 快捷键 中更换，或从托盘打开 VoxFlow。"),
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
    "mic.system_default": ("Follow system default", "跟随系统默认"),
    "mic.virtual": ("{name} (virtual)", "{name}（虚拟）"),
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
    "section.theme": ("Theme", "主题"),
    "field.theme": ("Color mode", "颜色模式"),
    "desc.theme": ("Light or dark look for the settings window.", "设置窗口使用浅色或深色外观。"),
    "theme.system": ("Follow system", "跟随系统"),
    "theme.light": ("Light", "浅色"),
    "theme.dark": ("Dark", "深色"),
    "field.color_theme": ("Color theme", "配色主题"),
    "desc.color_theme": ("Colors the voice overlay and the settings together.", "统一浮层柔光和设置界面的颜色。"),
    "color.sky": ("Sky", "晴空蓝"),
    "color.dusk": ("Dusk", "暮紫"),
    "color.teal": ("Teal", "青绿"),
    "color.amber": ("Amber", "暖橙"),
    "color.blossom": ("Blossom", "樱粉"),
    "color.graphite": ("Graphite", "石墨"),
    "color.custom": ("Custom", "自定义"),
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
    "button.delete_model": ("Delete", "删除"),
    "button.go_download": ("Download", "去下载"),
    "about.restart_tutorial": ("Restart tutorial", "重新开始教程"),
    "button.refresh": ("Refresh", "刷新"),
    "dialog.choose_model": ("Choose a GGUF model", "选择 GGUF 模型"),
    "dialog.choose_server": ("Choose llama-server.exe", "选择 llama-server.exe"),
    "filter.gguf": ("GGUF models (*.gguf)", "GGUF 模型 (*.gguf)"),
    "filter.exe": ("Programs (*.exe)", "程序 (*.exe)"),
    "models.refreshed": ("{count} models found", "找到 {count} 个模型"),
    "models.refresh_failed": ("Could not list models · {reason}", "无法获取模型列表 · {reason}"),
    # Memory page
    "category.memory": ("Memory", "记忆"),
    "field.memory_enable": ("Remember what I dictate", "记住我口述的内容"),
    "desc.memory_enable": ("Confirmed texts are kept on this computer for 7 days; names, terms and plans found "
                           "in them help fix misheard words and fill in details. Saying \"remember …\" keeps "
                           "something forever. Off by default.",
                           "确认发送的文字会保存在本机 7 天，从中找出的人名、专有名词和安排用来纠正听错的字、补全遗漏的信息。"
                           "说“记住……”的内容永久保留。默认关闭。"),
    "field.memory_location": ("Stored on this computer", "保存在本机"),
    "desc.memory_location": ("{path} · turning memory off keeps what is there; Clear deletes it",
                             "{path} · 关闭记忆不会删除已有内容，“清空”才会删除"),
    "button.open_folder": ("Open folder", "打开文件夹"),
    "button.clear_memory": ("Clear all", "清空"),
    "memory.remote_note": ("Smart editing uses an online model: finding things to remember, filling in details and "
                           "daily summaries send your texts and memories to {endpoint}.",
                           "智能编辑当前使用在线模型：提取记忆、补全信息和每日总结会把你的文字和记忆发送到 {endpoint}。"),
    "placeholder.memory_search": ("Search memories", "搜索记忆"),
    "placeholder.memory_new": ("Something to remember, e.g. 张三 is my manager", "要记住的内容，例如：张三是我的主管"),
    "field.memory_saved": ("Saved memories", "已保存的记忆"),
    "desc.memory_saved": ("{count} saved · search, sort, add, edit, delete, keep for 7 days or forever",
                          "共 {count} 条 · 可搜索、排序、添加、编辑、删除，在 7 天和永久之间转移"),
    "button.manage": ("Manage", "管理"),
    "field.memory_days": ("Daily records and summary", "每日记录与总结"),
    "desc.memory_days": ("The texts you confirmed each day; summaries are made only when you ask",
                         "每天确认发送的文字；总结只在你点击时生成"),
    "button.view": ("View", "查看"),
    "button.save": ("Save", "保存"),
    "button.cancel": ("Cancel", "取消"),
    "memory.dialog_title": ("Saved memories", "已保存的记忆"),
    "memory.days_title": ("Daily records and summary", "每日记录与总结"),
    "memory.records_title": ("Texts of the day", "当天的文字"),
    "memory.actions": ("More", "更多"),
    "memory.more_actions": ("More actions", "更多操作"),
    "memory.add": ("Add a memory", "添加记忆"),
    "memory.sort_newest": ("Newest first · click for oldest first", "最新在前 · 点击改为最早在前"),
    "memory.sort_oldest": ("Oldest first · click for newest first", "最早在前 · 点击改为最新在前"),
    "memory.kind.all": ("All kinds", "全部类型"),
    "memory.keep.all": ("All", "全部"),
    "memory.move_forever": ("Keep forever", "改为永久"),
    "memory.move_week": ("Keep for 7 days", "改为 7 天"),
    "memory.count": ("Showing {shown} of {total}", "显示 {shown} / 共 {total} 条"),
    "button.edit": ("Edit", "编辑"),
    "button.delete": ("Delete", "删除"),
    "memory.kind.person": ("Person", "人名"),
    "memory.kind.term": ("Term", "专有名词"),
    "memory.kind.event": ("Plan", "安排"),
    "memory.kind.fact": ("Fact", "事实"),
    "memory.source.explicit": ("You said remember", "口令记住"),
    "memory.source.auto": ("Found automatically", "自动提取"),
    "memory.source.manual": ("Added here", "手动添加"),
    "memory.keep.week": ("7 days", "7 天"),
    "memory.keep.forever": ("Forever", "永久"),
    "memory.time": ("When: {time}", "时间：{time}"),
    "memory.empty": ("Nothing remembered yet. Say \"remember …\" or add one from the ⋯ menu.",
                     "还没有记住任何内容。说“记住……”，或从 ⋯ 菜单添加。"),
    "memory.no_matches": ("Nothing matches", "没有匹配的内容"),
    "memory.today": ("{day} (today)", "{day}（今天）"),
    "button.delete_day": ("Delete this day", "删除这一天"),
    "memory.no_records": ("No texts kept for this day", "这一天没有保存的文字"),
    "field.memory_summary": ("Summary", "总结"),
    "memory.no_summary": ("No summary for this day yet", "这一天还没有总结"),
    "memory.summary_made": ("Summarized {when}", "生成于 {when}"),
    "button.summarize": ("Summarize", "生成总结"),
    "button.summarize_again": ("Summarize again", "重新生成"),
    "button.summarizing": ("Summarizing…", "正在总结…"),
    "memory.summary_empty": ("No texts to summarize", "没有可总结的文字"),
    "memory.summary_model": ("Turn on smart editing and wait for the model to load, then try again",
                             "请开启智能编辑并等待模型加载完成后再试"),
    "memory.summary_failed": ("Could not summarize · {reason}", "无法生成总结 · {reason}"),
    "memory.confirm_clear": ("Delete everything VoxFlow remembers, all kept texts and summaries?",
                             "删除记住的所有内容、保存的文字和总结？"),
    "memory.confirm_delete_day": ("Delete the texts and summary of {day}?", "删除 {day} 的文字和总结？"),
    # Shortcuts page
    "category.shortcuts": ("Shortcuts", "快捷键"),
    "section.global_shortcuts": ("Global shortcuts", "全局快捷键"),
    "field.hotkey_record": ("Start or stop voice input", "开始 / 停止录音"),
    "desc.hotkey_record": ("Works in any app. Press again to stop.", "在任何应用中都可以按，再按一次停止。"),
    "field.hotkey_continue": ("Continue", "继续说"),
    "desc.hotkey_continue": ("Keep dictating after the text in the overlay. Without text it starts a new recording.",
                             "接着浮层里已有的文字继续说；没有文字时等同于开始录音。"),
    "field.hotkey_restore": ("Restore defaults", "恢复默认快捷键"),
    "desc.hotkey_restore": ("{record} and {resume}.", "{record} 和 {resume}。"),
    "hotkey.prompt": ("Press new keys…", "请按下新的组合键…"),
    "hotkey.need_modifier": ("Include Ctrl, Alt or Win", "需包含 Ctrl、Alt 或 Win"),
    "hotkey.help": ("Click a shortcut, then press the new keys. Esc cancels.",
                    "点击快捷键后按下新的组合键，按 Esc 取消。"),
    "hotkey.saved": ("Saved · {hotkey}", "已保存 · {hotkey}"),
    "hotkey.duplicate": ("{hotkey} is already used for {action}", "{hotkey} 已用于“{action}”"),
    "hotkey.in_use": ("{hotkey} is taken by another app · kept the previous shortcut",
                      "{hotkey} 已被其他程序占用 · 仍使用原来的快捷键"),
    "hotkey.invalid": ("{hotkey} cannot be used as a shortcut", "{hotkey} 不能用作快捷键"),
    # About page
    "category.about": ("About", "关于"),
    "about.version": ("Version {version}", "版本 {version}"),
    "about.author": ("Author {author}", "作者 {author}"),
    "about.repo": ("View on GitHub", "查看 GitHub 仓库"),
    "about.models": ("Models on Hugging Face", "Hugging Face 模型"),
    "section.components": ("Components", "组件"),
    "about.asr": ("Speech recognition", "语音识别"),
    "about.rewrite": ("Smart editing", "智能编辑"),
    "about.rewrite_value": ("Qwen3.5-2B fine-tuned · llama.cpp", "Qwen3.5-2B 微调 · llama.cpp"),
    "about.framework": ("Desktop framework", "桌面框架"),
    "about.license": ("License", "许可证"),
    "about.license_value": ("To be decided before release", "发布前确定"),
    "section.updates": ("Updates", "更新"),
    "about.channel": ("Update channel", "更新频道"),
    "desc.channel": ("Stable checks only stable releases; Beta also receives pre-releases.",
                     "正式版只检查稳定发布；测试版同时接收预发布版本。"),
    "channel.stable": ("Stable", "正式版"),
    "channel.beta": ("Beta (includes stable)", "测试版（含正式版）"),
    "about.check_on_start": ("Check for updates at startup", "启动时检查更新"),
    "desc.check_on_start": ("Shows release notes when a new version is out. Nothing downloads automatically.",
                            "发现新版本时显示更新说明，不会自动下载。"),
    "about.check_now": ("Check manually", "手动检查"),
    "desc.check_now": ("Look for a new version on the selected channel now.", "立即检查所选频道是否有新版本。"),
    "button.check_updates": ("Check for updates", "检查更新"),
    "about.updates_note": ("Updates turn on once VoxFlow is published.", "更新功能将在 VoxFlow 正式发布后开放。"),
    # Downloads
    "download.source": ("Download from", "下载源"),
    "download.source.auto": ("Automatic", "自动"),
    "download.source.huggingface": ("Hugging Face", "Hugging Face"),
    "download.source.mirror": ("China mirror", "国内镜像"),
    "download.source_desc": ("Automatic tries Hugging Face first and switches to the China mirror (hf-mirror.com) "
                             "when it cannot connect or is too slow. In mainland China, pick the mirror directly.",
                             "自动：先连 Hugging Face，连不上或太慢就换成国内镜像（hf-mirror.com）。国内网络建议直接选“国内镜像”。"),
    "download.title": ("Download models", "下载模型"),
    "download.load": ("Load list", "加载列表"),
    "download.loading": ("Loading…", "正在加载…"),
    "download.offline": ("Could not connect · showing the built-in list", "无法连接，使用内置列表"),
    "download.selected": ("{count} selected · {size} in total", "已选 {count} 项 · 共 {size}"),
    "download.start": ("Download selected", "下载所选"),
    "download.cancel": ("Cancel", "取消"),
    "download.cancel_all": ("Cancel all", "全部取消"),
    "download.background": ("You can close this window; downloads continue in the background.",
                            "可以关闭窗口，下载会在后台继续。"),
    "download.installed": ("Installed", "已安装"),
    "download.required": ("Required", "必需"),
    "download.recommended": ("Recommended", "推荐"),
    "download.needs_nvidia": ("Needs an NVIDIA graphics card", "需要 NVIDIA 显卡"),
    "download.queued": ("Queued", "排队中"),
    "download.verifying": ("Verifying…", "正在校验…"),
    "download.cancelled": ("Cancelled", "已取消"),
    "download.progress": ("{percent}% · {done} / {total} · {speed} · {eta}", "{percent}% · {done} / {total} · {speed} · {eta}"),
    "download.eta_seconds": ("about {count} s left", "约 {count} 秒"),
    "download.eta_minutes": ("about {count} min left", "约 {count} 分钟"),
    "download.done_title": ("VoxFlow downloads finished", "VoxFlow 下载已结束"),
    "download.done_body": ("Open Settings › Smart editing to see the results.", "可在 设置 › 智能编辑 中查看结果。"),
    "download.error.network": ("Network interrupted · download again to resume", "网络中断 · 重新下载会从断点继续"),
    "download.error.hash": ("The file was damaged · download it again", "文件校验失败 · 请重新下载"),
    "download.error.install": ("Could not install · close programs using these files and try again",
                               "安装失败 · 请关闭正在使用这些文件的程序后重试"),
    "download.error.delete": ("Could not delete the model · {reason}", "无法删除模型 · {reason}"),
    "download.error.disk": ("Could not save the file · check free disk space", "无法保存文件 · 请检查磁盘空间"),
    # First-run tutorial
    "onboarding.window_title": ("Welcome to VoxFlow", "欢迎使用 VoxFlow"),
    "onboarding.skip": ("Skip", "跳过"),
    "onboarding.back": ("Back", "上一步"),
    "onboarding.next": ("Next", "下一步"),
    "onboarding.start": ("Get started", "开始使用"),
    "onboarding.welcome_title": ("Welcome to VoxFlow", "欢迎使用 VoxFlow"),
    "onboarding.welcome_desc": ("Speak, and your words are typed for you. Setting up takes about two minutes.",
                                "说话，就能输入文字。接下来花 2 分钟完成设置。"),
    "onboarding.look_title": ("Choose a look", "选择外观"),
    "onboarding.look_desc": ("The color theme colors the voice overlay and the settings together.",
                             "配色主题会统一浮层柔光和设置界面的颜色。"),
    "onboarding.look_custom": ("You can pick your own colors later in Settings › Appearance.",
                               "之后可以在 设置 › 外观 中自定义颜色。"),
    "onboarding.mic_title": ("Choose a microphone", "选择麦克风"),
    "onboarding.mic_desc": ("Say something: the bar below moves with your voice. "
                            "The level is measured on this PC only; nothing is recorded.",
                            "对着麦克风说句话，下面的音量条会跳动。只在本机计算音量，不会录音。"),
    "onboarding.mic_missing": ("No microphone found. Plug one in, then reopen this step.",
                               "没有找到麦克风。接好麦克风后再回到这一步。"),
    "onboarding.download_title": ("Download components", "下载组件"),
    "onboarding.download_desc": ("The speech model is required. llama.cpp and a smart editing model polish your text; "
                                 "you can also download them later in Settings › Smart editing.",
                                 "语音识别模型是必需的；llama.cpp 和智能编辑模型用于整理文字，也可以之后在 设置 › 智能编辑 中下载。"),
    "onboarding.try_title": ("Give it a try", "动手试一次"),
    "onboarding.try_text": ("Click into any text box, press {hotkey} and speak. Press it again to stop.",
                            "把光标放到任意输入框，按 {hotkey} 开始说话，再按一次停止。"),
    "onboarding.try_example": ("Try saying: “Um, meeting at three tomorrow, no, four”",
                               "试试说：“额，明天下午三点开会，不对，四点”"),
    "onboarding.try_result": ("Smart editing turns it into: “Meeting at four tomorrow.”",
                              "智能编辑会整理成：“明天下午四点开会。”"),
    "onboarding.try_keys": ("Press Enter to type it in, Esc to cancel.", "按 Enter 输入，Esc 取消。"),
    "onboarding.try_missing": ("You can try it as soon as the speech model has downloaded.",
                               "语音识别模型下载完成后即可试用。"),
    "onboarding.memory_title": ("Memory (optional)", "记忆（可选）"),
    "onboarding.memory_desc": ("VoxFlow can remember names, terms and plans from what you dictate: it then writes "
                               "names the way you taught it, can fill in a meeting time you left out, and can "
                               "summarize a day when you ask in Settings › Memory.",
                               "VoxFlow 可以从你口述的内容里记住人名、专有名词和安排：之后按记住的写法纠正人名，"
                               "能补上你漏说的会议时间，也可以在 设置 › 记忆 里按需生成每日总结。"),
    "onboarding.memory_keep": ("Confirmed texts are kept for 7 days; say \"remember …\" to keep something forever. "
                               "You can move anything between 7 days and forever, or delete it.",
                               "确认发送的文字保留 7 天；说“记住……”的内容永久保留。任何一条都可以在 7 天和永久之间转移，或者删除。"),
    "onboarding.memory_privacy": ("Everything stays on this computer while you use the local model. Off until you "
                                  "turn it on; you can change this any time in Settings.",
                                  "使用本地模型时，所有内容只保存在本机。打开之前不会记录任何内容，之后随时可以在设置里关闭。"),
    "onboarding.tips_title": ("You're all set", "准备好了"),
    "onboarding.tip_commands": ("Say “translate to English” or “make it more polite” and it happens.",
                                "说“翻译成英文”“正式一点”，会直接执行。"),
    "onboarding.tip_continue": ("Click Continue after a result to keep dictating.", "说完后点“继续说”，可以接着补充。"),
    "onboarding.tip_undo": ("Hover Undo edits to see what you originally said.", "鼠标悬停“撤回修改”可以查看原文。"),
    "onboarding.tip_tray": ("VoxFlow stays in the tray at the bottom right.", "VoxFlow 常驻在右下角托盘。"),
    # Local model state
    "model.off": ("Off · turn on smart editing to start it", "未启动 · 开启智能编辑后会自动启动"),
    "model.custom": ("Custom endpoint · use Test connection to check it", "自定义接口 · 可点击“测试连接”检查"),
    "model.starting": ("Starting…", "正在启动…"),
    "model.ready": ("Ready", "已就绪"),
    "model.missing_server": ("llama.cpp is not installed · download it below", "未安装 llama.cpp · 可在下方下载"),
    "model.not_installed": ("No model installed · download one below", "未安装模型 · 可在下方下载"),
    "model.missing_model": ("Model file not found: {path}", "找不到模型文件：{path}"),
    "model.failed": ("Stopped · {detail}", "已停止 · {detail}"),
    # Local model dropdown
    "model.note.recommended": ("Recommended", "推荐"),
    "model.note.run": ("training run", "训练目录"),
    "model.note.archived": ("archived", "旧版"),
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
    apply_qt_language(_current)


def language() -> str:
    return _current


_qt_translator: QTranslator | None = None


def apply_qt_language(code: str) -> bool:
    """Translate Qt's own dialogs (color picker, OK/Cancel) to match the interface language."""
    global _qt_translator
    app = QCoreApplication.instance()
    if app is None:
        return False
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if code != "zh":
        return False
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load("qtbase_zh_CN", folder):
        return False
    app.installTranslator(translator)
    _qt_translator = translator
    return True


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
