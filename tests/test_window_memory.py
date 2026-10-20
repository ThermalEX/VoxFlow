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
    store.add_entry("李思涵", kind="person")
    app, window, output = make_window(tmp_path, store=store)
    window.apply_transcript("final", "把文件发给李丝涵。")
    animation = window.smart.animation
    assert animation.state() == animation.State.Running
    finish(app, animation)
    assert window.transcript.toPlainText() == "把文件发给李思涵。"
    assert window.smart.undo_button.isVisibleTo(window)
    window._confirm_text()
    assert output.calls == ["把文件发给李思涵。"]
    window.close()


def test_remembered_names_are_fixed_in_the_rewrite(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    store.add_entry("李思涵", kind="person")
    client = FakeClient("把文件发给李丝涵。")
    app, window, _output = make_window(tmp_path, store=store, client=client)
    window.apply_transcript("final", "额，把文件发给李丝涵。")
    animation = window.smart.animation
    settle(app, window, lambda: animation.state() == animation.State.Running)
    finish(app, animation)
    assert window.transcript.toPlainText() == "把文件发给李思涵。"
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


class MemoryClient(FakeClient):
    """A rewrite model that also knows the memory tasks."""

    def __init__(self, clean, extracted=(), filled=None, summary="- 周三下午三点评审会", suggestions=()):
        super().__init__(clean)
        self.extracted = list(extracted)
        self.filled = filled
        self.summary = summary
        self.suggestions = list(suggestions)

    def suggest(self, text):
        self.calls.append(("suggest", text))
        return self.suggestions

    def extract(self, text, today):
        self.calls.append(("extract", text, today))
        return self.extracted

    def fill(self, text, memories):
        self.calls.append(("fill", text, memories))
        return self.filled if self.filled is not None else text

    def summarize(self, day, texts, memories):
        self.calls.append(("summarize", day, texts, memories))
        return self.summary


def test_confirmed_texts_are_mined_for_entries_once_the_overlay_is_idle(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    client = MemoryClient("周三下午三点开评审会，李思涵主持。", extracted=[
        {"kind": "event", "content": "评审会", "time": "周三下午三点"}, {"kind": "person", "content": "李思涵"}])
    app, window, _output = make_window(tmp_path, store=store, client=client)
    window.apply_transcript("final", "周三下午三点开评审会，李思涵主持。")
    settle(app, window, lambda: client.calls and window.smart.future is None)
    assert not any(call[0] == "extract" for call in client.calls)  # never while the overlay is in use
    window._confirm_text()
    settle(app, window, lambda: not store.pending_records())
    entries = {entry.content: entry for entry in store.entries()}
    from datetime import date

    detail = entries["评审会"].detail
    assert detail["time"] == "周三下午三点" and entries["评审会"].keep == WEEK
    assert date.fromisoformat(detail["date"]).weekday() == 2  # worked out by rule: the coming Wednesday
    assert entries["李思涵"].kind == "person" and entries["李思涵"].source == "auto"
    window.close()


def test_entries_found_in_a_remember_request_are_kept_forever(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    client = MemoryClient("我叫李思涵。", extracted=[{"kind": "person", "content": "李思涵"}])
    app, window, _output = make_window(tmp_path, store=store, client=client)
    window.apply_transcript("final", "记住我叫李思涵。")
    finish(app, window.smart.highlight)
    settle(app, window, lambda: window.smart.future is None and window.smart._pending_clean is None)
    window._confirm_text()
    settle(app, window, lambda: not store.pending_records())
    keeps = {entry.content: entry.keep for entry in store.entries()}
    assert keeps["李思涵"] == FOREVER
    window.close()


def test_an_unreachable_model_leaves_the_text_for_later(tmp_path):
    from voxflow.rewriter import RewriteError

    store = MemoryStore(tmp_path / "m.db")
    store.add_record("明天十点开会。")

    class Down(MemoryClient):
        def extract(self, text, today):
            raise RewriteError("down", kind="unreachable")

    client = Down("x")
    app, window, _output = make_window(tmp_path, store=store, client=client)
    window.hide_overlay()
    settle(app, window, lambda: window.memory._retry_at > 0)
    assert len(store.pending_records()) == 1
    window.close()


def test_related_memories_offer_a_fill_in_suggestion(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    store.add_entry("评审会", kind="event", detail={"time": "周三下午三点"})
    client = MemoryClient("提醒大家参加评审会。", filled="提醒大家参加周三下午三点的评审会。",
                          suggestions=[{"label": "更正式", "text": "请各位准时参加评审会。"}])
    app, window, _output = make_window(tmp_path, store=store, client=client)
    window.smart.suggest_delay_ms = 0
    window.apply_transcript("final", "提醒大家参加评审会。")
    button = window.smart.suggestion_buttons[0]
    settle(app, window, lambda: button.text() == "Fill from memory")
    assert ("fill", "提醒大家参加评审会。", ["评审会（周三下午三点）"]) in client.calls
    assert window.smart.suggestion_buttons[1].text() == "更正式"
    button.click()
    assert window.transcript.toPlainText() == "提醒大家参加周三下午三点的评审会。"
    window.close()


def test_no_fill_in_without_related_memories_or_when_nothing_changes(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    store.add_entry("北极星项目", kind="term")
    client = MemoryClient("明天交房租。")
    app, window, _output = make_window(tmp_path, store=store, client=client)
    window.smart.suggest_delay_ms = 0
    window.apply_transcript("final", "明天交房租。")
    settle(app, window, lambda: any(call[0] == "suggest" for call in client.calls) and window.smart.future is None)
    assert not any(call[0] == "fill" for call in client.calls)
    assert all(button.isHidden() for button in window.smart.suggestion_buttons)
    window.close()


def test_a_day_is_summarized_on_request(tmp_path):
    from voxflow.memory_store import day_of

    store = MemoryStore(tmp_path / "m.db")
    record = store.add_record("周三下午三点开评审会。")
    store.add_entry("评审会", kind="event", detail={"time": "周三下午三点"})
    client = MemoryClient("x")
    app, window, _output = make_window(tmp_path, store=store, client=client)
    ready = []
    window.memory.summary_ready.connect(ready.append)
    day = day_of(record.created_at)
    assert window.memory.summarize(day)
    assert not window.memory.summarize(day)  # already running
    settle(app, window, lambda: ready == [day])
    assert store.summary(day).text == "- 周三下午三点评审会"
    _name, sent_day, texts, memories = next(call for call in client.calls if call[0] == "summarize")
    assert (sent_day.isoformat(), texts, memories) == (day, ["周三下午三点开评审会。"], ["评审会（周三下午三点）"])
    window.close()


def test_summaries_need_texts_and_a_model(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    app, window, _output = make_window(tmp_path, store=store)
    failures = []
    window.memory.summary_failed.connect(lambda day, reason: failures.append(reason))
    assert not window.memory.summarize("2026-10-20")
    store.add_record("周三开会。")
    from voxflow.memory_store import day_of
    assert not window.memory.summarize(day_of(store.records()[0].created_at))
    assert failures == ["empty", "model"]
    window.close()
