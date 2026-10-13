# 智能编辑接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把口语改写模型接入 VoxFlow 浮层：最终识别结果经改写后播放一次修改动画，悬停“撤回修改”看原文，浮动显示建议；模型经 OpenAI 兼容接口调用，设置里可换，本地模型服务由 VoxFlow 自动启动。

**Architecture:** 纯逻辑放在小模块里（`edit_diff`、`rewriter`、`local_server`），各自单测；`training/rewrite/serve.py` 在 WSL 里提供接口；`settings_window` 新增 Smart editing 页；`window` 用后台线程调用改写并由 `_poll` 收取结果。

**Tech Stack:** Python 3.12、PySide6 6.10.1、标准库 urllib / http.server / difflib / subprocess；WSL 端沿用训练环境（Unsloth、transformers v5）。不新增依赖。

**Spec:** `docs/superpowers/specs/2026-10-13-smart-editing-integration-design.md`

## Global Constraints

- 界面文案英文（与现有 UI 一致）；识别和改写结果保留原语种。
- 智能编辑默认关闭；关闭或任何失败时行为与现在完全一致（原文可确认上屏）。
- 只改写最终结果，不改写实时草稿；新录音或关闭浮层时丢弃过期结果。
- 本地服务地址 `http://127.0.0.1:8765/v1`，模型名 `voxflow-rewrite`；超时：清理 15 s、建议 20 s、测试连接 3 s。
- 系统提示唯一来源 `voxflow/rewrite_prompts.py`。
- 提交信息不得包含任何 Claude 署名；只 `git add` 本任务列出的文件。
- Windows 测试命令：`$env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`。

## Review Focus

- 改写结果返回时用户已经开始编辑或开始新录音：不得覆盖用户内容（Task 6 测试 `test_late_rewrite_does_not_overwrite_edits_or_new_sessions`）。
- 自定义接口返回带 ``` 代码块或多余文字的建议 JSON：应解析出数组或视为无建议，不能崩溃（Task 3 测试 `test_suggest_tolerates_code_fences_and_garbage`）。
- WSL 或适配器不存在导致本地服务启动即退出：不能反复无限拉起，状态栏给出原因，原文照常可用（Task 4 测试 `test_server_that_exits_is_reported_not_respawned`）。
- 撤回悬停预览时点击确认：上屏的是当前文字而不是灰色原文预览（Task 6 测试 `test_confirm_during_hover_preview_pastes_current_text`）。
- 包含换行的改写结果（口述格式列表）在动画与撤回间切换后保持换行（Task 2/6 测试中的多行用例）。

---

### Task 1: 共享系统提示

**Files:**
- Create: `voxflow/rewrite_prompts.py`（内容为现 `training/rewrite/prompts.py` 的两个常量）
- Modify: `training/rewrite/prompts.py` → `from voxflow.rewrite_prompts import CLEAN_SYSTEM_PROMPT, SUGGEST_SYSTEM_PROMPT`
- Test: `tests/test_rewrite_prompts.py`

**Interfaces:** Produces `voxflow.rewrite_prompts.CLEAN_SYSTEM_PROMPT`, `SUGGEST_SYSTEM_PROMPT`。

- [ ] Step 1: 写失败测试：

```python
from training.rewrite import prompts as training_prompts
from voxflow import rewrite_prompts


def test_app_and_training_share_the_same_prompts():
    assert training_prompts.CLEAN_SYSTEM_PROMPT is rewrite_prompts.CLEAN_SYSTEM_PROMPT
    assert training_prompts.SUGGEST_SYSTEM_PROMPT is rewrite_prompts.SUGGEST_SYSTEM_PROMPT
