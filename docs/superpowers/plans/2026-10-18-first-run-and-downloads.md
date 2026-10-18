# 新手教程、组件下载与配色主题 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 安装包只含程序本体；语音模型、llama.cpp（通用版 / NVIDIA 加速版二选一）和改写模型在软件里勾选下载；首次启动有 6 步新手教程；外观页加入统一浮层与设置界面的配色主题。

**Architecture:** 新增“数据目录”概念（源码运行 = 仓库根目录，安装版 = `%LOCALAPPDATA%\VoxFlow`），所有模型与运行组件都从数据目录发现。下载清单 `catalog.json` 放在 Hugging Face，软件内置一份副本兜底；后台下载器逐项下载、断点续传、SHA-256 校验后才安装。下载面板是一个独立控件，设置页与新手教程共用。配色主题是一组颜色（浮层背景、胶囊、强调色），由设置窗口统一发出变更信号，浮层和所有设置类窗口一起换色。

**Tech Stack:** Python 3.12、PySide6 6.10.1、urllib（下载）、hashlib、zipfile、sounddevice（教程试音）、PyInstaller + Inno Setup、huggingface_hub（仅发布脚本）。

**Spec:** [docs/superpowers/specs/2026-10-18-first-run-and-downloads-design.md](../specs/2026-10-18-first-run-and-downloads-design.md)

## Global Constraints

- 所有新界面文字加到 `voxflow/i18n.py` 的 `STRINGS`（英文、简体中文两份），用 `tr()`；浮层状态用 `show_status(key)`。
- 用户设置存 `QSettings("VoxFlow", "VoxFlow")`；新键：`ui/color_theme`、`downloads/source`、`onboarding/done`。
- 测试不访问网络、不写用户注册表：网络层可注入，设置用临时 INI `QSettings`。
- 已下载文件必须通过 SHA-256 校验才算安装；未完成的下载只存在于 `*.part`。
- 不把录音写入磁盘；教程试音只在内存里算音量。
- Hugging Face 地址：`https://huggingface.co/{repo}/resolve/{revision}/{path}`；国内镜像把主机换成 `hf-mirror.com`，路径不变。
- 改写模型仓库 `ThermalEX/voxflow-rewrite`，标签 `v4`；语音模型仓库 `csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`，提交 `2365baeacb507f821a0c8120fcee3d484dba7a07`；llama.cpp 版本 `b11596`。
- “自动”下载源：先连 Hugging Face，连接失败或前 10 秒平均速度低于 200 KB/s 时，从断点切换到镜像。
- 下载逐项进行，不并行。
- 新图标只用 Google Material Symbols（`voxflow/assets/icons/`，同步 README 来源说明与 `pyproject.toml` 的 `package-data`）。
- 提交信息不加 Claude 署名。

## Review Focus

1. **下载中途断网 / 电脑睡眠**：再次下载应从 `.part` 续传，不会把半截文件当成已安装（Task 4 `test_resumes_from_partial_file`、`test_interrupted_download_is_not_installed`）。
2. **文件被篡改或镜像返回错误内容**：校验失败要删除文件、该项标为失败，不能被选用（Task 4 `test_hash_mismatch_discards_file`）。
3. **数据目录写不了（磁盘满、权限）**：显示错误、该项失败，程序不崩溃（Task 4 `test_write_error_fails_item`）。
4. **删除正在使用的模型**：智能编辑应切到其他已安装模型，或显示“未安装”，不能崩溃或继续指向不存在的文件（Task 6 `test_deleting_model_in_use_switches_or_disables`）。
5. **清单地址返回 404 或乱码**：回退到内置清单并提示，不能出现空列表（Task 3 `test_bad_remote_catalog_falls_back_to_builtin`）。

---

### Task 1: 数据目录

**Files:**
- Modify: `voxflow/paths.py`、`voxflow/__main__.py`（`DEFAULT_MODEL_DIR`）、`voxflow/model_catalog.py`、`voxflow/smart_editing.py`（`REPO_ROOT` → 数据目录）、`voxflow/settings_window.py`（`REPO_ROOT` 用于模型发现与相对路径的部分）
- Test: `tests/test_paths.py`、`tests/test_model_catalog.py`

