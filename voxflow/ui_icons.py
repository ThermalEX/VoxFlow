"""Small vector-painted icons shared by the tray and settings window."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


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
        painter.setBrush(QColor("#173D78"))
        painter.drawRoundedRect(QRectF(26, 15, 12, 25), 6, 6)
        pen = QPen(QColor("#173D78"), 3.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(20, 27, 24, 20), 180 * 16, 180 * 16)
        painter.drawLine(QPointF(32, 47), QPointF(32, 52))
        painter.drawLine(QPointF(26, 52), QPointF(38, 52))
        painter.end()
        icon.addPixmap(image)
    return icon


def line_icon(name: str, color: str = "#526376") -> QIcon:
    image = QPixmap(40, 40)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    pen = QPen(QColor(color), 1.65)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if name == "personalize":
        for y, knob in ((5, 7), (10, 13), (15, 9)):
            painter.drawLine(QPointF(3, y), QPointF(17, y))
            painter.setBrush(QColor("#F6F8FB"))
            painter.drawEllipse(QPointF(knob, y), 2.1, 2.1)
            painter.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "settings":
        painter.drawEllipse(QPointF(10, 10), 5.4, 5.4)
        painter.drawEllipse(QPointF(10, 10), 2.15, 2.15)
        for x1, y1, x2, y2 in (
            (10, 1.5, 10, 4.1), (10, 15.9, 10, 18.5),
            (1.5, 10, 4.1, 10), (15.9, 10, 18.5, 10),
            (4, 4, 5.8, 5.8), (14.2, 14.2, 16, 16),
            (4, 16, 5.8, 14.2), (14.2, 5.8, 16, 4),
        ):
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif name == "restore":
        painter.drawArc(QRectF(3, 3, 14, 14), 165 * 16, 270 * 16)
        arrow = QPainterPath()
        arrow.moveTo(QPointF(2.0, 7.3))
        arrow.lineTo(QPointF(7.8, 5.2))
        arrow.lineTo(QPointF(6.9, 11.1))
        arrow.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(arrow, QColor(color))
    painter.end()
    return QIcon(image)