```

- [ ] Step 2: 运行确认失败（`ModuleNotFoundError: voxflow.rewrite_prompts`）。
- [ ] Step 3: 移动常量，`training/rewrite/prompts.py` 改为重新导出（保留模块文档字符串）。
- [ ] Step 4: 运行全部 rewrite 测试与构建：`.\.venv\Scripts\python.exe -m training.rewrite.build_dataset` 输出与之前条数一致。
- [ ] Step 5: Commit `Share rewrite prompts between app and training`。

---

### Task 2: 修改痕迹与动画帧（`voxflow/edit_diff.py`）

**Interfaces — Produces:**
- `diff_segments(old: str, new: str) -> list[tuple[str, str]]`，kind ∈ `same | removed | added`，中文按字、英文按词与空白切分。
- `similarity(old: str, new: str) -> float`（0–1）。
- `LARGE_CHANGE_SIMILARITY = 0.5`
- `frame_html(old: str, new: str, progress: float, text_rgb, removed_rgb, added_rgb) -> str`：progress 0→1；小改动时删除部分带删除线、透明度 1−p，新增部分透明度 p；大改动时前半段旧文淡出、后半段新文淡入；保留换行和空格（`white-space: pre-wrap`），HTML 转义。

- [ ] Step 1: 写失败测试 `tests/test_edit_diff.py`：

```python
from voxflow import edit_diff

WHITE, GRAY, BLUE = (243, 247, 255), (150, 160, 175), (140, 190, 255)


def test_chinese_diff_is_per_character():
    assert edit_diff.diff_segments("额，我明天请个假啊。", "我明天请个假。") == [
        ("removed", "额，"), ("same", "我明天请个假"), ("removed", "啊"), ("same", "。")]


def test_english_diff_is_per_word():
    segments = edit_diff.diff_segments("I need eggs, bread, and cheese", "I need eggs and bread.")
    assert ("same", "I need eggs") in segments
    assert any(kind == "removed" and "cheese" in text for kind, text in segments)


def test_similarity_separates_light_edits_from_rewrites():
    assert edit_diff.similarity("额，我明天请个假啊。", "我明天请个假。") > edit_diff.LARGE_CHANGE_SIMILARITY
    assert edit_diff.similarity("明天下午开会", "There's a meeting tomorrow afternoon.") < edit_diff.LARGE_CHANGE_SIMILARITY


def test_light_edit_frames_strike_then_fade_removed_text():
    start = edit_diff.frame_html("额，我请假。", "我请假。", 0.0, WHITE, GRAY, BLUE)
    end = edit_diff.frame_html("额，我请假。", "我请假。", 1.0, WHITE, GRAY, BLUE)
    assert "line-through" in start and "额，" in start and "rgba(150,160,175,1.00)" in start
    assert "rgba(150,160,175,0.00)" in end


def test_rewrite_frames_crossfade_and_escape_html():
    early = edit_diff.frame_html("明天<开会>", "Meeting <tomorrow>.", 0.1, WHITE, GRAY, BLUE)
    late = edit_diff.frame_html("明天<开会>", "Meeting <tomorrow>.", 0.9, WHITE, GRAY, BLUE)
    assert "明天&lt;开会&gt;" in early and "Meeting" not in early
    assert "Meeting &lt;tomorrow&gt;." in late and "明天" not in late


def test_frames_keep_line_breaks():
    html = edit_diff.frame_html("待办，第一，开会", "待办：\n1. 开会", 1.0, WHITE, GRAY, BLUE)
    assert "pre-wrap" in html and "\n" in html
```

- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 实现：

```python
"""Diff a spoken transcript against its rewrite and render the one-time edit animation."""

import html
import re
from difflib import SequenceMatcher

LARGE_CHANGE_SIMILARITY = 0.5
_TOKEN = re.compile(r"[A-Za-z0-9']+|\s+|.", re.S)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def diff_segments(old: str, new: str) -> list[tuple[str, str]]:
    a, b = _tokens(old), _tokens(new)
    segments: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            segments.append(("same", "".join(a[i1:i2])))
            continue
        if i2 > i1:
            segments.append(("removed", "".join(a[i1:i2])))
        if j2 > j1:
            segments.append(("added", "".join(b[j1:j2])))
    return segments


def similarity(old: str, new: str) -> float:
    return SequenceMatcher(None, _tokens(old), _tokens(new), autojunk=False).ratio()