**Interfaces:**
- Produces: `paths.data_root() -> Path`、常量 `paths.DATA_ROOT`。源码运行返回仓库根目录；`sys.frozen` 时返回 `Path(os.environ["LOCALAPPDATA"]) / "VoxFlow"` 并确保目录存在。`APP_ROOT` 保留（程序文件位置）。
- 约定：数据目录下的布局与仓库一致——`models/<ASR 名称>/`、`runtime/llama.cpp/`、`runtime/models/*.gguf`。设置里保存的相对路径一律相对数据目录解析。

- [ ] **Step 1:** 在 `tests/test_paths.py` 加 `test_installed_app_keeps_downloads_in_local_app_data`：monkeypatch `sys.frozen=True`、`LOCALAPPDATA=tmp_path`，断言 `paths.data_root() == tmp_path / "VoxFlow"` 且目录已创建；加 `test_source_checkout_keeps_downloads_in_the_repository`：断言源码运行时 `data_root() == app_root()`。
- [ ] **Step 2:** 运行 `.\.venv\Scripts\python.exe -m pytest -q tests/test_paths.py`，预期 FAIL（`data_root` 未定义）。
- [ ] **Step 3:** 实现 `data_root()`，把上面列出的四个模块里“找模型 / 找 llama-server / 写 llama-server.log / 解析设置里的相对路径”的根目录换成 `DATA_ROOT`。`SettingsWindow` 里 `_repo_relative` / `_same_path` 改为相对 `DATA_ROOT`（函数名可改为 `_data_relative`）。
- [ ] **Step 4:** 运行全部测试，预期全部 PASS（源码运行时数据目录等于仓库根目录，行为不变）。
- [ ] **Step 5:** 提交 `Keep models and runtime in a per-user data folder when installed`。

---

### Task 2: 配色主题

**Files:**
- Create: `voxflow/color_themes.py`
- Modify: `voxflow/settings_theme.py`（`Theme` 支持替换强调色）、`voxflow/settings_window.py`（外观页）、`voxflow/window.py`（浮层取色）、`voxflow/i18n.py`
- Test: `tests/test_color_themes.py`、`tests/test_settings_widgets.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ColorTheme: id: str; name_key: str; background: str; capsule: str; accent_light: str; accent_dark: str`
  - `PRESETS: tuple[ColorTheme, ...]`，6 项，id 依次为 `sky`（默认，`background="#438aee"`、`capsule="#2766d6"`，强调色沿用现有 `#2F7CF6` / `#3D8BFF`）、`dusk`、`teal`、`amber`、`blossom`、`graphite`；`CUSTOM = "custom"`。
  - `saved_color_theme(settings) -> ColorTheme`：读 `ui/color_theme`；为 `custom` 时用 `appearance/background_color`、`appearance/capsule_color` 组成主题，两种模式的强调色都等于胶囊色。
  - `migrate_color_theme(settings) -> None`：没有 `ui/color_theme`、但存过与默认不同的柔光颜色的，写入 `custom`；否则写入 `sky`。
  - `settings_theme.with_accent(theme: Theme, accent: str) -> Theme`（`dataclasses.replace`）。
  - `SettingsWindow.color_theme_changed = Signal(object)`（发出 `ColorTheme`）；`SettingsWindow.color_theme_buttons: dict[str, QAbstractButton]`（键为 id 和 `"custom"`）。
  - 设置窗口应用主题时调用 `stylesheet(with_accent(current_theme(...), accent))`；其他设置类窗口（Task 7 的教程窗口）通过同一信号换色。

