import threading
import time

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from voxflow.rewriter import RewriteConfig, RewriteError
from voxflow.window import VoxFlowWindow

ORIGINAL = "额，我明天请个假啊。"
POLISHED = "我明天请个假。"


class FakeClient:
    def __init__(self, clean=POLISHED, suggestions=(), fail=False, gate=None):
        self.clean_result = clean
        self.suggestions = list(suggestions)
        self.fail = fail
        self.gate = gate
        self.calls = []

    def clean(self, text):
        self.calls.append(("clean", text))
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail:
            raise RewriteError("model is down")
        return self.clean_result

    def suggest(self, text):
        self.calls.append(("suggest", text))
        return self.suggestions


class FakeServer:
    def __init__(self):
        self.is_ready = False
        self.failed = None
        self.problem = None
        self.started = self.stopped = 0

    def start(self):
        self.started += 1

    def ready(self):
        return self.is_ready and not self.failed

    def stop(self):
        self.stopped += 1


class RecordingOutput:
    def __init__(self):
        self.calls = []

    def remember_foreground(self, _own_hwnd):
        pass

    def paste(self, text):
        self.calls.append(text)
        return True


def make_window(tmp_path, client, enabled=True, provider="custom", server=None):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    RewriteConfig(enabled=enabled, provider=provider, endpoint="http://example.test/v1", model="m").save(settings)
    output = RecordingOutput()
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings, text_output=output,
                           rewrite_client=client,
                           local_server_factory=(lambda _config: server) if server is not None else None)
    window.model_ready = True
    window.reveal()
    window._background_progress = 1.0
    return app, window, output


