"""Capture overlay states for the A2 storyboards with the real local rewrite model.

Needs runtime/llama.cpp and runtime/models/voxflow-rewrite-v4-q8_0.gguf. Run from the repository root:
    $env:QT_QPA_PLATFORM='offscreen'; $env:QT_QPA_FONTDIR='C:\Windows\Fonts'
    .\.venv\Scripts\python.exe docs\a2\scripts\capture.py <shots-folder>
    .\.venv\Scripts\python.exe docs\a2\scripts\compose.py <shots-folder> docs\a2
Model outputs are not edited; the log.json written next to the shots records them and their latency.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from voxflow import i18n
from voxflow.memory_store import MemoryStore
from voxflow.rewriter import RewriteClient, RewriteConfig
from voxflow.smart_editing import default_server_factory
from voxflow.window import VoxFlowWindow


class RecordingOutput:
    """Stands in for pasting into another app, so the capture never types into the desktop."""

    def __init__(self):
        self.calls = []

    def remember_foreground(self, _own_hwnd):
        pass

    def paste(self, text):
        self.calls.append(text)
        return True

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
log = {}
app = QApplication.instance() or QApplication([])
i18n.set_language("en")

config = RewriteConfig(enabled=True, provider="local", model_path="runtime/models/voxflow-rewrite-v4-q8_0.gguf")
server = default_server_factory(config)
server.start()
deadline = time.monotonic() + 90
while not server.ready() and not server.failed and time.monotonic() < deadline:
    time.sleep(0.2)
assert server.ready(), server.failed


class TimedClient(RewriteClient):
    def _chat(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            return super()._chat(*args, **kwargs)
        finally:
            log.setdefault("latency", []).append(round(time.perf_counter() - start, 3))


client = TimedClient(config.base_url, config.model_name)


def make(review=False, memory=False, store=None):
    tmp = Path(tempfile.mkdtemp())
    settings = QSettings(str(tmp / "voxflow.ini"), QSettings.Format.IniFormat)
    settings.setValue("ui/language", "en")
    settings.setValue("memory/enabled", memory)
    RewriteConfig(enabled=True, provider="local", model_path=config.model_path,
                  review=review).save(settings)
    window = VoxFlowWindow(model_dir=tmp, start_worker=False, settings=settings, text_output=RecordingOutput(),
                           rewrite_client=client, memory_store=store)
    window.model_ready = True
    window.reveal()
    window._background_progress = 1.0
    window.smart.suggest_delay_ms = 0
    return window


def pump(window, condition=lambda: False, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window._poll()
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def settle_size(window):
    for _ in range(30):
        app.processEvents()
    if window._result_animation.state() == window._result_animation.State.Running:
        window._result_animation.setCurrentTime(window._result_animation.duration())
    app.processEvents()


def shot(window, name):
    settle_size(window)
    window.grab().save(str(OUT / f"{name}.png"))


def buttons(window):
    return [b.text() for b in window.smart.suggestion_buttons if b.isVisible()]


# Storyboard 1: dictate, watch the edit, inspect it -----------------------------------------------
SAID_1 = sys.argv[2] if len(sys.argv) > 2 else (
    "um so can we move the design review to Wednesday, no sorry, Thursday at 3pm, "
    "and please send the slides to Zhang San before that")
w = make()
w.apply_transcript("partial", SAID_1[: len(SAID_1) * 2 // 3])
w._background_progress = 1.0
w._background_revealing = False
w._sync_content_visibility()
shot(w, "sb1_1_recording")
w.apply_transcript("final", SAID_1)
anim = w.smart.animation
pump(w, lambda: anim.state() == anim.State.Running or w._status[0] == "status.no_edits")
log["sb1_status_after_clean"] = w._status[0]
if anim.state() == anim.State.Running:
    anim.setCurrentTime(anim.duration() // 2)
    app.processEvents()
    w.window().grab().save(str(OUT / "sb1_2_animating.png"))
    anim.setCurrentTime(anim.duration())
    pump(w, lambda: anim.state() != anim.State.Running, 5)
pump(w, lambda: len(buttons(w)) > 0, timeout=20)
log["sb1_polished"] = w.transcript.toPlainText()
log["sb1_suggestions"] = [(s["label"], s["text"]) for s in w.smart._suggestions]
shot(w, "sb1_3_polished")
w.smart.undo_button.hovered.emit(True)
shot(w, "sb1_4_hover_original")
w.smart.undo_button.hovered.emit(False)
w.close()

# Storyboard 2: an instruction meant for someone else is executed; catch it and undo, or review ------
SAID_2 = "告诉小李，第一句删了吧，太啰嗦，然后周五前交给我。"
w = make()
w.apply_transcript("final", SAID_2)
anim = w.smart.animation
pump(w, lambda: anim.state() == anim.State.Running)
anim.setCurrentTime(anim.duration())
pump(w, lambda: anim.state() != anim.State.Running, 5)
log["sb2_polished"] = w.transcript.toPlainText()
shot(w, "sb2_1_misread")
w.smart.undo_button.hovered.emit(True)
shot(w, "sb2_2_hover_original")
w.smart.undo_button.hovered.emit(False)
w.smart.undo_button.click()
shot(w, "sb2_3_undone")
log["sb2_after_undo"] = w.smart.current_text()
w.close()

SAID_2B = ("um tell Zhang San the deadline is Friday, no wait, Monday, and the report should be shorter, "
           "like, two pages.")
w = make(review=True)
w.apply_transcript("final", SAID_2B)
pump(w, lambda: w.smart.reviewing or w._status[0] == "status.no_edits")
log["sb2b_hunks"] = [h for h in (w.smart.review_hunks or []) if h[0] == "change"]
if w.smart.reviewing:
    shot(w, "sb2_4_review")
    changes = [h for h in w.smart.review_hunks if h[0] == "change"]
    target = next((i for i, h in enumerate(changes) if "shorter" in h[1]), len(changes) - 1)
    w.smart.toggle_change(target)
    shot(w, "sb2_5_review_kept_word")
    log["sb2b_kept_text"] = w.smart.current_text()
w.close()

# Storyboard 3: remember, inspect, fill in -------------------------------------------------------
tmp = Path(tempfile.mkdtemp())
store = MemoryStore(tmp / "memory.db")
w = make(memory=True, store=store)
w.apply_transcript("final", "Remember the design review is on Thursday at 3 pm in room 204.")
hl = w.smart.highlight
hl.pause()
hl.setCurrentTime(hl.duration() // 2)
w.smart._render_highlight(hl.currentValue())
shot(w, "sb3_1_glow")
hl.setCurrentTime(hl.duration())
hl.stop()
w.smart._finish_highlight()
pump(w, lambda: w.smart.future is None and w.smart.animation.state() != w.smart.animation.State.Running, 20)
shot(w, "sb3_2_remembered")
w._confirm_text()
log["sb3_entries"] = [(e.content, e.keep, e.source) for e in store.entries()]
sw = w.settings_window
sw.resize(980, 640)
sw.pages.setCurrentIndex(3)
sw.show()
for _ in range(30):
    app.processEvents()
sw.grab().save(str(OUT / "sb3_3_settings_page.png"))
sw.memory_page.show_memories()
dialog = sw.memory_page.memories_dialog
dialog.resize(640, 360)
for _ in range(30):
    app.processEvents()
dialog.grab().save(str(OUT / "sb3_3_memory_page.png"))
dialog.hide()
sw.hide()
w.reveal()
w.apply_transcript("final", "Please remind everyone to come to the design review.")
pump(w, lambda: any(b.text() == "Fill from memory" and b.isVisible() for b in w.smart.suggestion_buttons), 30)
log["sb3_fill_suggestions"] = [(s["label"], s["text"]) for s in w.smart._suggestions]
shot(w, "sb3_4_fill_offered")
fill = next((i for i, s in enumerate(w.smart._suggestions) if s["label"] == "Fill from memory"), None)
if fill is not None:
    w.smart.suggestion_buttons[fill].click()
    shot(w, "sb3_5_filled")
log["sb3_final"] = w.transcript.toPlainText()
w.close()

server.stop()
(OUT / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(log, ensure_ascii=False, indent=1))