- [ ] **Step 1:** 写 `tests/test_color_themes.py`：
  - `test_presets_have_unique_ids_and_readable_accents`：6 个 id 唯一；每个 `accent_light` 与白色、`accent_dark` 与 `#212121` 的对比度 ≥ 3:1（写一个 WCAG 相对亮度的小函数）。
  - `test_custom_theme_uses_saved_glow_colors`：存 `ui/color_theme=custom`、两种颜色后，`saved_color_theme` 返回这两种颜色，强调色等于胶囊色。
  - `test_migration_keeps_customized_colors`：只存了 `appearance/capsule_color="#ff0000"` → 迁移后 `ui/color_theme == "custom"`；什么都没存 → `"sky"`。
- [ ] **Step 2:** 在 `tests/test_settings_widgets.py`（或新文件 `tests/test_settings_color_theme.py`）加：
  - `test_picking_a_preset_recolors_overlay_and_settings`：构造 `VoxFlowWindow(start_worker=False, settings=临时INI)`，点 `settings_window.color_theme_buttons["teal"]`，断言 `window.background_color.name()`、`window.capsule.accent_color.name()` 等于 teal 的 `background`、`capsule`，设置窗口样式表中含 teal 的强调色，`ui/color_theme == "teal"`。
  - `test_custom_shows_color_pickers_only_when_selected`：选预设时两个颜色按钮所在的行隐藏，选 `custom` 时显示。
  - `test_restore_appearance_returns_to_default_theme`：点“恢复”后 `ui/color_theme == "sky"`。
- [ ] **Step 3:** 运行上述测试，预期 FAIL。
- [ ] **Step 4:** 实现。外观页最上面新增“配色主题”区：7 个圆角色块（6 个预设 + “自定义”）排成一行，选中项有描边；预设名称加到 `i18n`（中文用设计草图里的晴空蓝、暮紫、青绿、暖橙、樱粉、石墨，英文 Sky、Dusk、Teal、Amber、Blossom、Graphite）。原“柔光”区的两个颜色按钮只在“自定义”时显示。启动时 `VoxFlowWindow.__init__` 调用 `migrate_color_theme`，再按 `saved_color_theme` 设置浮层颜色。具体色值由实现者定，需满足 Step 1 的对比度测试。
- [ ] **Step 5:** 运行全部测试，预期 PASS。用 `VOXFLOW_THEME=dark` / `light` 各截一张外观页图（参照 `.superpowers/tmp/shot_pages.py`），确认色块与选中状态清楚。
- [ ] **Step 6:** 提交 `Add color themes that recolor the overlay and settings together`。

---

### Task 3: 下载清单

**Files:**
- Create: `voxflow/catalog.py`、`voxflow/assets/catalog.json`（内置副本，内容由 Task 8 发布后回填；本任务先放入下文已知的条目）
- Modify: `pyproject.toml`（`package-data` 加 `assets/catalog.json`）
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class CatalogFile: repo: str; revision: str; path: str; size: int; sha256: str; dest: str; extract: bool = False`（`dest` 为相对数据目录的目标：普通文件是文件路径，`extract=True` 时是解压目标目录）
  - `@dataclass(frozen=True) class CatalogItem: id: str; kind: str  # "asr" | "runtime" | "rewrite"; group: str  # 同组只能装一个，如 "llama"；required: bool; recommended: bool; needs_nvidia: bool; title: dict[str, str]; desc: dict[str, str]; files: tuple[CatalogFile, ...]; check: str  # 判断是否已安装的相对路径`
  - `parse_catalog(data: dict) -> list[CatalogItem]`（字段缺失或类型不对时抛 `ValueError`）
  - `builtin_catalog() -> list[CatalogItem]`
  - `fetch_catalog(source: str, opener=urllib.request.urlopen, timeout: float = 10) -> tuple[list[CatalogItem], bool]`：返回（条目，是否来自网络）；网络或解析失败时返回内置清单和 `False`。远程地址：`ThermalEX/voxflow-rewrite` 仓库 `main` 分支的 `catalog.json`。
  - `file_url(file: CatalogFile, source: str) -> str`，`source` 取 `"huggingface"` 或 `"mirror"`。
  - `installed_ids(items, root: Path) -> set[str]`：读 `root / "installed.json"`（`{id: sha256 列表}`）；没有记录的条目，若 `root / item.check` 存在也算已安装（兼容源码运行时已有的文件）。
  - `SOURCES = ("auto", "huggingface", "mirror")`
