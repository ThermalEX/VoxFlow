"""Standalone, light settings window for VoxFlow."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSettings, QSize, Qt, Signal, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QColorDialog, QFontComboBox, QFrame,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .appearance import DEFAULT_BACKGROUND, DEFAULT_CAPSULE, DEFAULT_FONT, DEFAULT_TEXT_SIZE, saved_color
from .ui_icons import app_icon, line_icon


class _Chevron(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.angle = 0.0

    def set_angle(self, angle: float) -> None:
        self.angle = angle
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(9, 9)
        painter.rotate(self.angle)
        pen = QPen(QColor("#56677A"), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(-4, -1, 0, 3)
        painter.drawLine(0, 3, 4, -1)
        painter.end()


class _AnimatedCombo:
    """Keep a consistent chevron while retaining Qt's keyboard and popup behavior."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.chevron = _Chevron(self)
        self._chevron_animation = QVariantAnimation(self)
        self._chevron_animation.setDuration(150)
        self._chevron_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._chevron_animation.valueChanged.connect(self.chevron.set_angle)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.chevron.move(self.width() - 33, (self.height() - self.chevron.height()) // 2)
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


class SettingsComboBox(_AnimatedCombo, QComboBox):
    pass


class SettingsFontComboBox(_AnimatedCombo, QFontComboBox):
    pass


class SettingsWindow(QWidget):
    font_changed = Signal(str)
    text_size_changed = Signal(int)
    background_color_changed = Signal(QColor)
    capsule_color_changed = Signal(QColor)
    alignment_changed = Signal(str)

    def __init__(self, settings: QSettings) -> None:
        super().__init__()
        self.settings = settings
        self.setWindowTitle("VoxFlow Settings")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(700, 490)
        self.resize(760, 520)
        self.setObjectName("settingsWindow")
        self.setStyleSheet("""
            QWidget#settingsWindow { background: #FFFFFF; color: #20242B; font-family: 'Segoe UI'; }
            QFrame#sidebar { background: #F6F8FB; border-radius: 15px; }
            QLabel { color: #20242B; font-size: 14px; background: transparent; }
            QLabel#brand { font-size: 15px; font-weight: 650; color: #172B48; }
            QLabel#eyebrow { color: #8693A3; font-size: 10px; font-weight: 600; }
            QLabel#pageTitle { font-size: 24px; font-weight: 650; }
            QLabel#description { color: #66717D; font-size: 13px; }
            QLabel#fieldTitle { font-weight: 600; }
            QListWidget { background: transparent; border: none;
                          color: #3B4652; font-size: 14px; outline: none; }
            QListWidget::item { padding: 12px 10px; margin: 3px 0; border-radius: 9px; }
            QListWidget::item:selected { background: #E2ECFA; color: #153B75; }
            QListWidget::item:hover:!selected { background: #ECF1F7; }
            QComboBox, QFontComboBox, QSpinBox { background: #FFFFFF; color: #20242B;
                border: 1px solid #CFD6DF; border-radius: 9px; padding: 6px 42px 6px 12px;
                min-height: 29px; }
            QComboBox:hover, QFontComboBox:hover, QSpinBox:hover { border-color: #9BAFC8; }
            QComboBox:focus, QFontComboBox:focus, QSpinBox:focus { border: 2px solid #5C87C7; }
            QComboBox::drop-down, QFontComboBox::drop-down { width: 34px; border: none;
                background: transparent; }
            QComboBox::down-arrow, QFontComboBox::down-arrow { image: none; width: 0px; height: 0px; }
            QComboBox QAbstractItemView { background: #FFFFFF; color: #20242B;
                border: 1px solid #CFD6DF; selection-background-color: #E2ECFA;
                selection-color: #153B75; outline: none; }
            QPushButton#colorButton { background: #FFFFFF; color: #20242B;
                border: 1px solid #CFD6DF; border-radius: 9px; padding: 7px 12px;
                text-align: left; min-height: 30px; }
            QPushButton#colorButton:hover { background: #F3F6FA; }
            QPushButton#resetButton { background: #FFFFFF; color: #2A5083;
                border: 1px solid #CFD6DF; border-radius: 8px; padding: 8px 14px; }
            QPushButton#resetButton:hover { background: #F3F6FA; }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 30, 20)
        root.setSpacing(30)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(204)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(13, 18, 13, 12)
        sidebar_layout.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(29, 29))
        brand_row.addWidget(mark)
        brand = QLabel("VoxFlow")
        brand.setObjectName("brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        sidebar_layout.addLayout(brand_row)
        eyebrow = QLabel("PREFERENCES")
        eyebrow.setObjectName("eyebrow")
        sidebar_layout.addSpacing(24)
        sidebar_layout.addWidget(eyebrow)
        self.categories = QListWidget()
        self.categories.setIconSize(QSize(20, 20))
        self.categories.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.addItem(QListWidgetItem(line_icon("personalize"), "Personalization"))
        self.categories.addItem(QListWidgetItem(line_icon("settings"), "App settings"))
        self.categories.setAccessibleName("Settings categories")
        self.categories.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        sidebar_layout.addWidget(self.categories, 1)
        root.addWidget(sidebar)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.pages.addWidget(self._build_personalization())
        self.pages.addWidget(self._build_app_settings())
        self._page_effects = []
        for index in range(self.pages.count()):
            effect = QGraphicsOpacityEffect(self.pages.widget(index))
            self.pages.widget(index).setGraphicsEffect(effect)
            self._page_effects.append(effect)
        self._page_animation: QPropertyAnimation | None = None
        self._entrance_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._entrance_animation.setDuration(190)
        self._entrance_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.categories.currentRowChanged.connect(self._switch_category)
        self.categories.setCurrentRow(0)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if QApplication.platformName() == "offscreen":
            self.setWindowOpacity(1.0)
            return
        self._entrance_animation.stop()
        self._entrance_animation.setStartValue(0.72)
        self._entrance_animation.setEndValue(1.0)
        self.setWindowOpacity(0.72)
        self._entrance_animation.start()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def _switch_category(self, row: int) -> None:
        if row < 0:
            return
        if self._page_animation is not None:
            self._page_animation.stop()
        self.pages.setCurrentIndex(row)
        for index in range(self.categories.count()):
            name = "personalize" if index == 0 else "settings"
            color = "#285C9D" if index == row else "#657486"
            self.categories.item(index).setIcon(line_icon(name, color))
        effect = self._page_effects[row]
        if not self.isVisible():
            effect.setOpacity(1.0)
            return
        effect.setOpacity(0.3)
        self._page_animation = QPropertyAnimation(effect, b"opacity", self)
        self._page_animation.setDuration(190)
        self._page_animation.setStartValue(0.3)
        self._page_animation.setEndValue(1.0)
        self._page_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._page_animation.start()

    @staticmethod
    def _page(title: str, description: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        subtitle = QLabel(description)
        subtitle.setObjectName("description")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(13)
        return page, layout

    @staticmethod
    def _field(layout: QVBoxLayout, title: str, control: QWidget) -> None:
        label = QLabel(title)
        label.setObjectName("fieldTitle")
        layout.addWidget(label)
        layout.addWidget(control)
        layout.addSpacing(9)

    def _build_personalization(self) -> QWidget:
        page, layout = self._page("Personalization", "Changes appear in the voice overlay immediately.")
        self.font_box = SettingsFontComboBox()
        self.font_box.setAccessibleName("Transcript font")
        self.font_box.setCurrentFont(QFont(str(self.settings.value("appearance/font", DEFAULT_FONT))))
        self.font_box.currentFontChanged.connect(self._set_font)
        self._field(layout, "Transcript font", self.font_box)

        self.text_size_box = QSpinBox()
        self.text_size_box.setRange(14, 48)
        self.text_size_box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.text_size_box.setSuffix(" px")
        self.text_size_box.setAccessibleName("Transcript font size")
        try:
            saved_size = int(self.settings.value("appearance/text_size", DEFAULT_TEXT_SIZE))
        except (TypeError, ValueError):
            saved_size = DEFAULT_TEXT_SIZE
        self.text_size_box.setValue(max(14, min(48, saved_size)))
        self.text_size_box.valueChanged.connect(self._set_text_size)
        self._field(layout, "Text size", self.text_size_box)

        self.background_button = self._color_button("background", "Background color", DEFAULT_BACKGROUND)
        self._field(layout, "Background glow", self.background_button)
        self.capsule_button = self._color_button("capsule", "Capsule color", DEFAULT_CAPSULE)
        self._field(layout, "Capsule glow", self.capsule_button)

        reset = QPushButton("Restore appearance defaults")
        reset.setObjectName("resetButton")
        reset.setIcon(line_icon("restore", "#285C9D"))
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self._reset_appearance)
        layout.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _build_app_settings(self) -> QWidget:
        page, layout = self._page("App settings", "Choose how VoxFlow listens and displays speech.")
        self.device_box = SettingsComboBox()
        self.device_box.setAccessibleName("Microphone")
        self._field(layout, "Microphone", self.device_box)
        self.alignment_box = SettingsComboBox()
        self.alignment_box.setAccessibleName("Transcript alignment")
        for title, value in (("Left", "left"), ("Center", "center"), ("Right", "right")):
            self.alignment_box.addItem(title, value)
        saved = str(self.settings.value("transcript/alignment", "left"))
        self.alignment_box.setCurrentIndex(max(0, self.alignment_box.findData(saved)))
        self.alignment_box.currentIndexChanged.connect(
            lambda _index: self.alignment_changed.emit(str(self.alignment_box.currentData()))
        )
        self._field(layout, "Transcript alignment", self.alignment_box)
        note = QLabel("Confirm inserts the final text into the last active app.")
        note.setObjectName("description")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return page

    def _color_button(self, key: str, label: str, fallback: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("colorButton")
        button.setAccessibleName(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_color(button, saved_color(self.settings.value(f"appearance/{key}_color", fallback), fallback))
        button.clicked.connect(lambda: self._choose_color(key))
        return button

    @staticmethod
    def _show_color(button: QPushButton, color: QColor) -> None:
        swatch = QPixmap(20, 20)
        swatch.fill(Qt.GlobalColor.transparent)
        painter = QPainter(swatch)
        painter.setPen(QColor("#AAB4BF"))
        painter.setBrush(color)
        painter.drawRoundedRect(1, 1, 17, 17, 4, 4)
        painter.end()
        button.setIcon(QIcon(swatch))
        button.setText(f"{color.name().upper()}    Change…")

    def _choose_color(self, key: str) -> None:
        fallback = DEFAULT_BACKGROUND if key == "background" else DEFAULT_CAPSULE
        initial = saved_color(self.settings.value(f"appearance/{key}_color", fallback), fallback)
        chosen = QColorDialog.getColor(initial, self, f"Choose {key} color")
        if chosen.isValid():
            self.set_color(key, chosen)

    def set_color(self, key: str, color: QColor) -> None:
        if key not in {"background", "capsule"} or not color.isValid():
            raise ValueError("Unknown appearance color")
        self.settings.setValue(f"appearance/{key}_color", color.name())
        self._show_color(self.background_button if key == "background" else self.capsule_button, color)
        (self.background_color_changed if key == "background" else self.capsule_color_changed).emit(color)

    def _set_font(self, font: QFont) -> None:
        family = font.family()
        self.settings.setValue("appearance/font", family)
        self.font_changed.emit(family)

    def _set_text_size(self, size: int) -> None:
        self.settings.setValue("appearance/text_size", size)
        self.text_size_changed.emit(size)

    def _reset_appearance(self) -> None:
        self.font_box.setCurrentFont(QFont(DEFAULT_FONT))
        self.text_size_box.setValue(DEFAULT_TEXT_SIZE)
        self.set_color("background", QColor(DEFAULT_BACKGROUND))
        self.set_color("capsule", QColor(DEFAULT_CAPSULE))
