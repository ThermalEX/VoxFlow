"""The first-run tutorial: language, look, microphone, downloads, a first try, tips. Shown once; restartable."""

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .catalog import builtin_catalog
from .color_themes import PRESETS, saved_color_theme
from .download_panel import DownloadPanel
from .hotkeys import saved as saved_hotkey
from .i18n import tr
from .mic_meter import MicMeter
from .paths import DATA_ROOT
from .settings_theme import THEME_CHOICES, stylesheet
from .settings_widgets import CheckBox, SegmentedControl, SettingsComboBox, ThemeSwatch
from .ui_icons import app_icon

DONE_SETTING = "onboarding/done"
PRESELECT = ["asr-sensevoice", "llama-vulkan", "rewrite-v4-q8"]
STEPS = 6


def should_show_onboarding(settings: QSettings) -> bool:
    return str(settings.value(DONE_SETTING, "false")).lower() not in ("true", "1")


class StepDots(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(STEPS * 16, 10)
        self.current = 0
        self.colors = ("#3D8BFF", "#555555")

    def set_current(self, index: int) -> None:
        self.current = index
        self.update()

    def set_colors(self, active: str, idle: str) -> None:
        self.colors = (active, idle)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(STEPS):
            painter.setBrush(QColor(self.colors[0] if index <= self.current else self.colors[1]))
            painter.drawEllipse(QRectF(index * 16 + 1, 1, 8, 8))
        painter.end()


class OverlayPreview(QWidget):
    """A small picture of the voice overlay in the chosen colors."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(260, 150)
        self.background_color = QColor("#438aee")
        self.capsule_color = QColor("#2766d6")

    def set_colors(self, background: str, capsule: str) -> None:
        self.background_color = QColor(background)
        self.capsule_color = QColor(capsule)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QRadialGradient(QPointF(130, 150), 170)
        light = QColor(self.background_color)
        light.setAlpha(170)
        glow.setColorAt(0, light)
        fade = QColor(self.background_color)
        fade.setAlpha(0)
        glow.setColorAt(1, fade)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(QRectF(0, 0, 260, 150), 16, 16)
        painter.setBrush(QColor(255, 255, 255, 215))
        painter.drawRoundedRect(QRectF(40, 34, 180, 12), 6, 6)
        painter.drawRoundedRect(QRectF(60, 54, 140, 12), 6, 6)
        capsule = QLinearGradient(QPointF(95, 0), QPointF(165, 0))
        capsule.setColorAt(0, self.capsule_color.lighter(135))
        capsule.setColorAt(1, self.capsule_color)
        painter.setBrush(capsule)
        painter.drawRoundedRect(QRectF(95, 96, 70, 30), 15, 15)
        painter.end()


class OnboardingWindow(QWidget):
    finished = Signal()

    def __init__(self, settings: QSettings, settings_window, downloads, meter: MicMeter | None = None,
                 has_nvidia=None) -> None:
        super().__init__()
        self.settings = settings
        self.settings_window = settings_window
        self.meter = meter if meter is not None else MicMeter()
        self._texts: list[tuple] = []
        self._loaded_downloads = False
        self.setObjectName("settingsWindow")
        self.setWindowIcon(app_icon())
        self._bind(self.setWindowTitle, "onboarding.window_title")
        self.resize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 26, 36, 22)
        root.setSpacing(14)
        top = QHBoxLayout()
        self.dots = StepDots()
        top.addWidget(self.dots, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        self.skip_button = self._button("onboarding.skip", "secondary", self._finish)
        top.addWidget(self.skip_button)
        root.addLayout(top)

        self.steps = QStackedWidget()
        for build in (self._step_welcome, self._step_look, self._step_microphone,
                      lambda: self._step_downloads(downloads, has_nvidia), self._step_try, self._step_tips):
            self.steps.addWidget(build())
        root.addWidget(self.steps, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.back_button = self._button("onboarding.back", "secondary", lambda: self._go(-1))
        self.next_button = self._button("onboarding.next", "primary", lambda: self._go(1))
        bottom.addWidget(self.back_button)
        bottom.addWidget(self.next_button)
        root.addLayout(bottom)

        settings_window.palette_changed.connect(self.apply_theme)
        settings_window.language_changed.connect(lambda _choice: self.retranslate())
        settings_window.color_theme_changed.connect(self._show_color_theme)
        self.meter.level.connect(lambda value: self.mic_level.setValue(round(value * 100)))
        self.apply_theme(settings_window.theme)
        self._show_color_theme(saved_color_theme(settings))
        self._show_step(0)

    # Building blocks ----------------------------------------------------------------------------

    def _bind(self, setter, key: str, **values) -> None:
        setter(tr(key, **values))
        self._texts.append((setter, key, values))

    def _label(self, key: str | None, name: str, wrap: bool = True) -> QLabel:
        label = QLabel()
        label.setObjectName(name)
        label.setWordWrap(wrap)
        if key:
            self._bind(label.setText, key)
        return label

    def _button(self, key: str, name: str, handler) -> QPushButton:
        button = QPushButton()
        button.setObjectName(name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bind(button.setText, key)
        button.clicked.connect(handler)
        return button

    def _page(self, title_key: str, desc_key: str | None) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._label(title_key, "pageTitle"))
        if desc_key:
            layout.addWidget(self._label(desc_key, "rowDesc"))
        layout.addSpacing(8)
        return page, layout

    # Steps ----------------------------------------------------------------------------------------

    def _step_welcome(self) -> QWidget:
        page, layout = self._page("onboarding.welcome_title", "onboarding.welcome_desc")
        layout.addWidget(self._label("field.language", "rowTitle"))
        self.language_control = SegmentedControl([("system", ""), ("en", "English"), ("zh", "简体中文")])
        self._bind(lambda text: self.language_control.set_texts({"system": text}), "language.system")
        saved = str(self.settings.value("ui/language", "system"))
        self.language_control.buttons[saved if saved in self.language_control.buttons else "system"].setChecked(True)
        self.language_control.changed.connect(self._choose_language)
        layout.addWidget(self.language_control, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _step_look(self) -> QWidget:
        page, layout = self._page("onboarding.look_title", "onboarding.look_desc")
        row = QHBoxLayout()
        row.setSpacing(28)
        column = QVBoxLayout()
        column.setSpacing(8)
        column.addWidget(self._label("field.theme", "rowTitle"))
        self.mode_control = SegmentedControl([(value, "") for value, _key in THEME_CHOICES])
        self._bind(lambda _text: self.mode_control.set_texts({value: tr(key) for value, key in THEME_CHOICES}),
                   "theme.system")
        saved = str(self.settings.value("ui/theme", "system"))
        self.mode_control.buttons[saved if saved in self.mode_control.buttons else "system"].setChecked(True)
        self.mode_control.changed.connect(self._choose_mode)
        column.addWidget(self.mode_control, 0, Qt.AlignmentFlag.AlignLeft)
        column.addSpacing(10)
        column.addWidget(self._label("field.color_theme", "rowTitle"))
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.color_theme_buttons: dict[str, ThemeSwatch] = {}
        for theme in PRESETS:
            swatch = ThemeSwatch(theme.background, theme.capsule)
            self._bind(swatch.setToolTip, theme.name_key)
            swatch.clicked.connect(lambda _checked=False, value=theme.id: self.settings_window.select_color_theme(value))
            self.color_theme_buttons[theme.id] = swatch
            chips.addWidget(swatch)
        chips.addStretch(1)
        column.addLayout(chips)
        column.addWidget(self._label("onboarding.look_custom", "rowDesc"))
        column.addStretch(1)
        row.addLayout(column, 1)
        self.preview = OverlayPreview()
        row.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _step_microphone(self) -> QWidget:
        page, layout = self._page("onboarding.mic_title", "onboarding.mic_desc")
        self.mic_box = SettingsComboBox()
        self.mic_box.setFixedWidth(420)
        self.mic_box.currentIndexChanged.connect(self._choose_microphone)
        layout.addWidget(self.mic_box, 0, Qt.AlignmentFlag.AlignLeft)
        self.mic_level = QProgressBar()
        self.mic_level.setObjectName("downloadProgress")
        self.mic_level.setRange(0, 100)
        self.mic_level.setTextVisible(False)
        self.mic_level.setFixedSize(420, 8)
        layout.addWidget(self.mic_level)
        self.mic_missing = self._label("onboarding.mic_missing", "note")
        layout.addWidget(self.mic_missing)
        layout.addStretch(1)
        return page

    def _step_downloads(self, downloads, has_nvidia) -> QWidget:
        page, layout = self._page("onboarding.download_title", "onboarding.download_desc")
        self.download_panel = DownloadPanel(self.settings, downloads, root=DATA_ROOT, compact=True,
                                            has_nvidia=has_nvidia)
        layout.addWidget(self.download_panel)
        layout.addStretch(1)
        return page

    def _step_try(self) -> QWidget:
        page, layout = self._page("onboarding.try_title", None)
        self.try_text = self._label(None, "rowTitle")
        layout.addWidget(self.try_text)
        layout.addWidget(self._label("onboarding.try_example", "rowDesc"))
        layout.addWidget(self._label("onboarding.try_result", "rowDesc"))
        layout.addWidget(self._label("onboarding.try_keys", "rowDesc"))
        self.speech_missing = self._label("onboarding.try_missing", "note")
        layout.addWidget(self.speech_missing)
        layout.addStretch(1)
        return page

    def _step_tips(self) -> QWidget:
        page, layout = self._page("onboarding.tips_title", None)
        for key in ("onboarding.tip_commands", "onboarding.tip_continue", "onboarding.tip_undo",
                    "onboarding.tip_tray"):
            layout.addWidget(self._label(key, "rowDesc"))
        layout.addStretch(1)
        return page

    # Navigation -----------------------------------------------------------------------------------

    def _go(self, step: int) -> None:
        target = self.steps.currentIndex() + step
        if target >= STEPS:
            self._finish()
        else:
            self._show_step(max(0, target))

    def _show_step(self, index: int) -> None:
        self.steps.setCurrentIndex(index)
        self.dots.set_current(index)
        self.back_button.setEnabled(index > 0)
        self.next_button.setText(tr("onboarding.start" if index == STEPS - 1 else "onboarding.next"))
        if index == 2:
            self._fill_microphones()
            self.meter.start(self.mic_box.currentData())
        else:
            self.meter.stop()
        if index == 3 and not self._loaded_downloads:
            self._loaded_downloads = True
            self.download_panel.load(preselect=PRESELECT)
        if index == 4:
            self.try_text.setText(tr("onboarding.try_text", hotkey=saved_hotkey(self.settings, "record").text))
            speech = next(item for item in builtin_catalog() if item.kind == "asr")
            self.speech_missing.setVisible(not (DATA_ROOT / speech.check).is_file())

    def _finish(self) -> None:
        self.settings.setValue(DONE_SETTING, True)
        self.meter.stop()
        self.finished.emit()
        self.close()

    def closeEvent(self, event) -> None:
        # Closing the window counts as skipping, so the tutorial does not come back at every start.
        self.settings.setValue(DONE_SETTING, True)
        self.meter.stop()
        super().closeEvent(event)

    # Choices --------------------------------------------------------------------------------------

    def _choose_language(self, value: str) -> None:
        box = self.settings_window.language_box
        box.setCurrentIndex(max(0, box.findData(value)))

    def _choose_mode(self, value: str) -> None:
        box = self.settings_window.theme_box
        box.setCurrentIndex(max(0, box.findData(value)))

    def _fill_microphones(self) -> None:
        source = self.settings_window.device_box
        self.mic_box.blockSignals(True)
        self.mic_box.clear()
        for index in range(source.count()):
            self.mic_box.addItem(source.itemText(index), source.itemData(index))
        self.mic_box.setCurrentIndex(source.currentIndex())
        self.mic_box.blockSignals(False)
        self.mic_missing.setVisible(source.count() == 0)

    def _choose_microphone(self, index: int) -> None:
        if index < 0:
            return
        self.settings_window.device_box.setCurrentIndex(index)
        self.meter.start(self.mic_box.currentData())

    # Look -----------------------------------------------------------------------------------------

    def _show_color_theme(self, theme) -> None:
        self.preview.set_colors(theme.background, theme.capsule)
        for theme_id, swatch in self.color_theme_buttons.items():
            swatch.setChecked(theme_id == theme.id)

    def apply_theme(self, theme) -> None:
        self.setStyleSheet(stylesheet(theme))
        self.dots.set_colors(theme.accent, theme.border)
        for kind in (ThemeSwatch, CheckBox, SettingsComboBox):
            for widget in self.findChildren(kind):
                widget.set_theme(theme)
        self.download_panel.set_theme(theme)

    def retranslate(self) -> None:
        for setter, key, values in self._texts:
            setter(tr(key, **values))
        self.next_button.setText(tr("onboarding.start" if self.steps.currentIndex() == STEPS - 1
                                    else "onboarding.next"))
        self.download_panel.retranslate()
        if self.steps.currentIndex() == 4:
            self._show_step(4)