- 内置条目（id → 内容）：
  - `asr-sensevoice`：kind `asr`，required；文件 `model.int8.onnx`（239233841 字节，sha256 `c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51`）、`tokens.txt`、`LICENSE`，目标 `models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/`；`check` 为其中的 `model.int8.onnx`。`tokens.txt`、`LICENSE` 的大小与 sha256 在 Task 8 下载核对后回填。
  - `llama-vulkan`：kind `runtime`，group `llama`，recommended；`runtime/llama-b11596-bin-win-vulkan-x64.zip`，`extract=True`，目标 `runtime/llama.cpp`；`check` 为 `runtime/llama.cpp/llama-server.exe`。
  - `llama-cuda`：kind `runtime`，group `llama`，`needs_nvidia`；两个 zip（`llama-b11596-bin-win-cuda-12.4-x64.zip`、`cudart-llama-bin-win-cuda-12.4-x64.zip`）解压到同一目录。
  - `rewrite-v4-q8`（recommended）、`rewrite-v4-q4`：仓库 `ThermalEX/voxflow-rewrite`，revision `v4`，目标 `runtime/models/voxflow-rewrite-v4-q8_0.gguf` / `…-v4-q4_k_m.gguf`，大小与 sha256 见设计文档 §6.2（Q8 2076674496 / `0d0750…47b5`，Q4 1312164288 / `94b067…9d84`）。
  - 说明文字照设计文档 §7.5 的效果说明写中英文两份。

- [ ] **Step 1:** 写 `tests/test_catalog.py`：
  - `test_builtin_catalog_parses_and_has_required_speech_model`
  - `test_file_url_uses_mirror_host`：`file_url(..., "mirror")` 以 `https://hf-mirror.com/ThermalEX/voxflow-rewrite/resolve/v4/` 开头。
  - `test_bad_remote_catalog_falls_back_to_builtin`：opener 分别抛 `URLError`、返回 404、返回非 JSON 文本 → 三种情况都返回内置清单且第二个值为 `False`。
  - `test_remote_catalog_replaces_builtin`：opener 返回含一个新条目的合法 JSON → 返回该条目、`True`。
  - `test_installed_ids_reads_record_and_existing_files`：`installed.json` 记录了 `rewrite-v4-q4`；另在 tmp 目录放 `runtime/llama.cpp/llama-server.exe` → 结果包含两者。
- [ ] **Step 2:** 运行测试，预期 FAIL。
- [ ] **Step 3:** 实现 `voxflow/catalog.py` 和内置 `catalog.json`（JSON 字段名与 dataclass 字段一致，`title`/`desc` 为 `{"en": …, "zh": …}`）。
- [ ] **Step 4:** 运行测试，预期 PASS。
- [ ] **Step 5:** 提交 `Add the download catalog with a built-in fallback`。

---

### Task 4: 后台下载器

**Files:**
- Create: `voxflow/downloads.py`
- Test: `tests/test_downloads.py`

