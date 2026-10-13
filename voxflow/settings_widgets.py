"""Building blocks for the settings window: rows grouped in cards, switches and themed dropdowns."""

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QComboBox, QFontComboBox, QFrame, QHBoxLayout, QLabel, QListView, QStyle,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

from .settings_theme import LIGHT, Theme
from .ui_icons import symbol_pixmap


class _Chevron(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.angle = 0.0
        self.set_color(LIGHT.icon)

    def set_color(self, color: str) -> None:
        self._symbol = symbol_pixmap("keyboard_arrow_down", 18, color)
        self.update()

    def set_angle(self, angle: float) -> None:
        self.angle = angle
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(9, 9)
        painter.rotate(self.angle)
        painter.drawPixmap(-9, -9, self._symbol)
        painter.end()


class ComboItemDelegate(QStyledItemDelegate):
    """Roomy dropdown rows with a hover highlight and a check mark on the current choice."""

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self.combo = combo
        self.theme = LIGHT

    def sizeHint(self, option, index) -> QSize:
        hint = super().sizeHint(option, index)
        return QSize(hint.width() + 44, 34)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(2, 1, -2, -1)
        if option.state & (QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_Selected):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme.hover))
            painter.drawRoundedRect(rect, 6, 6)
        text_rect = rect.adjusted(10, 0, -32, 0).toRect()
        text = option.fontMetrics.elidedText(str(index.data() or ""), Qt.TextElideMode.ElideRight, text_rect.width())
        painter.setPen(QColor(self.theme.text))
        painter.setFont(option.font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        if index.row() == self.combo.currentIndex():
            pen = QPen(QColor(self.theme.accent), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            right, middle = rect.right() - 12, rect.center().y()
            check = QPainterPath(QPointF(right - 11, middle))
            check.lineTo(right - 7, middle + 4)
            check.lineTo(right, middle - 4)
            painter.drawPath(check)
        painter.restore()


class _ThemedCombo:
    """Shared dropdown behavior: rotating chevron and a frameless rounded popup below the field."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.chevron = _Chevron(self)
        self._chevron_animation = QVariantAnimation(self)
        self._chevron_animation.setDuration(150)
        self._chevron_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._chevron_animation.valueChanged.connect(self.chevron.set_angle)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        popup = self.view().window()
        popup.setObjectName("comboPopup")
        popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                             | Qt.WindowType.NoDropShadowWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_theme(self, theme: Theme) -> None:
        self.chevron.set_color(theme.icon)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.chevron.move(self.width() - 28, (self.height() - self.chevron.height()) // 2)
        self.chevron.raise_()

    def _rotate_chevron(self, angle: float) -> None:
        self._chevron_animation.stop()
        self._chevron_animation.setStartValue(self.chevron.angle)
        self._chevron_animation.setEndValue(angle)
        self._chevron_animation.start()

    def showPopup(self) -> None:
        super().showPopup()
        self._rotate_chevron(180.0)

    def hidePopup(self) -> None:
        super().hidePopup()
        self._rotate_chevron(0.0)


class SettingsComboBox(_ThemedCombo, QComboBox):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setView(QListView())
        self.delegate = ComboItemDelegate(self)
        self.view().setItemDelegate(self.delegate)
        self.view().setMouseTracking(True)

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        self.delegate.theme = theme


class SettingsFontComboBox(_ThemedCombo, QFontComboBox):
    pass


class ToggleSwitch(QAbstractButton):
    """An on/off switch with a sliding knob; behaves like a checkable button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme = LIGHT
        self._offset = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._set_offset)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(40, 22)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def _set_offset(self, value) -> None:
        self._offset = float(value)
        self.update()

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(0, 0, 40, 22).translated((self.width() - 40) / 2, (self.height() - 22) / 2)
        off, on = QColor(self.theme.switch_off), QColor(self.theme.accent)
        mix = QColor(round(off.red() + (on.red() - off.red()) * self._offset),
                     round(off.green() + (on.green() - off.green()) * self._offset),
                     round(off.blue() + (on.blue() - off.blue()) * self._offset))
        if not self.isEnabled():
            mix.setAlpha(110)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(mix)
        painter.drawRoundedRect(track, 11, 11)
        painter.setBrush(QColor(self.theme.knob))
        knob_x = track.left() + 3 + (track.width() - 22) * self._offset
        painter.drawEllipse(QRectF(knob_x, track.top() + 3, 16, 16))
        painter.end()


class SettingRow(QWidget):
    """A card row: title and an optional description on the left, the control on the right."""

    def __init__(self, control: QWidget | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(18)
        self.text_column = QVBoxLayout()
        self.text_column.setSpacing(3)
        self.title = QLabel()
        self.title.setObjectName("rowTitle")
        self.desc = QLabel()
        self.desc.setObjectName("rowDesc")
        self.desc.setWordWrap(True)
        self.desc.hide()
        self.text_column.addWidget(self.title)
        self.text_column.addWidget(self.desc)
        layout.addLayout(self.text_column, 1)
        self.control_layout = QHBoxLayout()
        self.control_layout.setSpacing(8)
        layout.addLayout(self.control_layout)
        if control is not None:
            self.control_layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_desc(self, text: str) -> None:
        self.desc.setText(text)
        self.desc.setVisible(bool(text))


class SettingsCard(QFrame):
    """Rounded group of rows separated by hairlines; hidden rows take their divider with them."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.rows: list[QWidget] = []
        self.dividers: list[QFrame] = []

    def add_row(self, row: QWidget) -> QWidget:
        if self.rows:
            divider = QFrame()
            divider.setObjectName("divider")
            divider.setFixedHeight(1)
            self._layout.addWidget(divider)
            self.dividers.append(divider)
        self.rows.append(row)
        self._layout.addWidget(row)
        return row

    def refresh(self) -> None:
        seen_visible = False
        for index, row in enumerate(self.rows):
            if index:
                self.dividers[index - 1].setVisible(seen_visible and not row.isHidden())
            seen_visible = seen_visible or not row.isHidden()
