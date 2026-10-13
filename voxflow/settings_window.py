"""VoxFlow settings: sidebar navigation and pages of grouped rows, following the system light/dark scheme."""

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

import PySide6
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSettings, QSize, Qt, Signal, qVersion
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QColorDialog, QFileDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .hotkeys import ACTIONS, DEFAULTS as DEFAULT_HOTKEYS, parse as parse_hotkey, saved as saved_hotkey
from .appearance import DEFAULT_BACKGROUND, DEFAULT_CAPSULE, DEFAULT_FONT, DEFAULT_TEXT_SIZE, saved_color
from .i18n import LANGUAGE_CHOICES, describe_error, resolve, set_language, tr
from .model_catalog import LocalModel, describe as describe_model, discover_models, quant_of
from .rewriter import RewriteConfig
from .settings_theme import Theme, current_theme, stylesheet
from .settings_widgets import (
    HotkeyButton, SettingRow, SettingsCard, SettingsComboBox, SettingsFontComboBox, ToggleSwitch,
)
from .ui_icons import app_icon, line_icon

REPO_ROOT = Path(__file__).resolve().parents[1]
BROWSE = "__browse__"
CATEGORIES = (("settings", "category.general"), ("personalize", "category.appearance"), ("smart", "category.smart"),
              ("shortcuts", "category.shortcuts"), ("about", "category.about"))
HOTKEY_FIELDS = {"record": "field.hotkey_record", "continue": "field.hotkey_continue"}
AUTHOR = "ThermalEX"
REPO_URL = "https://github.com/ThermalEX/VoxFlow"


def app_version() -> str:
    try:
        return package_version("voxflow")
    except PackageNotFoundError:
        return "dev"