**Interfaces:**
- Consumes: Task 3 的 `CatalogItem`、`CatalogFile`、`file_url`；Task 1 的 `DATA_ROOT`。
- Produces: `class DownloadManager(QObject)`，构造参数 `(root: Path, opener=urllib.request.urlopen, clock=time.monotonic)`。
  - 方法：`start(items: list[CatalogItem], source: str)`、`cancel(item_id: str)`、`cancel_all()`、`remove(item: CatalogItem) -> None`（删除已安装文件并更新 `installed.json`）、`is_busy() -> bool`。
  - 信号：`progress(str item_id, int done_bytes, int total_bytes, float bytes_per_second)`、`item_state(str item_id, str state)`（`"queued" | "downloading" | "verifying" | "installed" | "failed" | "cancelled"`）、`item_failed(str item_id, str error_key)`（i18n 键，如 `download.error.network`、`download.error.hash`、`download.error.disk`）、`all_done()`。
  - 在一个工作线程里逐项、逐文件下载；信号跨线程投递到界面线程。
  - 文件先写 `dest.part`，已有 `.part` 时用 `Range: bytes=<size>-` 续传（服务器回 200 而非 206 时从头写）；读完后校验 sha256，不符则删除 `.part` 并失败；通过后改名为正式文件。`extract=True` 的 zip 解压到 `dest` 的临时兄弟目录，只取 llama-server 运行需要的文件（规则同 `packaging/build.py` 的 `copy_runtime`：跳过除 `llama-server.exe` 外的 `.exe`、跳过除 `llama-server-impl.dll` 外的 `*-impl.dll`），再整体替换 `dest`。
  - 同 `group` 的条目安装成功后，从 `installed.json` 去掉同组其他条目。
  - `source == "auto"`：先用 `huggingface`；连接异常，或开始后 10 秒内平均速度低于 200 KB/s，改用 `mirror` 从当前断点继续。
  - 写文件出错（`OSError`）→ `item_failed(id, "download.error.disk")`，继续下一项。

- [ ] **Step 1:** 写 `tests/test_downloads.py`，用一个假的 opener（按 URL 返回内存字节，可配置“读到第 N 字节抛异常”“返回 200 不支持 Range”“很慢”）和假时钟。用 `qtbot` 不可用，所以等待信号用 `QCoreApplication.processEvents()` 循环加超时（参照 `tests/test_window_rewrite.py` 的 `settle`）。测试：
  - `test_downloads_verifies_and_installs`：两项依次 `installed`，文件内容正确，`installed.json` 含两项，`progress` 最后一次 `done == total`。
  - `test_resumes_from_partial_file`：预先写好前一半到 `.part`，断言 opener 收到 `Range: bytes=<一半>-`，最终文件正确。
  - `test_interrupted_download_is_not_installed`：opener 读到一半抛 `ConnectionError` → `failed`，`dest` 不存在，`.part` 保留以便续传。
  - `test_hash_mismatch_discards_file`：内容与 sha256 不符 → `item_failed(..., "download.error.hash")`，`.part` 与 `dest` 都不存在。
  - `test_write_error_fails_item`：让目标目录是一个文件（无法创建）→ `download.error.disk`，后续条目仍会下载。
  - `test_auto_switches_to_mirror_when_slow`：huggingface 地址很慢（假时钟推进 10 秒只给 1 MB），之后的请求打到 `hf-mirror.com` 且带 `Range`。
  - `test_cancel_removes_partial_file`
  - `test_zip_install_keeps_only_server_files_and_replaces_other_variant`：zip 里有 `llama-server.exe`、`llama-cli.exe`、`ggml.dll`、`llama-cli-impl.dll` → 只留 `llama-server.exe`、`ggml.dll`；之前 `installed.json` 里的同组条目被移除。
- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现 `DownloadManager`（`QThread` 或 `threading.Thread` + 信号均可；读块大小约 1 MB，进度信号限频约每 0.2 秒一次）。
- [ ] **Step 4:** 运行，预期 PASS。
- [ ] **Step 5:** 提交 `Add a resumable, verified background downloader`。

---

### Task 5: 下载面板控件

**Files:**
- Create: `voxflow/download_panel.py`
- Modify: `voxflow/settings_widgets.py`（新增 `SegmentedControl`、`ProgressBar` 的主题化画法，如需要）、`voxflow/settings_theme.py`（新对象名的样式）、`voxflow/i18n.py`
- Test: `tests/test_download_panel.py`

