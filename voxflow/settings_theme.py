"""Light and dark palettes for the settings window, following the Windows color scheme."""

import os
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class Theme:
    name: str
    window: str
    sidebar: str
    card: str
    border: str
    divider: str
    text: str
    muted: str
    accent: str
    hover: str
    selected: str
    field: str
    popup: str
    switch_off: str
    knob: str
    icon: str
    icon_active: str


LIGHT = Theme("light", window="#FFFFFF", sidebar="#F9F9F9", card="#FFFFFF", border="#E3E3E3",
              divider="#ECECEC", text="#1F1F1F", muted="#6E6E6E", accent="#2F7CF6", hover="#F0F0F0",
              selected="#ECECEC", field="#FFFFFF", popup="#FFFFFF", switch_off="#C9C9C9", knob="#FFFFFF",
              icon="#5D5D5D", icon_active="#1F1F1F")
DARK = Theme("dark", window="#212121", sidebar="#181818", card="#2A2A2A", border="#3A3A3A",
             divider="#363636", text="#ECECEC", muted="#A3A3A3", accent="#3D8BFF", hover="#333333",
             selected="#383838", field="#303030", popup="#2E2E2E", switch_off="#5C5C5C", knob="#FFFFFF",
             icon="#B4B4B4", icon_active="#FFFFFF")


def current_theme() -> Theme:
    override = os.environ.get("VOXFLOW_THEME", "")
    if override in ("light", "dark"):
        return DARK if override == "dark" else LIGHT
    app = QGuiApplication.instance()
    scheme = app.styleHints().colorScheme() if app is not None else Qt.ColorScheme.Unknown
    return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


def stylesheet(theme: Theme) -> str:
    t = theme
    return f"""
        QWidget#settingsWindow {{ background: {t.window}; color: {t.text};
            font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 14px; }}
        QFrame#sidebar {{ background: {t.sidebar}; border: none; border-right: 1px solid {t.divider}; }}
        QLabel {{ color: {t.text}; background: transparent; }}
        QLabel#sidebarTitle {{ font-size: 20px; font-weight: 650; }}
        QLabel#pageTitle {{ font-size: 26px; font-weight: 650; }}
        QLabel#sectionTitle {{ font-size: 15px; font-weight: 600; }}
        QLabel#rowTitle {{ font-size: 14px; font-weight: 500; }}
        QLabel#rowDesc, QLabel#note {{ color: {t.muted}; font-size: 12px; }}
        QListWidget {{ background: transparent; border: none; outline: none; color: {t.text}; }}
        QListWidget::item {{ padding: 8px 10px; margin: 1px 0; border-radius: 8px; }}
        QListWidget::item:selected {{ background: {t.selected}; color: {t.text}; }}
        QListWidget::item:hover:!selected {{ background: {t.hover}; }}
        QScrollArea, QScrollArea > QWidget > QWidget#page {{ background: transparent; border: none; }}
        QFrame#card {{ background: {t.card}; border: 1px solid {t.border}; border-radius: 14px; }}
        QFrame#divider {{ background: {t.divider}; border: none; }}
        QComboBox, QFontComboBox, QSpinBox, QLineEdit {{ background: {t.field}; color: {t.text};
            border: 1px solid {t.border}; border-radius: 8px; padding: 5px 10px; min-height: 22px;
            selection-background-color: {t.accent}; }}
        QComboBox, QFontComboBox {{ padding-right: 34px; combobox-popup: 0; }}
        QComboBox:hover, QFontComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: {t.muted}; }}
        QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border: 1px solid {t.accent}; }}
        QComboBox::drop-down, QFontComboBox::drop-down {{ width: 30px; border: none; background: transparent; }}
        QComboBox::down-arrow, QFontComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}
        QFrame#comboPopup {{ background: transparent; border: none; }}
        QComboBox QAbstractItemView {{ background: {t.popup}; color: {t.text}; border: 1px solid {t.border};
            border-radius: 10px; padding: 4px; outline: none; selection-background-color: {t.hover};
            selection-color: {t.text}; }}
        QComboBox QAbstractItemView::item {{ min-height: 32px; padding: 0 10px; border-radius: 6px; }}
        QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {{
            background: {t.hover}; color: {t.text}; }}
        QPushButton#secondary, QPushButton#colorButton {{ background: {t.field}; color: {t.text};
            border: 1px solid {t.border}; border-radius: 8px; padding: 6px 14px; min-height: 20px; }}
        QPushButton#colorButton {{ text-align: left; padding-left: 10px; }}
        QPushButton#secondary:hover, QPushButton#colorButton:hover {{ background: {t.hover}; }}
        QPushButton#secondary:disabled {{ color: {t.muted}; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
        QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 3px; min-height: 30px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QToolTip {{ background: {t.popup}; color: {t.text}; border: 1px solid {t.border}; padding: 4px 6px; }}
    """
