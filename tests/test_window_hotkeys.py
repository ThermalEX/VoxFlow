from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from voxflow.hotkeys import HOTKEY_IDS, MOD_ALT, MOD_CONTROL
from voxflow.window import VoxFlowWindow


class FakeHotkeyApi:
    def __init__(self, taken=()):
        self.taken = set(taken)
        self.active: dict[int, str] = {}
        self.calls = []

    def register(self, _hwnd, ident, hotkey):
        self.calls.append(("register", ident, hotkey.text))
        if hotkey.text in self.taken or hotkey.text in self.active.values():
            return False
        self.active[ident] = hotkey.text
        return True

    def unregister(self, _hwnd, ident):
        self.calls.append(("unregister", ident))
        self.active.pop(ident, None)


class Output:
    def remember_foreground(self, _hwnd):
        pass

    def paste(self, _text):
        return True


def make_window(tmp_path, api, **saved):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    for action, text in saved.items():
        settings.setValue(f"hotkeys/{action}", text)
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings, text_output=Output(),
                           hotkey_api=api)
    return window, settings


def test_both_shortcuts_are_registered_from_settings(tmp_path):
    api = FakeHotkeyApi()
    window, _settings = make_window(tmp_path, api, record="Ctrl+Alt+R")
    assert window.register_hotkey()
    assert api.active == {HOTKEY_IDS["record"]: "Ctrl+Alt+R", HOTKEY_IDS["continue"]: "Ctrl+Alt+Shift+Space"}
    assert window.hotkeys["record"].modifiers == MOD_CONTROL | MOD_ALT
    window.close()
    assert api.active == {}


def test_a_taken_shortcut_is_reported_by_name(tmp_path):
    window, _settings = make_window(tmp_path, FakeHotkeyApi(taken={"Ctrl+Alt+Shift+Space"}))
    assert not window.register_hotkey()
    assert window.hotkey_failures == ["continue"]
    window.show_shortcut_problem()
    assert "Ctrl+Alt+Shift+Space" in window.status_label.text()
    window.close()


def test_changing_a_shortcut_updates_hints_and_announces_it(tmp_path):
    api = FakeHotkeyApi()
    window, _settings = make_window(tmp_path, api)
    window.register_hotkey()
    window.show_status("status.press_hotkey", hotkey=window.hotkeys["record"].text)
    events = []
    window.hotkeys_changed.connect(lambda: events.append("changed"))
    assert window.set_hotkey("record", "Ctrl+Alt+V") is None
    assert api.active[HOTKEY_IDS["record"]] == "Ctrl+Alt+V"
    assert events == ["changed"]
    assert "Ctrl+Alt+V" in window.status_label.text()
    assert "Ctrl+Alt+V" in window.record_button.toolTip()
    window.close()


def test_a_shortcut_in_use_keeps_the_old_one(tmp_path):
    api = FakeHotkeyApi(taken={"Ctrl+Alt+T"})
    window, _settings = make_window(tmp_path, api)
    window.register_hotkey()
    assert window.set_hotkey("continue", "Ctrl+Alt+T") == "hotkey.in_use"
    assert window.hotkeys["continue"].text == "Ctrl+Alt+Shift+Space"
    assert api.active[HOTKEY_IDS["continue"]] == "Ctrl+Alt+Shift+Space"
    assert window.set_hotkey("continue", "Shift+T") == "hotkey.invalid"
    window.close()


def test_shortcuts_pause_while_a_new_one_is_recorded(tmp_path):
    api = FakeHotkeyApi()
    window, _settings = make_window(tmp_path, api)
    window.register_hotkey()
    window.settings_window.hotkey_capture.emit(True)
    assert api.active == {}
    window.settings_window.hotkey_capture.emit(False)
    assert len(api.active) == 2
    window.close()


def test_continue_shortcut_continues_the_result_or_starts_fresh(tmp_path):
    window, _settings = make_window(tmp_path, FakeHotkeyApi())
    window.model_ready = True
    calls = []
    window.continue_recording = lambda: calls.append("continue")
    window._start_recording = lambda continuation=False: calls.append("start")
    window.toggle_recording = lambda: calls.append("toggle")
    window._on_hotkey("continue")  # hidden: open the overlay and start a new recording
    assert calls == ["start"] and window.isVisible()
    window._on_hotkey("continue")
    window._on_hotkey("record")
    assert calls == ["start", "continue", "toggle"]
    window.close()


def test_continue_button_tooltip_names_its_shortcut(tmp_path):
    window, _settings = make_window(tmp_path, FakeHotkeyApi(), **{"continue": "Ctrl+Alt+C"})
    assert "Ctrl+Alt+C" in window.smart.continue_button.toolTip()
    window.close()
