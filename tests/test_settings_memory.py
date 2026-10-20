from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from voxflow.memory import Memory
from voxflow.memory_store import FOREVER, WEEK, MemoryStore, day_of
from voxflow.rewriter import RewriteConfig
from voxflow.settings_window import SettingsWindow


def make(tmp_path, enabled=True, store=None):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    settings.setValue("memory/enabled", enabled)
    window = SettingsWindow(settings)
    store = store if store is not None else MemoryStore(tmp_path / "m.db")
    memory = Memory(settings, store=store, root=tmp_path)
    window.set_memory(memory)
    return window, memory, store


def row_texts(card):
    return [row.title.text() for row in card.rows]


def test_the_switch_turns_memory_on_and_off(tmp_path):
    window, memory, _store = make(tmp_path, enabled=False)
    page = window.memory_page
    assert not page.enabled.isChecked() and not page.add_button.isEnabled()
    page.enabled.click()
    assert memory.enabled and page.add_button.isEnabled()
    # The path may break after any folder (zero-width spaces), so narrow windows do not overflow.
    assert str(tmp_path / "memory") in page.location_row.desc.text().replace("​", "")
    page.enabled.click()
    assert not memory.enabled
    window.close()


def test_remembered_entries_are_listed_added_edited_and_deleted(tmp_path):
    window, memory, store = make(tmp_path)
    page = window.memory_page
    assert row_texts(page.entry_card) == ["Nothing remembered yet. Say \"remember …\" or turn memory on to keep texts."]
    store.add_entry("评审会", kind="event", source="auto", detail={"time": "周三下午三点"})
    memory.changed.emit()
    [row] = page.entry_card.rows
    assert row.title.text() == "评审会"
    assert row.desc.text().startswith("Plan · Found automatically · When: 周三下午三点")

    page.new_entry.setText("王书涵")
    page.new_kind.setCurrentIndex(page.new_kind.findData("person"))
    page.add_button.click()
    assert page.new_entry.text() == ""
    added = next(entry for entry in store.entries() if entry.content == "王书涵")
    assert (added.kind, added.source, added.keep) == ("person", "manual", FOREVER)

    page.ask_text = lambda _title, text: ("王书涵（我）", True)
    edit_button = next(row for row in page.entry_card.rows if row.title.text() == "王书涵").control_layout.itemAt(1).widget()
    edit_button.click()
    assert store.entry(added.id).content == "王书涵（我）"

    page.search.setText("评审")
    assert row_texts(page.entry_card) == ["评审会"]
    page.search.setText("没有")
    assert row_texts(page.entry_card) == ["Nothing matches"]
    page.search.clear()
    delete_button = page.entry_card.rows[0].control_layout.itemAt(2).widget()
    delete_button.click()
    assert len(store.entries()) == 1
    window.close()


def test_rows_move_between_a_week_and_forever(tmp_path):
    window, memory, store = make(tmp_path)
    entry = store.add_entry("评审会", source="auto")
    memory.changed.emit()
    keep = window.memory_page.entry_card.rows[0].control_layout.itemAt(0).widget()
    assert keep.value() == WEEK
    keep.buttons[FOREVER].click()
    assert store.entry(entry.id).keep == FOREVER
    window.close()


def test_each_day_shows_its_texts_and_summary(tmp_path):
    window, memory, store = make(tmp_path)
    record = store.add_record("记住周三开会", explicit=True)
    store.add_record("明天交房租。")
    memory.changed.emit()
    page = window.memory_page
    day = day_of(record.created_at)
    assert page.day_box.currentData() == day and "(today)" in page.day_box.currentText()
    assert row_texts(page.record_card) == ["记住周三开会", "明天交房租。"]
    assert "You said remember" in page.record_card.rows[0].desc.text()
    assert row_texts(page.summary_card) == ["Summary", "No summary for this day yet"]
    assert page.generate_button.text() == "Summarize" and page.generate_button.isEnabled()

    page.generate_button.click()  # no model: smart editing is off
    assert "Turn on smart editing" in page.summary_card.rows[0].desc.text()

    store.save_summary(day, "- 周三开会\n- 交房租")
    memory.changed.emit()
    assert row_texts(page.summary_card) == ["Summary", "- 周三开会\n- 交房租"]
    assert page.summary_card.rows[0].desc.text().startswith("Summarized ")
    assert page.generate_button.text() == "Summarize again"
    window.close()


def test_deleting_a_day_and_clearing_everything_ask_first(tmp_path):
    window, memory, store = make(tmp_path)
    store.add_record("明天交房租。")
    store.add_entry("王书涵", kind="person")
    memory.changed.emit()
    page = window.memory_page
    answers = [False, True, True]
    page.confirm = lambda _text: answers.pop(0)
    page.delete_day_button.click()
    assert len(store.records()) == 1
    page.delete_day_button.click()
    assert store.records() == [] and len(store.entries()) == 1
    page.clear_button.click()
    assert store.entries() == []
    window.close()


def test_an_online_model_shows_where_memory_text_goes(tmp_path):
    window, memory, _store = make(tmp_path)
    page = window.memory_page
    assert page.remote_note.isHidden()
    RewriteConfig(enabled=True, provider="custom", endpoint="https://api.example.com/v1", model="m").save(window.settings)
    window.rewrite_changed.emit()
    assert not page.remote_note.isHidden()
    assert "https://api.example.com/v1" in page.remote_note.text()
    window.close()


def test_the_page_follows_the_interface_language(tmp_path):
    window, _memory, _store = make(tmp_path)
    window.language_box.setCurrentIndex(window.language_box.findData("zh"))
    assert window.categories.item(3).text() == "记忆"
    assert window.memory_page.new_kind.itemText(0) == "人名"
    assert window.memory_page.entry_card.rows[0].title.text().startswith("还没有记住任何内容")
    window.language_box.setCurrentIndex(window.language_box.findData("en"))
    window.close()
