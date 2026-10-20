import time

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from voxflow.memory import memory_path
from voxflow.memory_store import FOREVER, WEEK, MemoryStore
from voxflow.rewriter import RewriteConfig
from voxflow.window import VoxFlowWindow


class RecordingOutput:
    def __init__(self, works=True):
        self.calls = []
        self.works = works

    def remember_foreground(self, _own_hwnd):
        pass

    def paste(self, text):
        self.calls.append(text)
        return self.works


class FakeClient:
    def __init__(self, clean):
        self.clean_result = clean
        self.calls = []

    def clean(self, text):
        self.calls.append(("clean", text))
        return self.clean_result

    def suggest(self, text):
        return []


def make_window(tmp_path, memory_on=True, client=None, store=None, output=None):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    settings.setValue("memory/enabled", memory_on)
    RewriteConfig(enabled=client is not None, provider="custom", endpoint="http://example.test/v1",
                  model="m").save(settings)
    output = output or RecordingOutput()
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings, text_output=output,
                           rewrite_client=client, memory_store=store)
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


def finish(app, animation):
    if animation.state() == animation.State.Running:
        animation.setCurrentTime(animation.duration())
    app.processEvents()


def test_with_memory_off_nothing_is_stripped_or_written(tmp_path):
    app, window, output = make_window(tmp_path, memory_on=False)
    window.apply_transcript("final", "记住周三开会")
    assert window.transcript.toPlainText() == "记住周三开会"
    assert window.smart.highlight.state() != window.smart.highlight.State.Running
    window._confirm_text()
    assert output.calls == ["记住周三开会"]
    assert not memory_path(tmp_path / "data").exists()
    window.close()


def test_a_remember_request_pulses_and_is_remembered_forever_when_confirmed(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    app, window, output = make_window(tmp_path, store=store)
    window.apply_transcript("final", "记住周三下午三点开评审会")
    highlight = window.smart.highlight
    assert window.transcript.toPlainText() == "周三下午三点开评审会"
    assert highlight.state() == highlight.State.Running
    assert "Will remember" in window.status_label.text()
    highlight.setCurrentTime(highlight.duration() // 2)
    markup = window.transcript.toHtml()
    assert "color:#" in markup and "#f3f7ff" not in markup  # tinted, not the plain text color
    assert window.transcript.isReadOnly()
    finish(app, highlight)
    assert window.transcript.toPlainText() == "周三下午三点开评审会" and not window.transcript.isReadOnly()
    window._confirm_text()
    assert output.calls == ["周三下午三点开评审会"]
    [entry] = store.entries()
    assert (entry.content, entry.source, entry.keep) == ("周三下午三点开评审会", "explicit", FOREVER)
    [record] = store.records()
    assert (record.text, record.keep) == ("周三下午三点开评审会", WEEK)
    window.close()


def test_cancelling_a_remember_request_remembers_nothing(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    app, window, _output = make_window(tmp_path, store=store)
    window.apply_transcript("final", "记住周三开会")
    window.smart.reset()
    assert store.entries() == [] and store.records() == []
    window.close()


def test_ordinary_confirmed_text_is_recorded_for_a_week(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    app, window, output = make_window(tmp_path, store=store)
    window.apply_transcript("final", "明天上午十点开会。")
    window._confirm_text()
    assert [record.text for record in store.records()] == ["明天上午十点开会。"]
    assert store.entries() == []
    window.close()


def test_text_is_recorded_even_when_pasting_fails(tmp_path, preserve_clipboard):
    store = MemoryStore(tmp_path / "m.db")
    app, window, _output = make_window(tmp_path, store=store, output=RecordingOutput(works=False))
    window.apply_transcript("final", "记住客户姓欧阳")
    finish(app, window.smart.highlight)
    window._confirm_text()
    assert [entry.content for entry in store.entries()] == ["客户姓欧阳"]
    window.close()


def test_remembered_names_are_fixed_without_smart_editing(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    store.add_entry("王书涵", kind="person")
    app, window, output = make_window(tmp_path, store=store)
    window.apply_transcript("final", "把文件发给王淑涵。")
    animation = window.smart.animation
    assert animation.state() == animation.State.Running
    finish(app, animation)
    assert window.transcript.toPlainText() == "把文件发给王书涵。"
    assert window.smart.undo_button.isVisibleTo(window)
    window._confirm_text()
    assert output.calls == ["把文件发给王书涵。"]
    window.close()


def test_remembered_names_are_fixed_in_the_rewrite(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    store.add_entry("王书涵", kind="person")
    client = FakeClient("把文件发给王淑涵。")
    app, window, _output = make_window(tmp_path, store=store, client=client)
    window.apply_transcript("final", "额，把文件发给王淑涵。")
    animation = window.smart.animation
    settle(app, window, lambda: animation.state() == animation.State.Running)
    finish(app, animation)
    assert window.transcript.toPlainText() == "把文件发给王书涵。"
    window.close()


def test_a_rewrite_that_arrives_during_the_pulse_waits_for_it(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    client = FakeClient("周三下午三点开评审会。")
    app, window, _output = make_window(tmp_path, store=store, client=client)
    window.apply_transcript("final", "记住额周三下午三点开评审会")
    assert client.calls == [] or client.calls[0] == ("clean", "额周三下午三点开评审会")
    settle(app, window, lambda: window.smart._pending_clean is not None)
    assert window.smart.animation.state() != window.smart.animation.State.Running
    finish(app, window.smart.highlight)
    animation = window.smart.animation
    assert animation.state() == animation.State.Running
    finish(app, animation)
    assert window.transcript.toPlainText() == "周三下午三点开评审会。"
    window._confirm_text()
    assert [entry.content for entry in store.entries()] == ["周三下午三点开评审会。"]
    window.close()
