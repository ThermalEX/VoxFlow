"""Native-painted controls for the bottom voice surface."""

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton


class GlowCapsule(QPushButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(232, 76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Start or stop voice input")
        self.level = 0.0
        self.target_level = 0.0
        self.phase = 0.0
        self.recording = False

    def set_recording(self, recording: bool) -> None:
        self.recording = recording
        self.update()

    def set_level(self, level: float) -> None:
        noise_floor = 0.0003
        full_voice = 0.008
        self.target_level = max(0.0, min(1.0, math.log(max(level, noise_floor) / noise_floor)
                                         / math.log(full_voice / noise_floor)))

    def tick(self, dt: float) -> None:
        response = 18 if self.target_level > self.level else 8
        self.level += (self.target_level - self.level) * min(1.0, dt * response)
        self.phase = (self.phase + dt * (0.9 + (0.2 if self.recording else 0) + self.level * 3)) % (2 * math.pi)
        self.update()

    def reset(self) -> None:
        self.level = 0.0
        self.target_level = 0.0
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(3, 7, self.width() - 6, self.height() - 10)
        path = QPainterPath()
        path.addRoundedRect(body, body.height() / 2, body.height() / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(path, QColor(1, 4, 12, 250))
        painter.save()
        painter.setClipPath(path)
        breath = (1 + math.sin(self.phase)) / 2
        activity = min(1.65, self.level * 0.65 + (1.0 if self.recording else 0.0))
        glow = QLinearGradient(0, body.top(), 0, body.bottom())
        glow.setColorAt(0.0, QColor(0, 2, 8, 32))
        glow.setColorAt(0.24, QColor(2, 7, 18, 88))
        glow.setColorAt(0.42, QColor(4, 13, 34, 148))
        glow.setColorAt(0.60, QColor(8, 28, 70, 205))
        glow.setColorAt(0.82, QColor(22 + round(26 * activity + 5 * breath),
                                    66 + round(31 * activity + 5 * breath),
                                    150 + round(33 * activity), 242))
        glow.setColorAt(1.0, QColor(39 + round(44 * activity + 8 * breath),
                                   102 + round(50 * activity + 7 * breath),
                                   214 + round(20 * activity + 5 * breath), 255))
        painter.fillRect(body, glow)

        for offset, alpha in ((-9, 70), (2, 130)):
            wave = QPainterPath()
            wave.moveTo(body.left(), body.bottom())
            for step in range(59):
                x = body.left() + body.width() * step / 58
                distance = (x - body.left()) / body.width()
                y = (body.top() + body.height() * (0.62 - 0.10 * self.level
                                                    - (0.03 if self.recording else 0)) + offset
                     + (2.5 + (1.0 if self.recording else 0) + 25 * self.level)
                     * math.sin(distance * 2.4 * math.pi - self.phase * 1.45)
                     + (1 + 7 * self.level) * math.sin(distance * 4.2 * math.pi + self.phase * 0.8))
                wave.lineTo(x, y)
            wave.lineTo(body.right(), body.bottom())
            wave.closeSubpath()
            wave_light = QLinearGradient(0, body.top(), 0, body.bottom())
            wave_light.setColorAt(0.0, QColor(70, 130, 235, 0))
            wave_light.setColorAt(0.36, QColor(72, 137, 250, 0))
            wave_light.setColorAt(0.52, QColor(82, 155, 255,
                                               round((24 + 115 * self.level) * alpha / 130)))
            wave_light.setColorAt(0.78, QColor(113, 181, 255, round(alpha * 0.55 * (1 + 0.35 * activity))))
            wave_light.setColorAt(1.0, QColor(170, 214, 255, round(alpha * (1 + 0.35 * activity))))
            painter.fillPath(wave, wave_light)
        painter.restore()
        painter.setPen(QPen(QColor(27, 42, 65, 185), 1.25))
        painter.drawPath(path)


class CircleIconButton(QPushButton):
    def __init__(self, icon_name: str, label: str, parent=None) -> None:
        super().__init__(label, parent)
        self.icon_name = icon_name
        self.setFixedSize(54, 54)
        self.setToolTip(label)
        self.setAccessibleName(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(29, 33, 43, 220 if self.underMouse() else 202)
        if not self.isEnabled():
            fill.setAlpha(182)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(206, 225, 244, 36), 1))
        painter.drawEllipse(QRectF(1, 1, 52, 52))
        pen = QPen(QColor(238, 245, 255, 225 if self.isEnabled() else 158), 2.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.icon_name == "mic":
            painter.drawRoundedRect(QRectF(23, 14, 8, 18), 4, 4)
            painter.drawArc(QRectF(18, 20, 18, 18), 180 * 16, 180 * 16)
            painter.drawLine(27, 38, 27, 43)
            painter.drawLine(22, 43, 32, 43)
        elif self.icon_name == "stop":
            painter.setBrush(pen.color())
            painter.drawRoundedRect(QRectF(20, 20, 14, 14), 3, 3)
        elif self.icon_name == "close":
            painter.drawLine(20, 20, 34, 34)
            painter.drawLine(34, 20, 20, 34)
        elif self.icon_name == "copy":
            painter.drawRoundedRect(QRectF(21, 18, 17, 20), 3, 3)
            painter.drawLine(17, 20, 17, 36)
            painter.drawLine(17, 36, 33, 36)
        elif self.icon_name == "device":
            painter.drawRoundedRect(QRectF(17, 18, 20, 18), 4, 4)
            painter.drawLine(22, 41, 32, 41)
            painter.drawLine(27, 36, 27, 41)
