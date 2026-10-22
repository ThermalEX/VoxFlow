from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from voxflow.edit_diff import highlight_html
from voxflow.memory import Memory, memory_path
from voxflow.memory_store import FOREVER, MemoryStore


def make_memory(tmp_path, enabled):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    settings.setValue("memory/enabled", enabled)
    return Memory(settings, root=tmp_path), settings


def test_memory_off_never_creates_the_database(tmp_path):
    memory, _settings = make_memory(tmp_path, enabled=False)
    assert memory.store is None
    assert memory.strip_command("记住周三开会") is None
    assert memory.correct("李丝涵") == "李丝涵"
    memory.remember("周三开会", explicit=True)
    assert not memory_path(tmp_path).exists()
    memory.close()


def test_turning_memory_on_opens_the_database_and_keeps_texts(tmp_path):
    memory, settings = make_memory(tmp_path, enabled=False)
    changes = []
    memory.changed.connect(lambda: changes.append(True))
    memory.set_enabled(True)
    assert settings.value("memory/enabled", type=bool)
    memory.remember("记住我叫李思涵", explicit=True)
    assert memory_path(tmp_path).is_file()
    [entry] = memory.store.entries()
    assert (entry.content, entry.keep) == ("我叫李思涵", FOREVER)
    assert len(changes) == 2
    memory.close()


def test_turning_memory_off_keeps_existing_rows_readable(tmp_path):
    memory, _settings = make_memory(tmp_path, enabled=True)
    memory.remember("项目代号是北极星。")
    memory.set_enabled(False)
    memory.close()
    reopened = Memory(memory.settings, root=tmp_path)
    assert [record.text for record in reopened.store.records()] == ["项目代号是北极星。"]
    reopened.remember("这句不会被记下。")
    assert len(reopened.store.records()) == 1
    reopened.close()


def test_names_are_corrected_from_people_and_terms(tmp_path):
    store = MemoryStore(":memory:")
    store.add_entry("李思涵", kind="person")
    store.add_entry("周三开会", kind="event")
    memory, settings = make_memory(tmp_path, enabled=True)
    memory = Memory(settings, store=store)
    assert memory.correct("李丝涵说周三开会") == "李思涵说周三开会"
    memory.close()


def test_highlight_pulses_from_text_color_to_accent_and_back():
    text, accent = (240, 240, 240), (100, 150, 250)
    assert "rgba(240,240,240" in highlight_html("记住", 0.0, text, accent)
    assert "rgba(100,150,250" in highlight_html("记住", 0.5, text, accent)
    assert "rgba(240,240,240" in highlight_html("记住", 1.0, text, accent)
    assert "&lt;b&gt;" in highlight_html("<b>", 0.5, text, accent)


def test_events_are_described_with_the_words_said_and_the_date_they_mean():
    from voxflow.memory import describe_entry, describe_when
    from voxflow.memory_store import Entry

    assert describe_when({"time": "周三下午三点", "date": "2026-10-21"}) == "周三下午三点，10月21日周三"
    assert describe_when({"date": "2026-10-21"}) == "10月21日周三"
    assert describe_when({}) == ""
    entry = Entry(1, "event", "评审会", "auto", "week", 0.0, 0.0, {"time": "周三下午三点", "date": "2026-10-21"})
    assert describe_entry(entry) == "评审会（周三下午三点，10月21日周三）"
    assert describe_when({"time": "Wednesday at 3pm", "date": "2026-10-21"}, "en") == "Wednesday at 3pm, Wed 21 Oct"


def test_summary_headings_follow_the_interface_language():
    from voxflow.memory import display_summary

    chinese = "日程与会议：\n- 周三下午三点评审会\n待办事项：\n- 交报告\n提到的人和事：\n- 张三"
    assert display_summary(chinese, "en") == "Schedule:\n- 周三下午三点评审会\nTo do:\n- 交报告\nPeople and things:\n- 张三"
    assert display_summary("Schedule:\n- Seminar on Friday", "zh") == "日程与会议：\n- Seminar on Friday"
    assert display_summary("今天没有需要特别记录的安排或待办。", "en") == "Nothing in particular to note today."
    assert display_summary(chinese, "zh") == chinese
