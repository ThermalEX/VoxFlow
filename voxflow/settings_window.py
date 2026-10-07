"""Standalone, light settings window for VoxFlow."""

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QColorDialog, QFontComboBox, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .appearance import DEFAULT_BACKGROUND, DEFAULT_CAPSULE, DEFAULT_FONT, DEFAULT_TEXT_SIZE, saved_color


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
        self.setMinimumSize(680, 470)
        self.resize(720, 500)
        self.setObjectName("settingsWindow")
        self.setStyleSheet("""
            QWidget#settingsWindow { background: #FFFFFF; color: #20242B; font-family: 'Segoe UI'; }
            QLabel { color: #20242B; font-size: 14px; background: transparent; }
            QLabel#pageTitle { font-size: 24px; font-weight: 650; }
            QLabel#description { color: #66717D; font-size: 13px; }
            QLabel#fieldTitle { font-weight: 600; }
            QListWidget { background: #F5F6F8; border: none; border-radius: 12px;
                          color: #3B4652; font-size: 14px; padding: 8px; outline: none; }
            QListWidget::item { padding: 12px 14px; margin: 3px; border-radius: 8px; }
            QListWidget::item:selected { background: #E6EDF8; color: #153B75; }
            QComboBox, QFontComboBox, QSpinBox { background: #FFFFFF; color: #20242B;
                border: 1px solid #CFD6DF; border-radius: 8px; padding: 6px 10px;
                min-height: 29px; }
            QComboBox:focus, QFontComboBox:focus, QSpinBox:focus { border: 2px solid #5C87C7; }
            QPushButton#colorButton { background: #FFFFFF; color: #20242B;
                border: 1px solid #CFD6DF; border-radius: 8px; padding: 7px 12px;
                text-align: left; min-height: 30px; }
            QPushButton#colorButton:hover { background: #F3F6FA; }
            QPushButton#resetButton { background: #FFFFFF; color: #2A5083;
                border: 1px solid #CFD6DF; border-radius: 8px; padding: 8px 14px; }
            QPushButton#resetButton:hover { background: #F3F6FA; }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 30, 24)
        root.setSpacing(28)
        self.categories = QListWidget()
        self.categories.setFixedWidth(190)
        self.categories.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.addItems(["Personalization", "App settings"])
        self.categories.setAccessibleName("Settings categories")
        root.addWidget(self.categories)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.pages.addWidget(self._build_personalization())
        self.pages.addWidget(self._build_app_settings())
        self.categories.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.categories.setCurrentRow(0)

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
        self.font_box = QFontComboBox()
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
        reset.clicked.connect(self._reset_appearance)
        layout.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _build_app_settings(self) -> QWidget:
        page, layout = self._page("App settings", "Choose how VoxFlow listens and displays speech.")
        self.device_box = QComboBox()
        self.device_box.setAccessibleName("Microphone")
        self._field(layout, "Microphone", self.device_box)
        self.alignment_box = QComboBox()
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
