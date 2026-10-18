from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from voxflow.color_themes import PRESETS
from voxflow.window import VoxFlowWindow


class Output:
    def remember_foreground(self, _hwnd):
        pass

    def paste(self, _text):
        return True


def make_window(tmp_path):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    return VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings, text_output=Output()), settings


def test_picking_a_preset_recolors_overlay_and_settings(tmp_path):
    window, settings = make_window(tmp_path)
    teal = next(theme for theme in PRESETS if theme.id == "teal")
    window.settings_window.color_theme_buttons["teal"].click()
    assert window.background_color.name() == teal.background
    assert window.capsule.accent_color.name() == teal.capsule
    accent = teal.accent_dark if window.settings_window.theme.name == "dark" else teal.accent_light
    assert accent.lower() in window.settings_window.styleSheet().lower()
    assert settings.value("ui/color_theme") == "teal"
    window.close()


def test_custom_shows_color_pickers_only_when_selected(tmp_path):
    window, _settings = make_window(tmp_path)
    settings_window = window.settings_window
    settings_window.color_theme_buttons["dusk"].click()
    assert settings_window.background_button_row.isHidden() and settings_window.capsule_button_row.isHidden()
    settings_window.color_theme_buttons["custom"].click()
    assert not settings_window.background_button_row.isHidden()
    assert not settings_window.capsule_button_row.isHidden()
    window.close()


def test_custom_color_change_recolors_settings_accent(tmp_path):
    from PySide6.QtGui import QColor

    window, settings = make_window(tmp_path)
    window.settings_window.color_theme_buttons["custom"].click()
    window.settings_window.set_color("capsule", QColor("#aa3300"))
    assert window.capsule.accent_color.name() == "#aa3300"
    assert "#aa3300" in window.settings_window.styleSheet().lower()
    window.close()


def test_restore_appearance_returns_to_default_theme(tmp_path):
    window, settings = make_window(tmp_path)
    window.settings_window.color_theme_buttons["amber"].click()
    window.settings_window.restore_button.click()
    assert settings.value("ui/color_theme") == "sky"
    assert window.background_color.name() == "#438aee"
    assert window.settings_window.color_theme_buttons["sky"].isChecked()
    window.close()
