"""Color themes: one set of colors for the overlay glow, the capsule and the accent of settings and the tutorial."""

from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor

from .appearance import DEFAULT_BACKGROUND, DEFAULT_CAPSULE


@dataclass(frozen=True)
class ColorTheme:
    id: str
    name_key: str
    background: str
    capsule: str
    accent_light: str  # accent on the light settings palette
    accent_dark: str  # accent on the dark settings palette

    def accent(self, scheme: str) -> str:
        return self.accent_dark if scheme == "dark" else self.accent_light


PRESETS: tuple[ColorTheme, ...] = (
    ColorTheme("sky", "color.sky", DEFAULT_BACKGROUND, DEFAULT_CAPSULE, "#2F7CF6", "#3D8BFF"),
    ColorTheme("dusk", "color.dusk", "#9b7cf0", "#6d3fd6", "#7C3AED", "#A78BFA"),
    ColorTheme("teal", "color.teal", "#2fb5a3", "#0f8f7f", "#0F8F7F", "#2DD4BF"),
    ColorTheme("amber", "color.amber", "#f5a524", "#e2700f", "#C2410C", "#FB923C"),
    ColorTheme("blossom", "color.blossom", "#f06ba8", "#d63384", "#C2185B", "#F472B6"),
    ColorTheme("graphite", "color.graphite", "#8a96a8", "#4b5563", "#475569", "#94A3B8"),
)
DEFAULT_THEME = PRESETS[0]
CUSTOM = "custom"
SETTING = "ui/color_theme"


def _color(settings: QSettings, key: str, fallback: str) -> str:
    color = QColor(str(settings.value(key, fallback)))
    return color.name() if color.isValid() else fallback


def custom_theme(settings: QSettings) -> ColorTheme:
    """The user's own glow colors; the accent follows the capsule color."""
    background = _color(settings, "appearance/background_color", DEFAULT_BACKGROUND)
    capsule = _color(settings, "appearance/capsule_color", DEFAULT_CAPSULE)
    return ColorTheme(CUSTOM, "color.custom", background, capsule, capsule, capsule)


def saved_color_theme(settings: QSettings) -> ColorTheme:
    chosen = str(settings.value(SETTING, DEFAULT_THEME.id))
    if chosen == CUSTOM:
        return custom_theme(settings)
    return next((theme for theme in PRESETS if theme.id == chosen), DEFAULT_THEME)


def migrate_color_theme(settings: QSettings) -> None:
    """Users who picked their own glow colors before themes existed keep them as the custom theme."""
    if settings.contains(SETTING):
        return
    customized = any(
        settings.contains(key) and _color(settings, key, default) != default
        for key, default in (("appearance/background_color", DEFAULT_BACKGROUND),
                             ("appearance/capsule_color", DEFAULT_CAPSULE)))
    settings.setValue(SETTING, CUSTOM if customized else DEFAULT_THEME.id)