def _repo_relative(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _same_path(first: str, second: str) -> bool:
    def absolute(value: str) -> Path:
        path = Path(value).expanduser()
        return (path if path.is_absolute() else REPO_ROOT / path).resolve()

    return bool(first) and bool(second) and absolute(first) == absolute(second)


class SettingsWindow(QWidget):
    font_changed = Signal(str)
    text_size_changed = Signal(int)
    background_color_changed = Signal(QColor)
    capsule_color_changed = Signal(QColor)
    alignment_changed = Signal(str)
    rewrite_changed = Signal()
    language_changed = Signal(str)
    hotkey_capture = Signal(bool)  # True while a shortcut is being recorded

    def __init__(self, settings: QSettings) -> None:
        super().__init__()
        self.settings = settings
        self._texts: list[tuple] = []
        self._model_status: tuple[str, dict] | None = None
        self._test_result: tuple[str, dict] | None = None
        self._rewrite_tester = None
        self._model_lister = None
        self._hotkey_applier = None
        self._hotkey_message: tuple[str, dict] = ("hotkey.help", {})
        self._cards: list[SettingsCard] = []
        self.theme = current_theme()
        # File pickers go through this hook so tests can answer them.
        self.choose_file = lambda title, start, file_filter: QFileDialog.getOpenFileName(
            self, title, start, file_filter)[0]
        set_language(resolve(str(self.settings.value("ui/language", "system"))))
        self._bind(self.setWindowTitle, "settings.title")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(780, 600)
        self.resize(880, 660)
        self.setObjectName("settingsWindow")

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 20, 14, 14)
        sidebar_layout.setSpacing(6)
        heading = QLabel()
        heading.setObjectName("sidebarTitle")
        self._bind(heading.setText, "settings.heading")
        sidebar_layout.addWidget(heading)
        sidebar_layout.addSpacing(12)
        self.categories = QListWidget()
        self.categories.setIconSize(QSize(18, 18))
        self.categories.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for icon, key in CATEGORIES:
            item = QListWidgetItem(line_icon(icon), "")
            self.categories.addItem(item)
            self._bind(item.setText, key)
        self._bind(self.categories.setAccessibleName, "settings.categories")
        self.categories.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        sidebar_layout.addWidget(self.categories, 1)
        root.addWidget(sidebar)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        for build in (self._build_general, self._build_appearance, self._build_smart_editing,
                      self._build_shortcuts, self._build_about):
            self.pages.addWidget(self._scrollable(build()))
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
        self.apply_theme(self.theme)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: self.apply_theme(current_theme()))

    # Window behavior ---------------------------------------------------------------------------

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

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.setStyleSheet(stylesheet(theme))
        for kind in (SettingsComboBox, SettingsFontComboBox, ToggleSwitch):
            for widget in self.findChildren(kind):
                widget.set_theme(theme)
        for button in (self.restore_button, self.hotkey_restore_button):
            button.setIcon(line_icon("restore", theme.text))
        self._paint_category_icons(self.categories.currentRow())

    def _paint_category_icons(self, row: int) -> None:
        for index, (icon, _key) in enumerate(CATEGORIES):
            color = self.theme.icon_active if index == row else self.theme.icon
            self.categories.item(index).setIcon(line_icon(icon, color))

    def _switch_category(self, row: int) -> None:
        if row < 0:
            return
        if self._page_animation is not None:
            self._page_animation.stop()
        self.pages.setCurrentIndex(row)
        self._paint_category_icons(row)
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

    # Language ---------------------------------------------------------------------------------

    def _bind(self, setter, key: str, **values) -> None:
        setter(tr(key, **values))
        self._texts.append((setter, key, values))

    def retranslate(self) -> None:
        for setter, key, values in self._texts:
            setter(tr(key, **values))
        for index, key in enumerate(("source.local", "source.custom")):
            self.rewrite_provider.setItemText(index, tr(key))
        for index, key in enumerate(("align.left", "align.center", "align.right")):
            self.alignment_box.setItemText(index, tr(key))
        self.language_box.setItemText(0, tr("language.system"))
        for key, fallback in (("background", DEFAULT_BACKGROUND), ("capsule", DEFAULT_CAPSULE)):
            button = self.background_button if key == "background" else self.capsule_button
            self._show_color(button, saved_color(self.settings.value(f"appearance/{key}_color", fallback), fallback))
        self._populate_local_models(self._selected_model_path())
        if self._model_status is not None:
            self.set_model_status(self._model_status[0], **self._model_status[1])
        self.rewrite_status.setText(tr(self._test_result[0], **self._test_result[1]) if self._test_result else "")
        self.rewrite_status.setVisible(self._test_result is not None)
        for index, key in enumerate(("channel.stable", "channel.beta")):
            self.update_channel.setItemText(index, tr(key))
        key, values = self._hotkey_message
        self._show_hotkey_message(key, **values)

    def _set_language(self, _index: int) -> None:
        choice = str(self.language_box.currentData())
        self.settings.setValue("ui/language", choice)
        set_language(resolve(choice))
        self.retranslate()
        self.language_changed.emit(choice)

    # Layout helpers ---------------------------------------------------------------------------

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(page)
        return area

    def _page(self, title_key: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(8)
        title = QLabel()
        title.setObjectName("pageTitle")
        self._bind(title.setText, title_key)
        layout.addWidget(title)
        layout.addSpacing(10)
        return page, layout

    def _section(self, layout: QVBoxLayout, title_key: str | None = None) -> SettingsCard:
        layout.addSpacing(10)
        label = None
        if title_key:
            label = QLabel()
            label.setObjectName("sectionTitle")
            self._bind(label.setText, title_key)
            layout.addWidget(label)
            layout.addSpacing(2)
        card = SettingsCard()
        card.title_label = label
        layout.addWidget(card)
        self._cards.append(card)
        return card

    def _row(self, card: SettingsCard, title_key: str, desc_key: str | None, *controls: QWidget) -> SettingRow:
        row = SettingRow()
        self._bind(row.title.setText, title_key)
        if desc_key:
            self._bind(row.set_desc, desc_key)
        for control in controls:
            row.control_layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
            if not isinstance(control, QPushButton):
                self._bind(control.setAccessibleName, title_key)
        card.add_row(row)
        return row

    @staticmethod
    def _sized(widget: QWidget, width: int) -> QWidget:
        widget.setFixedWidth(width)
        return widget

    def _button(self, key: str, handler) -> QPushButton:
        button = QPushButton()
        button.setObjectName("secondary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bind(button.setText, key)
        button.clicked.connect(handler)
        return button

    # Pages ------------------------------------------------------------------------------------

    def _build_general(self) -> QWidget:
        page, layout = self._page("category.general")
        self.language_box = SettingsComboBox()
        for code, name in LANGUAGE_CHOICES:
            self.language_box.addItem(name or tr("language.system"), code)
        saved_language = str(self.settings.value("ui/language", "system"))
        self.language_box.setCurrentIndex(max(0, self.language_box.findData(saved_language)))
        self.language_box.currentIndexChanged.connect(self._set_language)
        card = self._section(layout, "section.language")
        self._row(card, "field.language", "desc.language", self._sized(self.language_box, 220))

        self.device_box = SettingsComboBox()
        self.alignment_box = SettingsComboBox()
        for key, value in (("align.left", "left"), ("align.center", "center"), ("align.right", "right")):
            self.alignment_box.addItem(tr(key), value)
        saved = str(self.settings.value("transcript/alignment", "left"))
        self.alignment_box.setCurrentIndex(max(0, self.alignment_box.findData(saved)))
        self.alignment_box.currentIndexChanged.connect(
            lambda _index: self.alignment_changed.emit(str(self.alignment_box.currentData())))
        card = self._section(layout, "section.input")
        self._row(card, "field.microphone", "desc.microphone", self._sized(self.device_box, 300))
        self._row(card, "field.alignment", "desc.alignment", self._sized(self.alignment_box, 220))
        note = QLabel()
        note.setObjectName("note")
        note.setWordWrap(True)
        self._bind(note.setText, "page.app.note")
        layout.addSpacing(4)
        layout.addWidget(note)
        layout.addStretch()
        return page

    def _build_appearance(self) -> QWidget:
        page, layout = self._page("category.appearance")
        self.font_box = SettingsFontComboBox()
        self.font_box.setCurrentFont(QFont(str(self.settings.value("appearance/font", DEFAULT_FONT))))
        self.font_box.currentFontChanged.connect(self._set_font)
        self.text_size_box = QSpinBox()
        self.text_size_box.setRange(14, 48)
        self.text_size_box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.text_size_box.setSuffix(" px")
        self.text_size_box.setAlignment(Qt.AlignmentFlag.AlignRight)
        try:
            saved_size = int(self.settings.value("appearance/text_size", DEFAULT_TEXT_SIZE))
        except (TypeError, ValueError):
            saved_size = DEFAULT_TEXT_SIZE
        self.text_size_box.setValue(max(14, min(48, saved_size)))
        self.text_size_box.valueChanged.connect(self._set_text_size)
        card = self._section(layout, "section.text")
        self._row(card, "field.font", "desc.font", self._sized(self.font_box, 240))
        self._row(card, "field.text_size", "desc.text_size", self._sized(self.text_size_box, 100))

        self.background_button = self._color_button("background", DEFAULT_BACKGROUND)
        self.capsule_button = self._color_button("capsule", DEFAULT_CAPSULE)
        card = self._section(layout, "section.glow")
        self._row(card, "field.background", "desc.background", self._sized(self.background_button, 170))
        self._row(card, "field.capsule", "desc.capsule", self._sized(self.capsule_button, 170))

        self.restore_button = self._button("button.restore", self._reset_appearance)
        self.restore_button.setIconSize(QSize(16, 16))
        card = self._section(layout, "section.reset")
        self._row(card, "field.restore", "desc.restore", self.restore_button)
        layout.addStretch()
        return page

    def _build_smart_editing(self) -> QWidget:
        page, layout = self._page("category.smart")
        config = RewriteConfig.from_settings(self.settings)

        self.rewrite_enabled = ToggleSwitch()
        self.rewrite_enabled.setChecked(config.enabled)
        card = self._section(layout)
        self._row(card, "field.smart_enable", "desc.smart_enable", self.rewrite_enabled)

        self.rewrite_provider = SettingsComboBox()
        self.rewrite_provider.addItem(tr("source.local"), "local")
        self.rewrite_provider.addItem(tr("source.custom"), "custom")
        self.rewrite_provider.setCurrentIndex(max(0, self.rewrite_provider.findData(config.provider)))
        self.rewrite_model_path = SettingsComboBox()
        self._last_model_index = 0
        self._populate_local_models(config.model_path)
        self.rewrite_endpoint = self._line(config.endpoint, None, "http://localhost:1234/v1")
        self.rewrite_model = SettingsComboBox()
        self.rewrite_model.setEditable(True)
        self.rewrite_model.setInsertPolicy(SettingsComboBox.InsertPolicy.NoInsert)
        if config.model:
            self.rewrite_model.addItem(config.model)
        self.rewrite_model.setCurrentText(config.model)
        self._bind(self.rewrite_model.lineEdit().setPlaceholderText, "placeholder.model")
        self.rewrite_model.lineEdit().editingFinished.connect(self._save_rewrite)
        self.rewrite_model.activated.connect(lambda _index: self._save_rewrite())
        self.rewrite_api_key = self._line(config.api_key, "placeholder.optional", password=True)
        refresh = self._button("button.refresh", self._refresh_models)

        card = self._section(layout, "section.model")
        self._model_card = card
        self._row(card, "field.model_source", "desc.model_source", self._sized(self.rewrite_provider, 280))
        self.rewrite_model_path_row = self._row(card, "field.local_model", "desc.local_model",
                                                self._sized(self.rewrite_model_path, 280))
        self.rewrite_endpoint_row = self._row(card, "field.endpoint", "desc.endpoint",
                                              self._sized(self.rewrite_endpoint, 280))
        self.rewrite_model_row = self._row(card, "field.model", "desc.custom_model",
                                           self._sized(self.rewrite_model, 200), refresh)
        self.rewrite_api_key_row = self._row(card, "field.api_key", "desc.api_key",
                                             self._sized(self.rewrite_api_key, 280))
        self.rewrite_test_button = self._button("button.test", self._test_rewrite)
        self.rewrite_model_status_row = self._row(card, "field.model_status", None, self.rewrite_test_button)
        self.rewrite_model_status = self.rewrite_model_status_row.desc
        self.rewrite_status = QLabel("")
        self.rewrite_status.setObjectName("rowDesc")
        self.rewrite_status.setWordWrap(True)
        self.rewrite_status.hide()
        self.rewrite_model_status_row.text_column.addWidget(self.rewrite_status)

        self.rewrite_server_path = self._line(config.server_path, None, RewriteConfig.server_path)
        browse = self._button("button.browse", self._browse_server)
        self._advanced_card = self._section(layout, "section.advanced")
        self.rewrite_server_path_row = self._row(self._advanced_card, "field.server_path", "desc.server_path",
                                                 self._sized(self.rewrite_server_path, 220), browse)
        layout.addStretch()

        self.rewrite_enabled.toggled.connect(self._save_rewrite)
        self.rewrite_provider.currentIndexChanged.connect(self._sync_rewrite_rows)
        self.rewrite_provider.currentIndexChanged.connect(self._save_rewrite)
        self.rewrite_model_path.currentIndexChanged.connect(self._local_model_chosen)
        self._sync_rewrite_rows()
        return page

    def _build_shortcuts(self) -> QWidget:
        page, layout = self._page("category.shortcuts")
        card = self._section(layout, "section.global_shortcuts")
        self.hotkey_buttons: dict[str, HotkeyButton] = {}
        for action in ACTIONS:
            button = HotkeyButton(saved_hotkey(self.settings, action).text)
            button.setMinimumWidth(190)
            self._bind(lambda _text, b=button: b.set_texts(tr("hotkey.prompt"), tr("hotkey.need_modifier")),
                       "hotkey.prompt")
            button.capture_changed.connect(self.hotkey_capture)
            button.captured.connect(lambda text, a=action: self._hotkey_captured(a, text))
            self.hotkey_buttons[action] = button
            row = self._row(card, HOTKEY_FIELDS[action], f"desc.hotkey_{action}", button)
            button.setAccessibleName(row.title.text())
        self.hotkey_status = QLabel()
        self.hotkey_status.setObjectName("note")
        self.hotkey_status.setWordWrap(True)
        layout.addSpacing(4)
        layout.addWidget(self.hotkey_status)
        self._show_hotkey_message("hotkey.help")

        self.hotkey_restore_button = self._button("button.restore", self._restore_hotkeys)
        self.hotkey_restore_button.setIconSize(QSize(16, 16))
        card = self._section(layout, "section.reset")
        row = self._row(card, "field.hotkey_restore", None, self.hotkey_restore_button)
        self._bind(row.set_desc, "desc.hotkey_restore", record=DEFAULT_HOTKEYS["record"],
                   resume=DEFAULT_HOTKEYS["continue"])
        layout.addStretch()
        return page

    def _build_about(self) -> QWidget:
        page, layout = self._page("category.about")
        hero = QWidget()
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 20, 20, 20)
        hero_layout.setSpacing(18)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(64, 64))
        hero_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(3)
        self.about_name = QLabel("VoxFlow")
        self.about_name.setObjectName("aboutName")
        self.about_version = QLabel()
        self.about_version.setObjectName("rowDesc")
        self._bind(self.about_version.setText, "about.version", version=app_version())
        self.about_author = QLabel()
        self.about_author.setObjectName("rowDesc")
        self._bind(self.about_author.setText, "about.author", author=AUTHOR)
        self.about_repo_button = QPushButton()
        self.about_repo_button.setObjectName("link")
        self.about_repo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bind(self.about_repo_button.setText, "about.repo")
        # Reserved until the first public release: the repository link opens REPO_URL then.
        self.about_repo_button.setEnabled(False)
        self._bind(self.about_repo_button.setToolTip, "about.coming")
        for widget in (self.about_name, self.about_version, self.about_author):
            column.addWidget(widget)
        column.addSpacing(6)
        column.addWidget(self.about_repo_button, 0, Qt.AlignmentFlag.AlignLeft)
        hero_layout.addLayout(column, 1)
        self._section(layout).add_row(hero)

        card = self._section(layout, "section.components")
        self._row(card, "about.asr", None, self._value("SenseVoiceSmall · sherpa-onnx"))
        rewrite_value = self._value("")
        self._bind(rewrite_value.setText, "about.rewrite_value")
        self._row(card, "about.rewrite", None, rewrite_value)
        self._row(card, "about.framework", None, self._value(f"PySide6 {PySide6.__version__} · Qt {qVersion()}"))
        license_value = self._value("")
        self._bind(license_value.setText, "about.license_value")
        self._row(card, "about.license", None, license_value)

        # Updates are reserved until VoxFlow is published; the controls show what is coming.
        self.update_channel = SettingsComboBox()
        for key, value in (("channel.stable", "stable"), ("channel.beta", "beta")):
            self.update_channel.addItem(tr(key), value)
        self.update_on_start = ToggleSwitch()
        self.update_check_button = self._button("button.check_updates", lambda: None)
        card = self._section(layout, "section.updates")
        self._row(card, "about.channel", "desc.channel", self._sized(self.update_channel, 220))
        self._row(card, "about.check_on_start", "desc.check_on_start", self.update_on_start)
        self._row(card, "about.check_now", "desc.check_now", self.update_check_button)
        for control in (self.update_channel, self.update_on_start, self.update_check_button):
            control.setEnabled(False)
        note = QLabel()
        note.setObjectName("note")
        note.setWordWrap(True)
        self._bind(note.setText, "about.updates_note")
        layout.addSpacing(4)
        layout.addWidget(note)
        layout.addStretch()
        return page

    @staticmethod
    def _value(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("rowValue")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _line(self, value: str, placeholder_key: str | None, placeholder: str = "",
              password: bool = False) -> QLineEdit:
        edit = QLineEdit(value)
        if placeholder_key:
            self._bind(edit.setPlaceholderText, placeholder_key)
        else:
            edit.setPlaceholderText(placeholder)
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setCursorPosition(0)  # long paths read from the start
        edit.editingFinished.connect(self._save_rewrite)
        return edit

    # Smart editing ----------------------------------------------------------------------------

    def _selected_model_path(self) -> str:
        data = self.rewrite_model_path.currentData()
        return str(data) if data and data != BROWSE else ""

    def _populate_local_models(self, selected: str) -> None:
        combo = self.rewrite_model_path
        combo.blockSignals(True)
        combo.clear()
        for model in discover_models(REPO_ROOT):
            key, values = describe_model(model)
            combo.addItem(tr(key, **values), _repo_relative(model.path))
            combo.setItemData(combo.count() - 1, str(model.path), Qt.ItemDataRole.ToolTipRole)
        index = next((i for i in range(combo.count()) if _same_path(str(combo.itemData(i)), selected)), -1)
        if index < 0 and selected:
            path = Path(selected).expanduser()
            path = path if path.is_absolute() else REPO_ROOT / path
            if path.is_file():
                key, values = describe_model(LocalModel(path, quant_of(path), path.stat().st_size))
                combo.addItem(tr(key, **values), selected)
            else:
                combo.addItem(tr("model.choice.missing", name=path.name), selected)
            index = combo.count() - 1
        combo.addItem(tr("model.browse"), BROWSE)
        combo.setCurrentIndex(max(0, index) if combo.count() > 1 else 0)
        self._last_model_index = combo.currentIndex()
        combo.blockSignals(False)

    def _local_model_chosen(self, index: int) -> None:
        if self.rewrite_model_path.itemData(index) != BROWSE:
            self._last_model_index = index
            self._save_rewrite()
            return
        chosen = self.choose_file(tr("dialog.choose_model"), str(REPO_ROOT), tr("filter.gguf"))
        if chosen:
            self._populate_local_models(_repo_relative(chosen))
            self._save_rewrite()
        else:
            self.rewrite_model_path.blockSignals(True)
            self.rewrite_model_path.setCurrentIndex(self._last_model_index)
            self.rewrite_model_path.blockSignals(False)

    def _browse_server(self) -> None:
        chosen = self.choose_file(tr("dialog.choose_server"), str(REPO_ROOT), tr("filter.exe"))
        if chosen:
            self.rewrite_server_path.setText(_repo_relative(chosen))
            self.rewrite_server_path.setCursorPosition(0)
            self._save_rewrite()

    def rewrite_config(self) -> RewriteConfig:
        return RewriteConfig(
            enabled=self.rewrite_enabled.isChecked(),
            provider=str(self.rewrite_provider.currentData()),
            endpoint=self.rewrite_endpoint.text().strip(),
            model=self.rewrite_model.currentText().strip(),
            api_key=self.rewrite_api_key.text().strip(),
            server_path=self.rewrite_server_path.text().strip() or RewriteConfig.server_path,
            model_path=self._selected_model_path() or RewriteConfig.model_path,
        )

    def _sync_rewrite_rows(self) -> None:
        custom = self.rewrite_provider.currentData() == "custom"
        for row in (self.rewrite_endpoint_row, self.rewrite_model_row, self.rewrite_api_key_row):
            row.setVisible(custom)
        self.rewrite_model_path_row.setVisible(not custom)
        self._advanced_card.setVisible(not custom)
        self._advanced_card.title_label.setVisible(not custom)
        for card in self._cards:
            card.refresh()

    def _save_rewrite(self) -> None:
        self.rewrite_config().save(self.settings)
        self.rewrite_changed.emit()

    def set_rewrite_tester(self, tester) -> None:
        self._rewrite_tester = tester

    def set_model_lister(self, lister) -> None:
        self._model_lister = lister

    def set_model_status(self, key: str, **values) -> None:
        self._model_status = (key, values)
        self.rewrite_model_status_row.set_desc(tr(key, **values))

    def _show_test_result(self, key: str, **values) -> None:
        self._test_result = (key, values)
        self.rewrite_status.setText(tr(key, **values))
        self.rewrite_status.show()

    def _test_rewrite(self) -> None:
        if self._rewrite_tester is None:
            self._show_test_result("test.unavailable")
            return
        self.rewrite_status.setText(tr("test.testing"))
        self.rewrite_status.show()
        self.rewrite_status.repaint()
        try:
            name = self._rewrite_tester(self.rewrite_config())
        except Exception as exc:  # explain any backend failure in the interface language
            self._show_test_result("test.failed", reason=describe_error(exc))
        else:
            self._show_test_result("test.connected", model=name)

    def _refresh_models(self) -> None:
        if self._model_lister is None:
            return
        try:
            names = self._model_lister(self.rewrite_config())
        except Exception as exc:  # explain any backend failure in the interface language
            self._show_test_result("models.refresh_failed", reason=describe_error(exc))
            return
        current = self.rewrite_model.currentText().strip()
        self.rewrite_model.clear()
        self.rewrite_model.addItems(names)
        self.rewrite_model.setCurrentText(current or (names[0] if names else ""))
        self._show_test_result("models.refreshed", count=len(names))
        self._save_rewrite()

    # Shortcuts --------------------------------------------------------------------------------

    def set_hotkey_applier(self, applier) -> None:
        """applier(action, text) registers the shortcut and returns None, or an error key to keep the old one."""
        self._hotkey_applier = applier

    def _show_hotkey_message(self, key: str, **values) -> None:
        self._hotkey_message = (key, values)
        shown = dict(values)
        if "action" in shown:
            shown["action"] = tr(shown["action"])
        self.hotkey_status.setText(tr(key, **shown))

    def _apply_hotkey(self, action: str, text: str) -> str | None:
        error = self._hotkey_applier(action, text) if self._hotkey_applier is not None else None
        if error is None:
            self.settings.setValue(f"hotkeys/{action}", text)
            self.hotkey_buttons[action].set_hotkey(text)
        return error

    def _hotkey_captured(self, action: str, text: str) -> None:
        other = next(name for name in ACTIONS if name != action)
        if parse_hotkey(text) == parse_hotkey(self.hotkey_buttons[other].hotkey):
            self._show_hotkey_message("hotkey.duplicate", hotkey=text, action=HOTKEY_FIELDS[other])
            return
        error = self._apply_hotkey(action, text)
        self._show_hotkey_message(error or "hotkey.saved", hotkey=text)

    def _restore_hotkeys(self) -> None:
        # Release both first so swapped custom keys can trade places.
        self.hotkey_capture.emit(True)
        errors = [(error, DEFAULT_HOTKEYS[action]) for action in ACTIONS
                  if (error := self._apply_hotkey(action, DEFAULT_HOTKEYS[action]))]
        self.hotkey_capture.emit(False)
        if errors:
            self._show_hotkey_message(errors[0][0], hotkey=errors[0][1])
        else:
            self._show_hotkey_message("hotkey.saved", hotkey=" / ".join(DEFAULT_HOTKEYS[a] for a in ACTIONS))

    # Appearance -------------------------------------------------------------------------------

    def _color_button(self, key: str, fallback: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("colorButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_color(button, saved_color(self.settings.value(f"appearance/{key}_color", fallback), fallback))
        button.clicked.connect(lambda: self._choose_color(key))
        return button

    @staticmethod
    def _show_color(button: QPushButton, color: QColor) -> None:
        swatch = QPixmap(20, 20)
        swatch.fill(Qt.GlobalColor.transparent)
        painter = QPainter(swatch)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#9A9A9A"))
        painter.setBrush(color)
        painter.drawRoundedRect(1, 1, 17, 17, 5, 5)
        painter.end()
        button.setIcon(QIcon(swatch))
        button.setText(tr("button.change_color", color=color.name().upper()))

    def _choose_color(self, key: str) -> None:
        fallback = DEFAULT_BACKGROUND if key == "background" else DEFAULT_CAPSULE
        initial = saved_color(self.settings.value(f"appearance/{key}_color", fallback), fallback)
        chosen = QColorDialog.getColor(initial, self, tr("field.background" if key == "background" else "field.capsule"))
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
