"""Bundled Google Material Symbols used by the tray and settings window."""

from functools import lru_cache
from importlib.resources import files

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


@lru_cache(maxsize=32)
def symbol_pixmap(name: str, size: int, color: str) -> QPixmap:
    """Render a bundled Material Symbol with the requested foreground color."""
    svg = files("voxflow").joinpath("assets", "icons", f"{name}.svg").read_text(encoding="utf-8")
    svg = svg.replace("<svg ", f'<svg fill="{QColor(color).name()}" ', 1)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        raise ValueError(f"Invalid Material Symbol: {name}")
    image = QPixmap(size, size)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    return image


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128):
        image = QPixmap(size, size)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 64, size / 64)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#315EAB"))
        painter.drawRoundedRect(QRectF(3, 3, 58, 58), 17, 17)
        painter.setBrush(QColor("#6FA8F6"))
        painter.drawRoundedRect(QRectF(6, 6, 52, 52), 15, 15)
        painter.drawPixmap(12, 12, symbol_pixmap("mic", 40, "#173D78"))
        painter.end()
        icon.addPixmap(image)
    return icon


def line_icon(name: str, color: str = "#526376") -> QIcon:
    symbols = {
        "personalize": "tune",
        "settings": "settings",
        "restore": "restart_alt",
    }
    return QIcon(symbol_pixmap(symbols[name], 40, color))
