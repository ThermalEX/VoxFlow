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


def texts(memory_list):
    return [row.text.text() for row in memory_list.rows]


def action(row, label):
    row.actions[label].trigger()


def test_the_page_shows_the_switch_count_and_location(tmp_path):
    window, memory, store = make(tmp_path, enabled=False)
    page = window.memory_page
    assert not page.enabled.isChecked()
    page.enabled.click()
    assert memory.enabled
    # The path may break after any folder (zero-width spaces), so narrow windows do not overflow.
    assert str(tmp_path / "memory") in page.location_row.desc.text().replace("​", "")
    assert page.memories_row.desc.text().startswith("0 saved")
    store.add_entry("张三", kind="person")
    memory.changed.emit()
    assert page.memories_row.desc.text().startswith("1 saved")
    page.enabled.click()
    assert not memory.enabled
    window.close()


def test_saved_memories_can_be_searched_filtered_and_sorted(tmp_path):
    window, memory, store = make(tmp_path)
    clock = iter(range(1, 100))
    store._clock = lambda: float(next(clock)) + 1_760_000_000
    store.add_entry("评审会", kind="event", source="auto", detail={"time": "周三下午三点"})
    store.add_entry("张三", kind="person", source="explicit")
    store.add_entry("对芒果过敏", kind="fact", source="manual")
    window.memory_page.manage_button.click()
    dialog = window.memory_page.memories_dialog
    assert dialog.isVisible()
    assert texts(dialog.list) == ["对芒果过敏", "张三", "评审会"]  # newest first
    meta = dialog.list.rows[2].meta.text()
    assert meta.startswith("Plan · 7 days · When: 周三下午三点 · Found automatically")
    dialog.sort_button.click()
    assert texts(dialog.list) == ["评审会", "张三", "对芒果过敏"]
    dialog.sort_button.click()
    dialog.kind_filter.setCurrentIndex(dialog.kind_filter.findData("person"))
    assert texts(dialog.list) == ["张三"]
    dialog.kind_filter.setCurrentIndex(0)
    dialog.keep_filter.buttons[WEEK].click()
    assert texts(dialog.list) == ["评审会"]
    dialog.keep_filter.buttons["all"].click()
    dialog.search.setText("芒果")
    assert texts(dialog.list) == ["对芒果过敏"]
    assert dialog.count.text() == "Showing 1 of 3"
    dialog.search.setText("没有这个")
    assert dialog.list.rows == [] and dialog.list.empty.text() == "Nothing matches"
    window.close()


def test_memories_can_be_added_edited_moved_and_deleted(tmp_path):
    window, memory, store = make(tmp_path)
    page = window.memory_page
    page.show_memories()
    dialog = page.memories_dialog
    assert dialog.list.empty.isVisibleTo(dialog) and "Nothing remembered yet" in dialog.list.empty.text()
    dialog.add_action.trigger()
    assert dialog.add_bar.isVisibleTo(dialog)
    dialog.new_entry.setText("张三")
    dialog.new_kind.setCurrentIndex(dialog.new_kind.findData("person"))
    dialog.save_button.click()
    assert not dialog.add_bar.isVisibleTo(dialog)
    [entry] = store.entries()
    assert (entry.content, entry.kind, entry.source, entry.keep) == ("张三", "person", "manual", FOREVER)

    page.ask_text = lambda _title, _text: ("张三（主管）", True)
    action(dialog.list.rows[0], "Edit")
    assert store.entry(entry.id).content == "张三（主管）"
    action(dialog.list.rows[0], "Keep for 7 days")
    assert store.entry(entry.id).keep == WEEK
    action(dialog.list.rows[0], "Keep forever")
    assert store.entry(entry.id).keep == FOREVER
    action(dialog.list.rows[0], "Delete")
    assert store.entries() == [] and dialog.list.rows == []
    window.close()


def test_clearing_everything_asks_first(tmp_path):
    window, memory, store = make(tmp_path)
    store.add_entry("张三", kind="person")
    page = window.memory_page
    page.show_memories()
    answers = [False, True]
    page.confirm = lambda _text: answers.pop(0)
    page.memories_dialog.clear_action.trigger()
    assert len(store.entries()) == 1
    page.memories_dialog.clear_action.trigger()
    assert store.entries() == []
    window.close()


def test_each_day_shows_its_texts_and_summary(tmp_path):
    window, memory, store = make(tmp_path)
    record = store.add_record("记住张三下周一入职", explicit=True)
    store.add_record("明天交房租。")
    page = window.memory_page
    page.days_button.click()
    dialog = page.days_dialog
    day = day_of(record.created_at)
    assert dialog.day_box.currentData() == day and "(today)" in dialog.day_box.currentText()
    assert texts(dialog.list) == ["记住张三下周一入职", "明天交房租。"]
    assert "You said remember" in dialog.list.rows[0].meta.text()
    assert dialog.summary_text.text() == "No summary for this day yet"
    assert dialog.generate_button.text() == "Summarize" and dialog.generate_button.isEnabled()

    dialog.generate_button.click()  # no model: smart editing is off
    assert "Turn on smart editing" in dialog.summary_header.desc.text()

    store.save_summary(day, "- 张三下周一入职\n- 交房租")
    memory.changed.emit()
    assert dialog.summary_text.text() == "- 张三下周一入职\n- 交房租"
    assert dialog.summary_header.desc.text().startswith("Summarized ")
    assert dialog.generate_button.text() == "Summarize again"
    dialog.summary_keep.buttons[FOREVER].click()
    assert store.summary(day).keep == FOREVER
    action(dialog.list.rows[1], "Keep forever")
    assert store.records()[1].keep == FOREVER
    action(dialog.list.rows[1], "Delete")
    assert texts(dialog.list) == ["记住张三下周一入职"]
    window.close()


def test_deleting_a_day_asks_first(tmp_path):
    window, memory, store = make(tmp_path)
    store.add_record("明天交房租。")
    page = window.memory_page
    page.show_days()
    answers = [False, True]
    page.confirm = lambda _text: answers.pop(0)
    page.days_dialog.delete_day_button.click()
    assert len(store.records()) == 1
    page.days_dialog.delete_day_button.click()
    assert store.records() == []
    window.close()


def test_an_online_model_shows_where_memory_text_goes(tmp_path):
    window, memory, _store = make(tmp_path)
    page = window.memory_page
    page.show_memories()
    assert page.remote_note.isHidden() and page.memories_dialog.remote_note.isHidden()
    RewriteConfig(enabled=True, provider="custom", endpoint="https://api.example.com/v1", model="m").save(window.settings)
    window.rewrite_changed.emit()
    assert not page.remote_note.isHidden() and not page.memories_dialog.remote_note.isHidden()
    assert "https://api.example.com/v1" in page.memories_dialog.remote_note.text()
    window.close()


def test_the_page_and_windows_follow_the_interface_language(tmp_path):
    window, _memory, _store = make(tmp_path)
    window.memory_page.show_memories()
    window.language_box.setCurrentIndex(window.language_box.findData("zh"))
    dialog = window.memory_page.memories_dialog
    assert window.categories.item(3).text() == "记忆"
    assert dialog.windowTitle() == "已保存的记忆"
    assert dialog.kind_filter.itemText(0) == "全部类型" and dialog.new_kind.itemText(0) == "人名"
    assert dialog.new_entry.placeholderText().startswith("要记住的内容，例如：张三")
    window.language_box.setCurrentIndex(window.language_box.findData("en"))
    window.close()
