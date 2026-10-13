from PySide6.QtCore import QSettings, Qt

from voxflow import hotkeys
from voxflow.hotkeys import DEFAULTS, MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, compose, parse, saved, vk_from_qt


def test_parse_turns_text_into_register_hotkey_arguments():
    hotkey = parse("Ctrl+Shift+Space")
    assert (hotkey.modifiers, hotkey.vk, hotkey.text) == (MOD_CONTROL | MOD_SHIFT, 0x20, "Ctrl+Shift+Space")
    assert parse("alt+ctrl+k").text == "Ctrl+Alt+K"
    assert parse("Win+F9").modifiers == MOD_WIN and parse("Win+F9").vk == 0x78
    assert parse("Ctrl+Alt+7").vk == 0x37


def test_parse_rejects_keys_that_would_clash_with_typing():
    for text in ("Space", "Shift+A", "Ctrl+Shift", "Ctrl+Unknown", "", "Ctrl++"):
        assert parse(text) is None, text


def test_same_combination_compares_keys_not_spelling():
    assert parse("Shift+Ctrl+Space") == parse("Ctrl+Shift+Space")
    assert parse("Ctrl+Alt+Shift+Space") != parse("Ctrl+Shift+Space")


def test_compose_builds_text_from_a_qt_key_press():
    mods = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    assert compose(mods, vk_from_qt(Qt.Key.Key_Space)) == "Ctrl+Alt+Space"
    assert compose(Qt.KeyboardModifier.MetaModifier, vk_from_qt(Qt.Key.Key_F2)) == "Win+F2"
    assert compose(Qt.KeyboardModifier.ShiftModifier, vk_from_qt(Qt.Key.Key_A)) is None
    assert compose(mods, 0) is None


def test_saved_falls_back_to_the_default_when_the_setting_is_unusable(tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    assert saved(settings, "record").text == DEFAULTS["record"] == "Ctrl+Shift+Space"
    assert saved(settings, "continue").text == DEFAULTS["continue"] == "Ctrl+Alt+Shift+Space"
    settings.setValue("hotkeys/record", "Q")
    assert saved(settings, "record").text == "Ctrl+Shift+Space"
    settings.setValue("hotkeys/record", "Ctrl+Alt+R")
    assert saved(settings, "record").text == "Ctrl+Alt+R"


def test_every_action_has_its_own_id():
    assert len(set(hotkeys.HOTKEY_IDS.values())) == len(hotkeys.ACTIONS) == 2
