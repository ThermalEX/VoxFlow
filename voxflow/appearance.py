"""Saved appearance values and color transformations for the overlay."""

from PySide6.QtGui import QColor


DEFAULT_BACKGROUND = "#438aee"
DEFAULT_CAPSULE = "#2766d6"
DEFAULT_TEXT_SIZE = 24
DEFAULT_FONT = "Segoe UI"


def saved_color(value: object, fallback: str) -> QColor:
    color = QColor(str(value))
    return color if color.isValid() else QColor(fallback)


def tint(reference: QColor, accent: QColor, original_accent: str) -> QColor:
    """Shift an existing shade toward the chosen accent without flattening gradients."""
    original = QColor(original_accent)
    if accent.name() == original.name():
        return QColor(reference)
    hue = accent.hsvHueF()
    saturation = accent.hsvSaturationF()
    value = accent.valueF()
    original_saturation = max(0.01, original.hsvSaturationF())
    original_value = max(0.01, original.valueF())
    return QColor.fromHsvF(
        max(0.0, hue),
        min(1.0, saturation * reference.hsvSaturationF() / original_saturation),
        min(1.0, value * reference.valueF() / original_value),
        reference.alphaF(),
    )