def _span(text: str, rgb, alpha: float, strike: bool = False) -> str:
    decoration = "text-decoration: line-through;" if strike else ""
    return (f'<span style="color: rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha:.2f});{decoration}">'
            f"{html.escape(text)}</span>")


def frame_html(old: str, new: str, progress: float, text_rgb, removed_rgb, added_rgb) -> str:
    progress = min(1.0, max(0.0, progress))
    if similarity(old, new) < LARGE_CHANGE_SIMILARITY:
        body = (_span(old, text_rgb, 1 - progress * 2) if progress < 0.5
                else _span(new, text_rgb, progress * 2 - 1))
    else:
        parts = []
        for kind, text in diff_segments(old, new):
            if kind == "same":
                parts.append(_span(text, text_rgb, 1.0))
            elif kind == "removed":
                parts.append(_span(text, removed_rgb, 1 - progress, strike=True))
            else:
                parts.append(_span(text, added_rgb, progress))
        body = "".join(parts)
    return f'<div style="white-space: pre-wrap;">{body}</div>'
```

- [ ] Step 4: 运行通过。
- [ ] Step 5: Commit `Add edit diff and animation frames`。

---

### Task 3: 改写客户端与配置（`voxflow/rewriter.py`）

**Interfaces — Produces:**
- `LOCAL_ENDPOINT = "http://127.0.0.1:8765/v1"`、`LOCAL_MODEL = "voxflow-rewrite"`
- `@dataclass(frozen=True) RewriteConfig(enabled=False, provider="local", endpoint="", model="", api_key="", wsl_distro="", environment="~/voxflow-train", adapter="training/rewrite/runs/qwen3.5-2b/adapter")`，`base_url`/`model_name` 属性（local 时返回本地常量），`from_settings(settings)`、`save(settings)`（键前缀 `rewrite/`）。
- `class RewriteError(Exception)`
- `RewriteClient(base_url, model, api_key="", opener=urllib.request.urlopen)`：`clean(text) -> str`、`suggest(text) -> list[dict]`、`check(timeout=3) -> str`。

- [ ] Step 1: 写失败测试 `tests/test_rewriter.py`（用本地 `ThreadingHTTPServer` 假服务记录请求、按路径返回固定响应）：
  - `test_clean_posts_prompt_and_returns_text`：断言请求体 model、messages[0] 为 `CLEAN_SYSTEM_PROMPT`、messages[1] 为原文、`temperature == 0`，Bearer 头在给定 key 时存在；返回值去首尾空白。
  - `test_suggest_parses_valid_items_only`：返回 `[{"label":"更正式","text":"…"},{"label":3},{"label":"同","text":"<原文>"}]` → 只保留第一项。
  - `test_suggest_tolerates_code_fences_and_garbage`：```` ```json\n[...]\n``` ```` 能解析；`"抱歉"` → `[]`。
  - `test_errors_raise_rewrite_error`：500、连接拒绝、超时、空内容 → `RewriteError`。
  - `test_check_lists_models`：`/models` 返回 `{"data":[{"id":"voxflow-rewrite"}]}` → `"voxflow-rewrite"`。
  - `test_config_round_trip_and_local_defaults`：INI QSettings 保存/读取；local 时 `base_url == LOCAL_ENDPOINT`。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 实现（`urllib.request.Request`，JSON 体，`Authorization: Bearer` 可选；`clean` 超时 15 s，`suggest` 20 s；解析建议时先剥离 ``` 围栏，再取第一个 `[` 到最后一个 `]`；每项需 label/text 为非空字符串且 text 不等于原文，最多 3 项；`URLError`/`TimeoutError`/`HTTPError`/JSON 错误统一转 `RewriteError`）。
- [ ] Step 4: 运行通过。
- [ ] Step 5: Commit `Add OpenAI-compatible rewrite client and settings`。

---

### Task 4: 本地模型服务与进程管理

