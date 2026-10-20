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
    assert memory.correct("王淑涵") == "王淑涵"
    memory.remember("周三开会", explicit=True)
    assert not memory_path(tmp_path).exists()
    memory.close()


def test_turning_memory_on_opens_the_database_and_keeps_texts(tmp_path):
    memory, settings = make_memory(tmp_path, enabled=False)
    changes = []
    memory.changed.connect(lambda: changes.append(True))
    memory.set_enabled(True)
    assert settings.value("memory/enabled", type=bool)
    memory.remember("记住我叫王书涵", explicit=True)
    assert memory_path(tmp_path).is_file()
    [entry] = memory.store.entries()
    assert (entry.content, entry.keep) == ("我叫王书涵", FOREVER)
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
    store.add_entry("王书涵", kind="person")
    store.add_entry("周三开会", kind="event")
    memory, settings = make_memory(tmp_path, enabled=True)
    memory = Memory(settings, store=store)
    assert memory.correct("王淑涵说周三开会") == "王书涵说周三开会"
    memory.close()


def test_highlight_pulses_from_text_color_to_accent_and_back():
    text, accent = (240, 240, 240), (100, 150, 250)
    assert "rgba(240,240,240" in highlight_html("记住", 0.0, text, accent)
    assert "rgba(100,150,250" in highlight_html("记住", 0.5, text, accent)
    assert "rgba(240,240,240" in highlight_html("记住", 1.0, text, accent)
    assert "&lt;b&gt;" in highlight_html("<b>", 0.5, text, accent)
