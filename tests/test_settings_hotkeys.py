from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from voxflow.settings_window import SettingsWindow

CTRL_ALT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier


def make(tmp_path):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return SettingsWindow(settings), settings


def test_shortcuts_and_about_pages_follow_smart_editing(tmp_path):
    window, _settings = make(tmp_path)
    names = [window.categories.item(index).text() for index in range(window.categories.count())]
    assert names == ["General", "Appearance", "Smart editing", "Shortcuts", "About"]
    assert all(not window.categories.item(index).icon().isNull() for index in range(5))
    assert window.hotkey_buttons["record"].text() == "Ctrl+Shift+Space"
    assert window.hotkey_buttons["continue"].text() == "Ctrl+Alt+Shift+Space"
    window.close()


def test_recording_a_shortcut_saves_it_and_pauses_global_shortcuts(tmp_path):
    window, settings = make(tmp_path)
    paused = []
    window.hotkey_capture.connect(paused.append)
    button = window.hotkey_buttons["record"]
    button.click()
    assert button.capturing and button.text() == "Press new keys…"
    QTest.keyClick(button, Qt.Key.Key_K)  # no modifier: keep waiting
    assert button.capturing and button.text() == "Include Ctrl, Alt or Win"
    QTest.keyClick(button, Qt.Key.Key_K, CTRL_ALT)
    assert not button.capturing and button.text() == "Ctrl+Alt+K"
    assert settings.value("hotkeys/record") == "Ctrl+Alt+K"
    assert paused == [True, False]
    assert window.hotkey_status.text() == "Saved · Ctrl+Alt+K"
    window.close()


def test_escape_cancels_recording(tmp_path):
    window, settings = make(tmp_path)
    window.show()
    button = window.hotkey_buttons["continue"]
    button.click()
    QTest.keyClick(button, Qt.Key.Key_Escape)
    assert not button.capturing and button.text() == "Ctrl+Alt+Shift+Space"
    assert settings.value("hotkeys/continue") is None
    assert window.isVisible()  # Esc cancels the recorder instead of closing settings
    window.close()


def test_the_same_keys_cannot_serve_both_actions(tmp_path):
    window, settings = make(tmp_path)
    button = window.hotkey_buttons["continue"]
    button.click()
    QTest.keyClick(button, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert button.text() == "Ctrl+Alt+Shift+Space"
    assert settings.value("hotkeys/continue") is None
    assert window.hotkey_status.text() == "Ctrl+Shift+Space is already used for Start or stop voice input"
    window.close()


def test_a_shortcut_the_app_cannot_register_is_rejected(tmp_path):
    window, settings = make(tmp_path)
    seen = []
    window.set_hotkey_applier(lambda action, text: seen.append((action, text)) or "hotkey.in_use")
    button = window.hotkey_buttons["record"]
    button.click()
    QTest.keyClick(button, Qt.Key.Key_F8, CTRL_ALT)
    assert seen == [("record", "Ctrl+Alt+F8")]
    assert button.text() == "Ctrl+Shift+Space" and settings.value("hotkeys/record") is None
    assert window.hotkey_status.text() == "Ctrl+Alt+F8 is taken by another app · kept the previous shortcut"
    window.close()


def test_restore_defaults_even_when_the_custom_keys_are_swapped(tmp_path):
    window, settings = make(tmp_path)
    applied = []
    window.set_hotkey_applier(lambda action, text: applied.append((action, text)))
    settings.setValue("hotkeys/record", "Ctrl+Alt+Shift+Space")
    settings.setValue("hotkeys/continue", "Ctrl+Shift+Space")
    window.hotkey_buttons["record"].set_hotkey("Ctrl+Alt+Shift+Space")
    window.hotkey_buttons["continue"].set_hotkey("Ctrl+Shift+Space")
    window.hotkey_restore_button.click()
    assert window.hotkey_buttons["record"].text() == "Ctrl+Shift+Space"
    assert window.hotkey_buttons["continue"].text() == "Ctrl+Alt+Shift+Space"
    assert settings.value("hotkeys/record") == "Ctrl+Shift+Space"
    assert {action for action, _text in applied} == {"record", "continue"}
    window.close()


def test_about_page_shows_the_app_and_reserves_release_features(tmp_path):
    window, _settings = make(tmp_path)
    assert window.about_name.text() == "VoxFlow"
    assert window.about_version.text().startswith("Version 0.")
    assert window.about_author.text() == "Author ThermalEX"
    for control in (window.about_repo_button, window.update_channel, window.update_on_start,
                    window.update_check_button):
        assert not control.isEnabled()
    assert window.about_repo_button.toolTip() == "Available after the first public release"
    window.close()


def test_new_pages_switch_language(tmp_path):
    window, _settings = make(tmp_path)
    window.language_box.setCurrentIndex(window.language_box.findData("zh"))
    assert window.categories.item(3).text() == "快捷键"
    assert window.categories.item(4).text() == "关于"
    assert window.about_version.text().startswith("版本 ")
    assert window.update_channel.itemText(1) == "测试版（含正式版）"
    window.language_box.setCurrentIndex(window.language_box.findData("en"))
    window.close()


def test_appearance_page_picks_light_dark_or_system(tmp_path, monkeypatch):
    monkeypatch.delenv("VOXFLOW_THEME", raising=False)
    window, settings = make(tmp_path)
    box = window.theme_box
    assert [box.itemData(i) for i in range(box.count())] == ["system", "light", "dark"]
    assert box.currentData() == "system"
    box.setCurrentIndex(box.findData("dark"))
    assert window.theme.name == "dark" and settings.value("ui/theme") == "dark"
    box.setCurrentIndex(box.findData("light"))
    assert window.theme.name == "light"
    reopened = SettingsWindow(settings)
    assert reopened.theme.name == "light" and reopened.theme_box.currentData() == "light"
    reopened.close()
    window.close()


def test_about_icon_is_vertically_centered(tmp_path):
    window, _settings = make(tmp_path)
    layout = window.about_icon.parentWidget().layout()
    assert layout.itemAt(layout.indexOf(window.about_icon)).alignment() == Qt.AlignmentFlag.AlignVCenter
    window.close()