**Files:** Create `training/rewrite/serve.py`、`voxflow/local_server.py`；Test `tests/test_rewrite_serve.py`、`tests/test_local_server.py`。

**Interfaces — Produces:**
- `serve.make_handler(generate: Callable[[list[dict], int], str], model_name: str) -> type[BaseHTTPRequestHandler]`（顶层只依赖标准库；`main()` 内才导入 unsloth）。`main()` 参数 `--model --adapter --host 127.0.0.1 --port 8765 --name voxflow-rewrite`；就绪后打印 `READY`；stdin EOF 后关闭服务退出。
- `local_server.windows_to_wsl_path(path) -> str`；`LocalRewriteServer.wsl_command(repo_root, distro, environment, adapter, port=8765) -> list[str]`；`LocalRewriteServer(command, health_url, log_path, popen=subprocess.Popen, opener=urlopen, clock=time.monotonic)`：`start()`、`ready() -> bool`（健康检查每 2 s 最多一次，成功后缓存）、`failed -> str | None`（进程已退出时给出原因，不自动重启）、`stop()`（关 stdin，5 s 后 terminate，再 kill）。

- [ ] Step 1: 写失败测试：
  - serve：用 `make_handler(lambda messages, max_tokens: "整理后")` 起服务，`GET /v1/models` 返回模型名；`POST /v1/chat/completions` 返回 `choices[0].message.content == "整理后"` 且 generate 收到 messages；非法 JSON → 400。
  - local_server：`windows_to_wsl_path(Path("F:/project/VoxFlow")) == "/mnt/f/project/VoxFlow"`；`wsl_command` 含 `-d <distro>`（为空时不含）、`source ~/voxflow-train/bin/activate`、`--adapter` 与端口；假 popen 下 `start()` 只拉起一次、Windows 时带 `CREATE_NO_WINDOW`；健康检查节流；`test_server_that_exits_is_reported_not_respawned`（假进程 `poll()` 返回 1 → `failed` 有值，再 `start()` 不再拉起）；`stop()` 关闭 stdin 并在超时后 terminate。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 实现。`serve.main` 复用 `training.rewrite.train.render_prompt` 与贪心生成（`max_new_tokens` 取请求的 `max_tokens`，上限 512），生成串行加锁。服务日志写到 `training/rewrite/runs/serve.log`。
- [ ] Step 4: 运行通过；在 WSL 手动 `python -m training.rewrite.serve --adapter training/rewrite/runs/qwen3.5-2b/adapter` 后 `curl` 两个接口验证。
- [ ] Step 5: Commit `Add local rewrite server and its process manager`。

---

### Task 5: Smart editing 设置页

**Files:** Modify `voxflow/settings_window.py`、`voxflow/ui_icons.py`；Create `voxflow/assets/icons/auto_fix_high.svg`（Material Symbols，同目录 LICENSE 覆盖，README 补来源）；Modify `pyproject.toml` 无需改（`*.svg` 已包含）；Test `tests/test_window.py` 或新文件 `tests/test_settings_rewrite.py`。

**Interfaces — Produces:** `SettingsWindow.rewrite_changed = Signal()`；控件 `rewrite_enabled`（QCheckBox）、`rewrite_provider`（combo，data `local|custom`）、`rewrite_endpoint`、`rewrite_model`、`rewrite_api_key`（密码）、`rewrite_distro`、`rewrite_environment`、`rewrite_adapter`、`rewrite_test_button`、`rewrite_status`（QLabel）；`set_rewrite_tester(callable[[RewriteConfig], str])` 由窗口注入（便于测试和复用客户端）。

- [ ] Step 1: 写失败测试：页面存在（分类第三项 “Smart editing”）；改动即保存到 QSettings 并发出 `rewrite_changed`；provider 切换时本地字段与自定义字段的可见性互斥；Test connection 调用注入的 tester，成功显示 “Connected · <model>”，异常显示错误文本。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 实现页面（复用 `_page`/`_field` 与现有样式；QLineEdit 加入样式表）。
- [ ] Step 4: 运行通过。
- [ ] Step 5: Commit `Add Smart editing settings page`。