**Interfaces:**
- Consumes: Task 3 `fetch_catalog`、`installed_ids`、`SOURCES`；Task 4 `DownloadManager`。
- Produces: `class DownloadPanel(QWidget)`，构造参数 `(settings: QSettings, manager: DownloadManager, fetch=fetch_catalog, has_nvidia=has_nvidia_gpu, compact: bool = False)`。
  - 属性：`source_control`（三段：`auto` / `huggingface` / `mirror`，保存到 `downloads/source`）、`load_button`、`download_button`、`rows: dict[str, ItemRow]`（每行有 `checkbox`、`progress`、`status_label`、`cancel_button`）、`notice`（如“使用内置列表”）。
  - 方法：`load()`、`preselect(ids: list[str])`、`selected_ids() -> list[str]`。
  - 信号：`installed(str item_id)`（manager 的 `item_state` 为 `"installed"` 时转发）。
  - `has_nvidia_gpu() -> bool` 放在 `voxflow/download_panel.py`：用 `ctypes` 调 `EnumDisplayDevicesW`，任一设备名含 `NVIDIA` 即为 True。
  - 规则：已安装的行勾选框禁用并显示“已安装”；`group` 相同的条目勾选互斥；`needs_nvidia` 且无 NVIDIA 时禁用并显示“需要 NVIDIA 显卡”；底部显示“已选 N 项 · 共 X GB”；下载中每行显示进度条、`68% · 836 MB / 1.2 GB · 9.1 MB/s · 约 40 秒`、排队中显示“排队中”；底部“全部取消”和“可以关闭窗口，下载会在后台继续”。`compact=True`（教程用）时隐藏说明文字、行高更紧凑。
  - 下载源一行在列表最上面，单独成行，下面一行说明文字（照设计草图第 3 版）。

- [ ] **Step 1:** 写 `tests/test_download_panel.py`（假 fetch 返回固定清单，假 manager 记录调用并可手动发信号）：
  - `test_load_lists_items_and_marks_installed`
  - `test_variants_in_same_group_are_exclusive`：勾 `llama-cuda` 后 `llama-vulkan` 自动取消。
  - `test_nvidia_build_disabled_without_nvidia_gpu`
  - `test_download_selected_passes_items_and_source`：选“国内镜像”，勾两项，点下载 → manager 收到这两项与 `"mirror"`；`downloads/source == "mirror"`。
  - `test_progress_text_shows_percent_size_speed_and_eta`
  - `test_offline_list_shows_notice`：fetch 返回 `(builtin, False)` → `notice` 可见且文字为“无法连接，使用内置列表”。
- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现。
- [ ] **Step 4:** 运行，预期 PASS；浅色、深色各截图一张检查。
- [ ] **Step 5:** 提交 `Add the download panel shared by settings and the tutorial`。

---

### Task 6: 设置页与缺少组件时的提示

**Files:**
- Modify: `voxflow/settings_window.py`（智能编辑页：“已安装的模型”区加删除按钮，下方嵌入 `DownloadPanel`；关于页加“重新开始教程”按钮）、`voxflow/window.py`（ASR 缺失提示、下载完成后启动语音进程）、`voxflow/smart_editing.py`（模型缺失状态带“去下载”）、`voxflow/__main__.py`（创建唯一的 `DownloadManager`；全部完成时托盘气泡）、`voxflow/i18n.py`、`voxflow/ui_icons.py`（如需下载图标）
- Test: `tests/test_settings_downloads.py`、`tests/test_window.py`

**Interfaces:**
- Consumes: Task 4 `DownloadManager`、Task 5 `DownloadPanel`。
- Produces:
  - `SettingsWindow(settings, downloads: DownloadManager | None = None)`；`SettingsWindow.download_panel`、`SettingsWindow.show_downloads()`（切到智能编辑页并滚动到下载区）、`SettingsWindow.restart_tutorial_button`、信号 `tutorial_requested = Signal()`。
  - `VoxFlowWindow(..., downloads: DownloadManager | None = None)`；`VoxFlowWindow.start_speech_worker()`（公开现有的 `_start_worker`；已在运行时什么都不做）。
  - 新状态键：`status.asr_needed`（“需要先下载语音识别模型 · 点击下载”，点击状态文字打开 `show_downloads()`）；智能编辑模型状态 `model.not_installed`（“未安装 · 去下载”）。

