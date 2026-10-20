import time

import numpy as np
import pytest
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication

from voxflow import download_panel as panel_module
from voxflow import i18n, onboarding
from voxflow.catalog import builtin_catalog
from voxflow.mic_meter import MicMeter
from voxflow.onboarding import OnboardingWindow, should_show_onboarding
from voxflow.settings_window import SettingsWindow


class FakeManager(QObject):
    progress = Signal(str, object, object, float)
    item_state = Signal(str, str)
    item_failed = Signal(str, str)
    all_done = Signal()

    def __init__(self):
        super().__init__()
        self.started = []

    def start(self, items, source):
        self.started.append([item.id for item in items])

    def cancel(self, _item_id):
        pass

    def cancel_all(self):
        pass

    def states(self):
        return dict(getattr(self, "current_states", {}))

    def is_busy(self):
        return False


class FakeStream:
    opened = []

    def __init__(self, callback=None, **kwargs):
        self.callback = callback
        self.kwargs = kwargs
        FakeStream.opened.append(self)

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


@pytest.fixture
def tutorial(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(onboarding, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(panel_module, "fetch_catalog", lambda source: (builtin_catalog(), True))
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings_window = SettingsWindow(settings)
    manager = FakeManager()
    window = OnboardingWindow(settings, settings_window, manager, meter=MicMeter(stream_factory=FakeStream),
                              has_nvidia=lambda: True)
    yield window, settings, settings_window, manager
    window.close()
    settings_window.close()


def test_shows_on_first_run_only(tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    assert should_show_onboarding(settings)
    settings.setValue("onboarding/done", True)
    assert not should_show_onboarding(settings)


def test_walks_seven_steps_and_marks_done(tutorial):
    window, settings, _settings_window, _manager = tutorial
    finished = []
    window.finished.connect(lambda: finished.append(True))
    assert window.steps.count() == 7
    assert not window.back_button.isEnabled()
    for _ in range(6):
        window.next_button.click()
    assert window.steps.currentIndex() == 6
    assert window.next_button.text() == "Get started"
    window.next_button.click()
    assert finished == [True]
    assert settings.value("onboarding/done") in (True, "true")


def test_skip_marks_done(tutorial):
    window, settings, _settings_window, _manager = tutorial
    window.skip_button.click()
    assert settings.value("onboarding/done") in (True, "true")


def test_language_step_switches_tutorial_language(tutorial):
    window, settings, settings_window, _manager = tutorial
    window.language_control.set_value("zh")
    assert window.next_button.text() == "下一步"
    assert settings.value("ui/language") == "zh"
    assert settings_window.categories.item(0).text() == "常规"
    i18n.set_language("en")


def test_theme_step_updates_settings_window(tutorial):
    window, settings, settings_window, _manager = tutorial
    window.next_button.click()
    window.color_theme_buttons["amber"].click()
    assert settings.value("ui/color_theme") == "amber"
    assert settings_window.color_theme_buttons["amber"].isChecked()
    window.mode_control.set_value("dark")
    assert settings.value("ui/theme") == "dark"
    assert window.preview.capsule_color.name() == "#e2700f"


def test_download_step_preselects_but_does_not_start(tutorial):
    window, _settings, _settings_window, manager = tutorial
    for _ in range(3):
        window.next_button.click()
    panel = window.download_panel
    deadline = time.monotonic() + 3
    while not panel.rows and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert panel.selected_ids() == ["asr-sensevoice", "llama-vulkan", "rewrite-v6-q8"]
    assert manager.started == []


def test_try_step_names_the_current_shortcut(tutorial):
    window, settings, _settings_window, _manager = tutorial
    settings.setValue("hotkeys/record", "Ctrl+Alt+R")
    for _ in range(4):
        window.next_button.click()
    assert "Ctrl+Alt+R" in window.try_text.text()
    assert not window.speech_missing.isHidden()  # no speech model in the empty data folder


def test_mic_meter_reports_level_without_saving_audio(tmp_path):
    QApplication.instance() or QApplication([])
    FakeStream.opened.clear()
    meter = MicMeter(stream_factory=FakeStream)
    levels = []
    meter.level.connect(levels.append)
    meter.start(None)
    wave = (0.3 * np.sin(np.linspace(0, 40 * np.pi, 1600))).astype("float32").reshape(-1, 1)
    FakeStream.opened[-1].callback(wave, len(wave), None, None)
    QApplication.processEvents()
    assert levels and levels[-1] > 0.1
    meter.stop()
    assert list(tmp_path.iterdir()) == []


def test_mic_meter_opens_the_device_at_its_own_rate():
    from voxflow.microphones import SYSTEM_DEFAULT

    QApplication.instance() or QApplication([])
    FakeStream.opened.clear()
    meter = MicMeter(stream_factory=FakeStream)
    meter.start(SYSTEM_DEFAULT)
    kwargs = FakeStream.opened[-1].kwargs
    assert kwargs["device"] is None  # follow the Windows default
    assert kwargs.get("samplerate") is None  # WASAPI shared mode only opens at the device's own rate
    meter.stop()


def test_the_memory_step_turns_memory_on_and_keeps_settings_in_step(tutorial):
    window, settings, settings_window, _manager = tutorial
    assert not window.memory_switch.isChecked()
    assert not settings.value("memory/enabled", False, type=bool)
    window.memory_switch.click()
    assert settings.value("memory/enabled", False, type=bool)
    assert settings_window.memory_page.enabled.isChecked()
    window.memory_switch.click()
    assert not settings.value("memory/enabled", False, type=bool)