---

### Task 6: 浮层接入

**Files:** Modify `voxflow/window.py`、`voxflow/overlay_widgets.py`（新增 `PillButton(QPushButton)`，带 `hovered = Signal(bool)`，半透明深色圆角样式与 `CircleIconButton` 协调）；Test `tests/test_window_rewrite.py`。

**Interfaces — Consumes:** Task 2/3/4 全部接口。**Produces:** `VoxFlowWindow(..., rewrite_client=None, local_server_factory=None)`；属性 `edit_bar`（含 `undo_button` 与最多 3 个建议按钮）、`_edit_animation`（QVariantAnimation，800 ms）、`original_text`、`edited_text`。

行为（按 spec §5）：
- `apply_transcript("final", text)` 非空时记录 `original_text`，若智能编辑可用（启用且客户端存在、本地服务 `ready()`），用单线程 `ThreadPoolExecutor` 提交 `clean`，状态 “Polishing…”。会话号 = `_recording_serial`。
- `_poll` 收取：会话号一致、mode 为 result、预览仍是 `original_text`（用户未编辑）才应用；结果与原文规范化后相同则不播动画，直接进入建议阶段。
- 动画：每帧 `transcript.setHtml(frame_html(...))`，结束 `setPlainText(edited_text)`、恢复对齐、`_expand_for_result()`，状态 “Polished · hover Undo edits to see the original”。
- `undo_button`：悬停 True 时把当前文字暂存并显示灰色原文（只读），False 时恢复；点击在原文与 `edited_text` 间切换并改按钮文字 Undo edits / Restore edits。确认上屏始终用暂存的当前文字。
- 建议：清理完成后提交 `suggest(edited_text)`；返回后显示按钮（文字为 label，tooltip 为 text）；点击采用：`edited_text = text` 并显示，撤回仍回到 `original_text`。
- 失败：状态 “Smart editing unavailable · kept the original”，`local_server.failed` 有值时显示其原因。
- `_discard_session()` 与 `_start_recording()` 清空编辑状态、隐藏 `edit_bar`；`_set_overlay_height` / `_expand_for_result` 计入 `edit_bar` 可见时的高度。
- 设置 `rewrite_changed` → 重新读取配置、重建客户端、按需启停本地服务；`closeEvent` 停止本地服务与线程池。

- [ ] Step 1: 写失败测试（假客户端同步返回；循环调用 `_poll()` + `processEvents()` 直到 future 完成；动画用 `setCurrentTime(800)` 结束）：
  - `test_final_text_is_polished_with_one_animation`
  - `test_hovering_undo_shows_original_and_click_toggles`
  - `test_suggestions_appear_and_apply`
  - `test_rewrite_failure_keeps_original`
  - `test_late_rewrite_does_not_overwrite_edits_or_new_sessions`
  - `test_confirm_during_hover_preview_pastes_current_text`
  - `test_disabled_smart_editing_changes_nothing`（不提交任何请求、无 edit_bar）
  - `test_multiline_rewrite_survives_undo_restore`
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 实现。
- [ ] Step 4: 运行全部测试通过。
- [ ] Step 5: Commit `Polish final transcripts with the rewrite model in the overlay`。

---

### Task 7: 收尾与端到端试用

**Files:** Modify `README.md`、`HANDOFF.md`。

- [ ] Step 1: README 增加 Smart editing 使用说明（开启方式、本地服务依赖 WSL 训练环境与适配器、自定义接口）；HANDOFF 第 3 节表格补 `rewriter.py`、`edit_diff.py`、`local_server.py`、`rewrite_prompts.py`，并说明数据流。
- [ ] Step 2: 全量测试。
- [ ] Step 3: 端到端：启动 `pythonw -m voxflow`，设置里开启 Smart editing（本地），等待服务就绪，口述含口气词、改口、“翻译成英文”各一句，观察动画、撤回悬停、建议与上屏；记录观察结果与延迟。
- [ ] Step 4: Commit `Document smart editing`。
