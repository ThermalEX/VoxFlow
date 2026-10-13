from PySide6.QtWidgets import QApplication, QLabel

from voxflow import settings_theme
from voxflow.settings_widgets import SettingRow, SettingsCard, ToggleSwitch


def app():
    return QApplication.instance() or QApplication([])


def test_dark_and_light_stylesheets_use_their_palettes():
    dark = settings_theme.stylesheet(settings_theme.DARK)
    light = settings_theme.stylesheet(settings_theme.LIGHT)
    assert settings_theme.DARK.window in dark and settings_theme.LIGHT.window in light
    assert "combobox-popup: 0" in dark


def test_theme_follows_override_then_system(monkeypatch):
    monkeypatch.setenv("VOXFLOW_THEME", "dark")
    assert settings_theme.current_theme() is settings_theme.DARK
    monkeypatch.setenv("VOXFLOW_THEME", "light")
    assert settings_theme.current_theme() is settings_theme.LIGHT


def test_toggle_switch_behaves_like_a_checkbox():
    app()
    switch = ToggleSwitch()
    seen = []
    switch.toggled.connect(seen.append)
    switch.click()
    assert switch.isChecked() and seen == [True]
    switch.setChecked(False)
    assert seen == [True, False]
    assert switch.sizeHint().width() > switch.sizeHint().height()


def test_card_hides_dividers_next_to_hidden_rows():
    app()
    card = SettingsCard()
    rows = [SettingRow(QLabel()) for _ in range(3)]
    for row in rows:
        card.add_row(row)
    card.show()
    assert [divider.isVisibleTo(card) for divider in card.dividers] == [True, True]
    rows[1].hide()
    card.refresh()
    assert [divider.isVisibleTo(card) for divider in card.dividers] == [False, True]
    rows[0].hide()
    card.refresh()
    assert [divider.isVisibleTo(card) for divider in card.dividers] == [False, False]


def test_color_dialog_controls_match_the_theme():
    sheet = settings_theme.stylesheet(settings_theme.DARK)
    assert "QColorDialog QSpinBox::up-button" in sheet
    assert "QColorDialog QPushButton:default" in sheet