def settle(app, window, condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        window._poll()
        app.processEvents()
        time.sleep(0.01)
    assert condition()


def polish(app, window):
    window.apply_transcript("final", ORIGINAL)
    animation = window.smart.animation
    settle(app, window, lambda: animation.state() == animation.State.Running)
    animation.setCurrentTime(animation.duration())
    app.processEvents()


def test_final_text_is_polished_with_one_animation(tmp_path):
    app, window, _output = make_window(tmp_path, FakeClient())
    window.apply_transcript("final", ORIGINAL)
    assert window.transcript.toPlainText() == ORIGINAL
    animation = window.smart.animation
    settle(app, window, lambda: animation.state() == animation.State.Running)
    animation.setCurrentTime(animation.duration() // 2)
    assert "line-through" in window.transcript.toHtml()
    animation.setCurrentTime(animation.duration())
    app.processEvents()
    assert window.transcript.toPlainText() == POLISHED
    assert "line-through" not in window.transcript.toHtml()
    assert not window.transcript.isReadOnly()
    assert window.smart.undo_button.isVisibleTo(window)
    assert "Polished" in window.status_label.text()
    assert window.smart.client.calls[0] == ("clean", ORIGINAL)
    window.close()


def test_hovering_undo_shows_original_and_click_toggles(tmp_path):
    app, window, _output = make_window(tmp_path, FakeClient())
    polish(app, window)
    undo = window.smart.undo_button
    undo.hovered.emit(True)
    assert window.transcript.toPlainText() == ORIGINAL and window.transcript.isReadOnly()
    undo.hovered.emit(False)
    assert window.transcript.toPlainText() == POLISHED and not window.transcript.isReadOnly()
    undo.click()
    assert window.transcript.toPlainText() == ORIGINAL and undo.text() == "Restore edits"
    undo.click()
    assert window.transcript.toPlainText() == POLISHED and undo.text() == "Undo edits"
    window.close()


def test_suggestions_appear_and_apply(tmp_path):
    client = FakeClient(suggestions=[{"label": "更正式", "text": "我明天需请假一天。"}])
    app, window, _output = make_window(tmp_path, client)
    polish(app, window)
    chip = window.smart.suggestion_buttons[0]
    settle(app, window, lambda: chip.isVisibleTo(window))
    assert chip.text() == "更正式" and chip.toolTip() == "我明天需请假一天。"
    assert not window.smart.suggestion_buttons[1].isVisibleTo(window)
    assert ("suggest", POLISHED) in client.calls
    chip.click()
    assert window.transcript.toPlainText() == "我明天需请假一天。"
    window.smart.undo_button.click()
    assert window.transcript.toPlainText() == ORIGINAL
    window.close()


def test_rewrite_failure_keeps_original(tmp_path):
    app, window, output = make_window(tmp_path, FakeClient(fail=True))
    window.apply_transcript("final", ORIGINAL)
    settle(app, window, lambda: "unavailable" in window.status_label.text())
    assert window.transcript.toPlainText() == ORIGINAL
    assert not window.smart.undo_button.isVisibleTo(window)
    window.confirm_button.click()
    assert output.calls == [ORIGINAL]
    window.close()


def test_late_rewrite_does_not_overwrite_edits_or_new_sessions(tmp_path):
    gate = threading.Event()
    app, window, _output = make_window(tmp_path, FakeClient(gate=gate))
    window.apply_transcript("final", ORIGINAL)
    window.transcript.setPlainText("我自己改过了")
    gate.set()
    settle(app, window, lambda: window.smart.future is None)
    assert window.transcript.toPlainText() == "我自己改过了"
    assert window.smart.animation.state() != window.smart.animation.State.Running

    gate.clear()
    window.apply_transcript("final", ORIGINAL)
    window.hide_overlay()
    gate.set()
    settle(app, window, lambda: window.smart.future is None)
    assert window.transcript.toPlainText() == ""
    assert window.mode == "idle"
    window.close()


def test_confirm_during_hover_preview_pastes_current_text(tmp_path):
    app, window, output = make_window(tmp_path, FakeClient())
    polish(app, window)
    window.smart.undo_button.hovered.emit(True)
    window.confirm_button.click()
    assert output.calls == [POLISHED]
    window.close()


def test_disabled_smart_editing_changes_nothing(tmp_path):
    client = FakeClient()
    app, window, _output = make_window(tmp_path, client, enabled=False)
    window.apply_transcript("final", ORIGINAL)
    for _ in range(10):
        window._poll()
        app.processEvents()
    assert client.calls == []
    assert window.transcript.toPlainText() == ORIGINAL
    assert not window.smart.undo_button.isVisibleTo(window)
    window.close()


def test_multiline_rewrite_survives_undo_restore(tmp_path):
    listed = "今天的待办：\n1. 开会\n2. 写周报"
    app, window, _output = make_window(tmp_path, FakeClient(clean=listed))
    polish(app, window)
    assert window.transcript.toPlainText() == listed
    window.smart.undo_button.click()
    window.smart.undo_button.click()
    assert window.transcript.toPlainText() == listed
    window.close()


def test_waits_for_the_local_server_then_polishes(tmp_path):
    server = FakeServer()
    client = FakeClient()
    app, window, _output = make_window(tmp_path, client, provider="local", server=server)
    assert server.started == 1
    window.apply_transcript("final", ORIGINAL)
    window._poll()
    assert client.calls == [] and "Waiting" in window.status_label.text()
    server.is_ready = True
    settle(app, window, lambda: client.calls[:1] == [("clean", ORIGINAL)])
    window.close()
    assert server.stopped == 1


def test_server_failure_is_reported_and_original_kept(tmp_path):
    server = FakeServer()
    app, window, _output = make_window(tmp_path, FakeClient(), provider="local", server=server)
    server.failed = "Local model server exited (code 1). See serve.log"
    window.apply_transcript("final", ORIGINAL)
    settle(app, window, lambda: "Local model unavailable" in window.status_label.text())
    assert "exited" in window.status_label.toolTip()
    assert window.transcript.toPlainText() == ORIGINAL
    window.close()


def test_turning_smart_editing_off_in_settings_stops_it(tmp_path):
    server = FakeServer()
    app, window, _output = make_window(tmp_path, FakeClient(), provider="local", server=server)
    window.settings_window.rewrite_enabled.setChecked(False)
    assert not window.smart.active and server.stopped == 1
    window.close()


def test_polished_text_keeps_the_transcript_font(tmp_path):
    from PySide6.QtGui import QTextCursor

    app, window, _output = make_window(tmp_path, FakeClient())
    family = window.transcript.font().family()
    window.apply_transcript("final", ORIGINAL)
    animation = window.smart.animation
    settle(app, window, lambda: animation.state() == animation.State.Running)
    animation.setCurrentTime(animation.duration() // 2)
    assert family in window.transcript.toHtml()
    animation.setCurrentTime(animation.duration())
    app.processEvents()
    cursor = QTextCursor(window.transcript.document())
    cursor.setPosition(1)
    assert cursor.charFormat().font().family() == family
    window.smart.undo_button.hovered.emit(True)
    assert family in window.transcript.toHtml()
    window.close()


def test_status_line_is_as_wide_as_the_transcript(tmp_path):
    app, window, _output = make_window(tmp_path, FakeClient())
    polish(app, window)
    assert window.status_label.width() == window.transcript.width()
    window.close()


def test_reset_cancels_queued_rewrite(tmp_path):
    gate = threading.Event()
    app, window, _output = make_window(tmp_path, FakeClient(gate=gate))
    window.apply_transcript("final", ORIGINAL)
    window.smart.reset()
    window.apply_transcript("final", ORIGINAL)
    queued = window.smart.future
    window.hide_overlay()
    assert queued.cancelled()
    gate.set()
    window.close()


def test_suggestions_wait_and_are_skipped_after_confirm(tmp_path):
    client = FakeClient(suggestions=[{"label": "更正式", "text": "我明天需请假一天。"}])
    app, window, output = make_window(tmp_path, client)
    polish(app, window)
    assert not any(kind == "suggest" for kind, _text in client.calls)
    window.confirm_button.click()
    deadline = time.monotonic() + window.smart.suggest_delay_ms / 1000 + 0.5
    while time.monotonic() < deadline:
        window._poll()
        app.processEvents()
        time.sleep(0.02)
    assert output.calls == [POLISHED]
    assert not any(kind == "suggest" for kind, _text in client.calls)
    window.close()


def test_disabling_mid_request_discards_the_result(tmp_path):
    gate = threading.Event()
    app, window, _output = make_window(tmp_path, FakeClient(gate=gate))
    window.apply_transcript("final", ORIGINAL)
    window.settings_window.rewrite_enabled.setChecked(False)
    gate.set()
    for _ in range(30):
        window._poll()
        app.processEvents()
        time.sleep(0.01)
    assert window.transcript.toPlainText() == ORIGINAL
    assert window.smart.animation.state() != window.smart.animation.State.Running
    assert "Polishing" not in window.status_label.text()
    window.close()


def test_editing_while_polishing_restores_the_status(tmp_path):
    gate = threading.Event()
    app, window, _output = make_window(tmp_path, FakeClient(gate=gate))
    window.apply_transcript("final", ORIGINAL)
    assert "Polishing" in window.status_label.text()
    window.transcript.setPlainText("我自己改过了")
    assert window.status_label.text() == "Transcript ready · edit or confirm"
    gate.set()
    window.close()


def test_punctuation_and_case_fixes_are_applied(tmp_path):
    client = FakeClient(clean="I think so. It's fine.")
    app, window, _output = make_window(tmp_path, client)
    window.apply_transcript("final", "i think so its fine")
    animation = window.smart.animation
    settle(app, window, lambda: animation.state() == animation.State.Running)
    animation.setCurrentTime(animation.duration())
    app.processEvents()
    assert window.transcript.toPlainText() == "I think so. It's fine."
    window.close()


def test_failed_paste_ends_the_session(tmp_path):
    class RefusingOutput(RecordingOutput):
        def paste(self, text):
            self.calls.append(text)
            return False

    gate = threading.Event()
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    RewriteConfig(enabled=True, provider="custom", endpoint="http://example.test/v1", model="m").save(settings)
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings, text_output=RefusingOutput(),
                           rewrite_client=FakeClient(gate=gate))
    window.model_ready = True
    window.reveal()
    window._background_progress = 1.0
    window.apply_transcript("final", ORIGINAL)
    window.confirm_button.click()
    gate.set()
    settle(app, window, lambda: window.smart.future is None)
    for _ in range(20):
        window._poll()
        app.processEvents()
        time.sleep(0.01)
    assert window.smart.animation.state() != window.smart.animation.State.Running
    assert window.transcript.toPlainText() == ORIGINAL
    assert "manual paste" in window.status_label.text()
    window.close()


def test_model_state_is_shown_in_settings(tmp_path):
    server = FakeServer()
    app, window, _output = make_window(tmp_path, FakeClient(), provider="local", server=server)
    status = window.settings_window.rewrite_model_status
    window._poll()
    assert status.text() == "Starting…"
    server.is_ready = True
    window._poll()
    assert status.text() == "Ready"
    server.problem = ("missing_model", "D:/models/x.gguf")
    server.failed = "Required file not found: D:/models/x.gguf"
    window._poll()
    assert status.text() == "Model file not found: D:/models/x.gguf"
    window.close()


def test_connection_test_explains_the_local_model_state(tmp_path):
    server = FakeServer()
    app, window, _output = make_window(tmp_path, FakeClient(), provider="local", server=server)
    window.settings_window.rewrite_test_button.click()
    assert window.settings_window.rewrite_status.text() == "Not connected · the local model is still starting"
    window.settings_window.rewrite_enabled.setChecked(False)
    window.settings_window.rewrite_test_button.click()
    assert window.settings_window.rewrite_status.text() == "Not connected · smart editing is off"
    window.close()


def test_switching_language_updates_overlay_and_settings(tmp_path):
    app, window, _output = make_window(tmp_path, FakeClient())
    polish(app, window)
    settings = window.settings_window
    settings.language_box.setCurrentIndex(settings.language_box.findData("zh"))
    assert window.smart.undo_button.text() == "撤回修改"
    assert window.status_label.text().startswith("已整理")
    assert settings.categories.item(2).text() == "智能编辑"
    assert settings.rewrite_test_button.text() == "测试连接"
    assert window.settings.value("ui/language") == "zh"
    settings.language_box.setCurrentIndex(settings.language_box.findData("en"))
    assert window.smart.undo_button.text() == "Undo edits"
    assert settings.categories.item(2).text() == "Smart editing"
    window.close()


def test_continue_appends_to_the_current_text_and_polishes_the_whole(tmp_path):
    client = FakeClient(clean="你好，我叫李四。")
    app, window, _output = make_window(tmp_path, client)
    window.apply_transcript("final", "你好，我叫王不是我叫李四")
    animation = window.smart.animation
    settle(app, window, lambda: animation.state() == animation.State.Running)
    animation.setCurrentTime(animation.duration())
    app.processEvents()
    assert window.smart.continue_button.isVisibleTo(window)
    started = []
    window._start_recording = lambda continuation=False: started.append(continuation)
    window.smart.continue_button.click()
    assert started == [True]
    window._set_mode("recording")
    window.apply_transcript("partial", "他叫王五")
    assert window.transcript.toPlainText() == "你好，我叫李四。他叫王五"
    client.clean_result = "Hello, my name is Si Li. His name is Wu Wang."
    window.apply_transcript("final", "他叫王五，翻译成英文")
    settle(app, window, lambda: animation.state() == animation.State.Running)
    assert client.calls[-1] == ("clean", "你好，我叫李四。他叫王五，翻译成英文")
    animation.setCurrentTime(animation.duration())
    app.processEvents()
    assert window.transcript.toPlainText() == "Hello, my name is Si Li. His name is Wu Wang."
    window.smart.undo_button.click()
    assert window.transcript.toPlainText() == "你好，我叫李四。他叫王五，翻译成英文"
    window.close()


def test_continue_with_nothing_new_keeps_the_text(tmp_path):
    app, window, _output = make_window(tmp_path, FakeClient(), enabled=False)
    window.apply_transcript("final", "已经写好的一句话。")
    window._start_recording = lambda continuation=False: None
    window.continue_recording()
    window._set_mode("recording")
    window.apply_transcript("final", "")
    assert window.transcript.toPlainText() == "已经写好的一句话。"
    window.close()


def test_continue_is_offered_even_without_smart_editing(tmp_path):
    app, window, _output = make_window(tmp_path, FakeClient(), enabled=False)
    window.apply_transcript("final", ORIGINAL)
    assert window.smart.continue_button.isVisibleTo(window)
    assert not window.smart.undo_button.isVisibleTo(window)
    window.hide_overlay()
    window.reveal()
    assert not window.smart.continue_button.isVisibleTo(window)
    assert window._continuation == ""
    window.close()
