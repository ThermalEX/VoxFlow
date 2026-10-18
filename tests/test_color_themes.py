from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from voxflow import color_themes
from voxflow.color_themes import CUSTOM, PRESETS, migrate_color_theme, saved_color_theme


def settings_at(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def contrast(first: str, second: str) -> float:
    def luminance(hex_color: str) -> float:
        color = QColor(hex_color)
        channels = []
        for value in (color.redF(), color.greenF(), color.blueF()):
            channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_presets_have_unique_ids_and_readable_accents():
    ids = [theme.id for theme in PRESETS]
    assert ids == ["sky", "dusk", "teal", "amber", "blossom", "graphite"]
    for theme in PRESETS:
        assert contrast(theme.accent_light, "#FFFFFF") >= 3, theme.id
        assert contrast(theme.accent_dark, "#212121") >= 3, theme.id
    sky = PRESETS[0]
    assert (sky.background, sky.capsule) == ("#438aee", "#2766d6")


def test_custom_theme_uses_saved_glow_colors(tmp_path):
    settings = settings_at(tmp_path)
    settings.setValue("ui/color_theme", CUSTOM)
    settings.setValue("appearance/background_color", "#112233")
    settings.setValue("appearance/capsule_color", "#445566")
    theme = saved_color_theme(settings)
    assert theme.id == CUSTOM
    assert (theme.background, theme.capsule) == ("#112233", "#445566")
    assert theme.accent_light == theme.accent_dark == "#445566"


def test_saved_preset_is_returned_and_unknown_falls_back_to_default(tmp_path):
    settings = settings_at(tmp_path)
    settings.setValue("ui/color_theme", "teal")
    assert saved_color_theme(settings).id == "teal"
    settings.setValue("ui/color_theme", "nonsense")
    assert saved_color_theme(settings).id == "sky"


def test_migration_keeps_customized_colors(tmp_path):
    settings = settings_at(tmp_path)
    settings.setValue("appearance/capsule_color", "#ff0000")
    migrate_color_theme(settings)
    assert settings.value("ui/color_theme") == CUSTOM
    fresh = QSettings(str(tmp_path / "fresh.ini"), QSettings.Format.IniFormat)
    migrate_color_theme(fresh)
    assert fresh.value("ui/color_theme") == "sky"
    fresh.setValue("ui/color_theme", "amber")
    migrate_color_theme(fresh)
    assert fresh.value("ui/color_theme") == "amber"  # an explicit choice is never overwritten