- [ ] **Step 1:** 写测试：
  - `test_missing_speech_model_points_to_downloads`：`model_dir` 指向空目录 → 状态为 `status.asr_needed`；点状态 → 设置窗口可见且当前页为智能编辑。
  - `test_speech_worker_starts_after_model_installed`：manager 发 `item_state("asr-sensevoice", "installed")` → 调用了 `start_speech_worker`（用 monkeypatch 记录）。
  - `test_deleting_model_in_use_switches_or_disables`：已安装 Q8（使用中）和 Q4，删除 Q8 → `rewrite/model_path` 指向 Q4；再删除 Q4 → 智能编辑状态为 `model.not_installed`，不报错。
  - `test_about_restart_tutorial_emits_signal`
- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现。删除按钮只对数据目录 `runtime/models/` 里由下载器安装（`installed.json` 有记录）的模型显示。下载器对一个改写模型发出 `item_state(id, "installed")` 且当前没有可用模型时，自动设为当前模型并 `rewrite_changed.emit()`。
- [ ] **Step 4:** 运行全部测试，预期 PASS。
- [ ] **Step 5:** 提交 `Manage downloads from settings and point to them when components are missing`。

---

### Task 7: 新手教程

**Files:**
- Create: `voxflow/onboarding.py`、`voxflow/mic_meter.py`
- Modify: `voxflow/__main__.py`（首次启动显示；关于页信号打开）、`voxflow/i18n.py`
- Test: `tests/test_onboarding.py`

**Interfaces:**
- Consumes: Task 2 `color_theme_changed` / `saved_color_theme`；Task 5 `DownloadPanel(compact=True)`；Task 6 `tutorial_requested`；`hotkeys.saved`。
- Produces:
  - `class MicMeter(QObject)`：`start(device_id)`、`stop()`、信号 `level(float)`（0–1，按 RMS 计算，约每 50 ms 一次）；只在内存里算，不保存音频。`stream_factory` 可注入（默认 `sounddevice.InputStream`）。
  - `class OnboardingWindow(QWidget)`，构造参数 `(settings, settings_window: SettingsWindow, downloads: DownloadManager, meter: MicMeter | None = None)`；属性 `steps: QStackedWidget`、`next_button`、`back_button`、`skip_button`；信号 `finished()`。
  - `should_show_onboarding(settings) -> bool`：`onboarding/done` 不为真时返回 True。
  - 完成或跳过时写 `onboarding/done = true`。
- 6 步内容照设计文档 §6.4。第 1、2、3 步直接操作设置窗口里已有的控件对应的设置（语言 `ui/language`、颜色模式 `ui/theme`、配色主题 `ui/color_theme`、麦克风），并与设置窗口保持同步（改完设置窗口里也能看到）。第 2 步右侧画一个缩小的浮层预览（背景柔光 + 胶囊），随主题实时变化。第 4 步嵌入 `DownloadPanel(compact=True)`，打开时自动 `load()` 并 `preselect(["asr-sensevoice", "llama-vulkan", "rewrite-v4-q8"])`，不会自动开始下载。第 5 步显示当前录音快捷键（`hotkeys.saved(settings, "record").text`），语音模型未安装时提示“下载完成后即可试用”。

- [ ] **Step 1:** 写 `tests/test_onboarding.py`：
  - `test_shows_on_first_run_only`：新 INI → `should_show_onboarding` 为 True；完成后为 False。
  - `test_walks_six_steps_and_marks_done`：连续点 `next_button` 到最后一步，按钮文字变为“开始使用”，再点 → `finished` 发出且 `onboarding/done`。
  - `test_skip_marks_done`
  - `test_language_step_switches_tutorial_language`：选 English → 下一步按钮文字为 “Next”。
  - `test_theme_step_updates_settings_window`：选 `amber` → `settings_window.color_theme_buttons["amber"]` 处于选中状态，`ui/color_theme == "amber"`。
  - `test_download_step_preselects_but_does_not_start`：进入第 4 步后 `selected_ids()` 为上述三项，假 manager 没有收到 `start`。
  - `test_mic_meter_reports_level_without_saving_audio`：假 stream 推入一段正弦波 → `level` > 0；断言没有写任何文件（`tmp_path` 下为空）。
- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现。窗口用 `settings_theme.stylesheet` 并响应 `color_theme_changed` 与颜色模式变化；尺寸约 720×520；底部左“跳过”，右“上一步 / 下一步”；顶部 6 个小圆点表示进度。
- [ ] **Step 4:** 运行全部测试，预期 PASS；中英文、浅深色各截图检查第 2、4、5 步。
- [ ] **Step 5:** 提交 `Add the first-run tutorial`。

---

### Task 8: 发布文件、只含本体的安装包与文档

**Files:**
- Create: `packaging/publish_runtime.py`
- Modify: `packaging/build.py`（不再拷贝 `models/`、`runtime/llama.cpp`、`runtime/models`、`THIRD_PARTY.txt` 中相应说明调整）、`packaging/voxflow.iss`（去掉模型与运行组件的 `[Files]`；卸载询问是否删除 `{localappdata}\VoxFlow`，默认“否”）、`voxflow/assets/catalog.json`（回填哈希）、`README.md`、`HANDOFF.md`、`training/rewrite/model_card.md`（文件表加 `runtime/`）
- Test: `tests/test_catalog.py`（内置清单哈希完整性）

**Interfaces:**
- Consumes: Task 3 的清单格式。
- Produces: Hugging Face `ThermalEX/voxflow-rewrite` 仓库里的 `runtime/llama-b11596-bin-win-vulkan-x64.zip`、`runtime/llama-b11596-bin-win-cuda-12.4-x64.zip`、`runtime/cudart-llama-bin-win-cuda-12.4-x64.zip`、`runtime/LICENSE-llama.cpp`、`catalog.json`，以及与之一致的内置清单。

- [ ] **Step 1:** 在 `tests/test_catalog.py` 加 `test_builtin_catalog_is_complete`：每个文件的 `size > 0` 且 `sha256` 为 64 位十六进制；`file_url` 不含空段。运行，预期 FAIL（`tokens.txt`、`LICENSE`、llama zip 尚未回填）。
- [ ] **Step 2:** 写 `packaging/publish_runtime.py`：用 `gh release download b11596 -R ggml-org/llama.cpp` 下载三个 zip 到一个新的空临时目录；下载语音模型仓库在固定提交下的 `tokens.txt`、`LICENSE`；计算全部大小与 sha256；用 `huggingface_hub.HfApi.upload_file` 上传 zip 与 LICENSE 到 `runtime/`；生成并上传 `catalog.json`；同时写入 `voxflow/assets/catalog.json`。上传需要用户已 `hf auth login`（已完成）。
- [ ] **Step 3:** 运行发布脚本；运行 Step 1 的测试，预期 PASS。用 `curl -sI` 检查 `huggingface.co` 与 `hf-mirror.com` 上新文件都返回 200。
- [ ] **Step 4:** 修改 `build.py` 与 `voxflow.iss`。卸载询问用 `[Code]` 的 `CurUninstallStepChanged(usPostUninstall)` + `MsgBox(..., mbConfirmation, MB_YESNO or MB_DEFBUTTON2)`，中英文提示放 `[CustomMessages]`。
- [ ] **Step 5:** 运行 `.\.venv\Scripts\python.exe packaging\build.py`，确认安装包体积（预计 100–200 MB）。在新的空 `LOCALAPPDATA` 下验证：`$env:LOCALAPPDATA` 指向临时目录后静默安装、启动 → 教程出现；在教程里真实下载三项（国内镜像与自动各试一次）；下载完成后录音识别与智能编辑可用；卸载时选择删除 → 临时数据目录被删。记录哪些步骤没能自动验证。
- [ ] **Step 6:** 更新 README（安装与首次使用、在软件里下载模型）、HANDOFF（数据目录、清单、下载器、教程、主题）、模型说明的文件表；把新的 `catalog.json` 也上传到 Hugging Face（发布脚本已做则跳过）。
- [ ] **Step 7:** 运行全部测试，提交 `Ship an app-only installer and publish runtime files for in-app download`。
