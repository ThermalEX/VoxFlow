"""The download list shared by settings and the tutorial: source, load list, tick items, download with progress."""

import ctypes
import sys
import threading

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .catalog import SOURCES, CatalogItem, fetch_catalog, installed_ids
from .i18n import language, tr
from .model_catalog import format_size
from .paths import DATA_ROOT
from .settings_widgets import CheckBox, SegmentedControl, SettingsCard

SOURCE_SETTING = "downloads/source"


def has_nvidia_gpu() -> bool:
    """True when Windows lists an NVIDIA display adapter."""
    if sys.platform != "win32":
        return False

    class DisplayDevice(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32), ("DeviceName", ctypes.c_wchar * 32),
                    ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", ctypes.c_uint32),
                    ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128)]

    index = 0
    while True:
        device = DisplayDevice()
        device.cb = ctypes.sizeof(device)
        if not ctypes.windll.user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
            return False
        if "NVIDIA" in device.DeviceString.upper():
            return True
        index += 1


def format_speed(bytes_per_second: float) -> str:
    return f"{bytes_per_second / 2**20:.1f} MB/s"


def format_eta(seconds: float) -> str:
    if seconds < 60:
        return tr("download.eta_seconds", count=max(1, round(seconds)))
    return tr("download.eta_minutes", count=round(seconds / 60))


class ItemRow(QWidget):
    def __init__(self, item: CatalogItem, compact: bool) -> None:
        super().__init__()
        self.item = item
        self.state = ""
        self.fixed_status = ""  # "installed" or "needs_nvidia": the row cannot be ticked
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8 if compact else 11, 14, 8 if compact else 11)
        layout.setSpacing(12)
        self.checkbox = CheckBox()
        layout.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(3)
        self.title = QLabel()
        self.title.setObjectName("rowTitle")
        self.desc = QLabel()
        self.desc.setObjectName("rowDesc")
        self.desc.setWordWrap(True)
        self.desc.setVisible(not compact)
        self.progress = QProgressBar()
        self.progress.setObjectName("downloadProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.hide()
        self.status_label = QLabel()
        self.status_label.setObjectName("rowDesc")
        self.status_label.setWordWrap(True)
        for widget in (self.title, self.desc, self.progress, self.status_label):
            column.addWidget(widget)
        layout.addLayout(column, 1)
        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName("secondary")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.retranslate()

    def retranslate(self) -> None:
        lang = language()
        tags = [tr("download.required")] if self.item.required else []
        if self.item.recommended and not self.item.required:
            tags.append(tr("download.recommended"))
        self.title.setText(" · ".join([self.item.title[lang]] + tags))
        self.desc.setText(f"{format_size(self.item.size)} · {self.item.desc[lang]}" if self.item.size
                          else self.item.desc[lang])
        self.cancel_button.setText(tr("download.cancel"))
        if self.fixed_status:
            self.status_label.setText(tr(f"download.{self.fixed_status}"))

    def set_fixed(self, status: str) -> None:
        self.fixed_status = status
        self.checkbox.setChecked(False)
        self.checkbox.setEnabled(not status)
        self.status_label.setText(tr(f"download.{status}") if status else "")
        self.status_label.setVisible(bool(status))


class DownloadPanel(QWidget):
    installed = Signal(str)
    _loaded = Signal(object, bool)  # delivers the list from the loading thread

    def __init__(self, settings: QSettings, manager, root=DATA_ROOT, fetch=None, has_nvidia=None,
                 compact: bool = False) -> None:
        super().__init__()
        self.settings = settings
        self.manager = manager
        self.root = root
        self._fetch = fetch or (lambda source: fetch_catalog(source))
        self._has_nvidia = has_nvidia or (lambda: has_nvidia_gpu())
        self._pending_preselect: list[str] = []
        self.compact = compact
        self.items: list[CatalogItem] = []
        self.rows: dict[str, ItemRow] = {}
        self._errors: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("sectionTitle")
        self.load_button = QPushButton()
        self.load_button.setObjectName("secondary")
        self.load_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_button.clicked.connect(self.load)
        self.title.setVisible(not compact)  # the tutorial step already has its own heading
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.load_button)
        layout.addLayout(header)

        self.card = SettingsCard()
        source_box = QWidget()
        source_box.setObjectName("sourceBox")
        source_layout = QVBoxLayout(source_box)
        source_layout.setContentsMargins(14, 12, 14, 12)
        source_layout.setSpacing(6)
        source_row = QHBoxLayout()
        source_row.setSpacing(14)
        self.source_title = QLabel()
        self.source_title.setObjectName("rowTitle")
        self.source_control = SegmentedControl([(value, "") for value in SOURCES])
        saved = str(settings.value(SOURCE_SETTING, "auto"))
        self.source_control.buttons[saved if saved in SOURCES else "auto"].setChecked(True)
        self.source_control.changed.connect(lambda value: self.settings.setValue(SOURCE_SETTING, value))
        source_row.addWidget(self.source_title)
        source_row.addWidget(self.source_control)
        source_row.addStretch(1)
        source_layout.addLayout(source_row)
        self.source_desc = QLabel()
        self.source_desc.setObjectName("rowDesc")
        self.source_desc.setWordWrap(True)
        self.source_desc.setVisible(not compact)
        source_layout.addWidget(self.source_desc)
        self.card.add_row(source_box)
        self.list_box = QWidget()
        self.list_layout = QVBoxLayout(self.list_box)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.card.add_row(self.list_box)
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 10, 14, 10)
        self.summary = QLabel()
        self.summary.setObjectName("rowDesc")
        self.cancel_all_button = QPushButton()
        self.cancel_all_button.setObjectName("secondary")
        self.cancel_all_button.clicked.connect(self.manager.cancel_all)
        self.cancel_all_button.hide()
        self.download_button = QPushButton()
        self.download_button.setObjectName("primary")
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_button.clicked.connect(self._download)
        footer_layout.addWidget(self.summary, 1)
        footer_layout.addWidget(self.cancel_all_button)
        footer_layout.addWidget(self.download_button)
        self.card.add_row(footer)
        layout.addWidget(self.card)
        self.notice = QLabel()
        self.notice.setObjectName("note")
        self.notice.setWordWrap(True)
        self.notice.hide()
        layout.addWidget(self.notice)
        self.background_hint = QLabel()
        self.background_hint.setObjectName("note")
        self.background_hint.hide()
        layout.addWidget(self.background_hint)

        self._loaded.connect(self._show_items)
        manager.progress.connect(self._on_progress)
        manager.item_state.connect(self._on_state)
        manager.item_failed.connect(lambda item_id, key: self._errors.__setitem__(item_id, key))
        manager.all_done.connect(self._sync_footer)
        self.retranslate()

    # Loading ------------------------------------------------------------------------------------

    def load(self, preselect: list[str] | None = None) -> None:
        """Read the list in the background; `preselect` ticks those items once it arrives (nothing starts)."""
        self._pending_preselect = list(preselect or [])
        self.load_button.setEnabled(False)
        self.load_button.setText(tr("download.loading"))
        source = self.source_control.value()
        fetch = self._fetch
        threading.Thread(target=lambda: self._loaded.emit(*fetch(source)), daemon=True).start()

    def _show_items(self, items: list[CatalogItem], online: bool) -> None:
        selected = set(self.selected_ids())
        for row in self.rows.values():
            row.setParent(None)
            row.deleteLater()
        self.rows.clear()
        self.items = items
        done = installed_ids(items, self.root)
        nvidia = self._has_nvidia()
        for item in items:
            row = ItemRow(item, self.compact)
            if getattr(self, "theme", None) is not None:
                row.checkbox.set_theme(self.theme)
            if item.id in done:
                row.set_fixed("installed")
            elif item.needs_nvidia and not nvidia:
                row.set_fixed("needs_nvidia")
            else:
                row.set_fixed("")
                row.checkbox.setChecked(item.id in selected)
            row.checkbox.toggled.connect(lambda checked, chosen=item: self._ticked(chosen, checked))
            row.cancel_button.clicked.connect(lambda _checked=False, item_id=item.id: self.manager.cancel(item_id))
            self.list_layout.addWidget(row)
            self.rows[item.id] = row
        self.notice.setText(tr("download.offline"))
        self.notice.setVisible(not online)
        self.load_button.setEnabled(True)
        self.load_button.setText(tr("download.load"))
        self.preselect(self._pending_preselect)
        self._pending_preselect = []
        self._sync_footer()

    # Selection ----------------------------------------------------------------------------------

    def _ticked(self, item: CatalogItem, checked: bool) -> None:
        if checked and item.group:
            for other in self.items:
                if other.id != item.id and other.group == item.group and other.id in self.rows:
                    self.rows[other.id].checkbox.setChecked(False)
        self._sync_footer()

    def preselect(self, ids: list[str]) -> None:
        for item_id in ids:
            row = self.rows.get(item_id)
            if row is not None and row.checkbox.isEnabled():
                row.checkbox.setChecked(True)

    def selected_ids(self) -> list[str]:
        return [item.id for item in self.items
                if item.id in self.rows and self.rows[item.id].checkbox.isChecked()]

    def _download(self) -> None:
        chosen = [item for item in self.items if item.id in self.selected_ids()]
        if not chosen:
            return
        source = self.source_control.value()
        self.settings.setValue(SOURCE_SETTING, source)
        for item in chosen:
            self.rows[item.id].checkbox.setChecked(False)
            self.rows[item.id].checkbox.setEnabled(False)
        self.manager.start(chosen, source)
        self._sync_footer()

    # Progress -----------------------------------------------------------------------------------

    def _on_progress(self, item_id: str, done, total, speed: float) -> None:
        row = self.rows.get(item_id)
        if row is None or not total:
            return
        percent = int(done * 100 / total)
        row.progress.setValue(percent)
        row.progress.show()
        eta = format_eta((total - done) / speed) if speed > 0 else ""
        values = {"percent": percent, "done": format_size(done), "total": format_size(total),
                  "speed": format_speed(speed), "eta": eta}
        row.status_label.setText(tr("download.progress", **values).rstrip(" ·"))
        row.status_label.show()

    def _on_state(self, item_id: str, state: str) -> None:
        row = self.rows.get(item_id)
        if row is None:
            return
        row.state = state
        busy = state in ("queued", "downloading", "verifying")
        row.cancel_button.setVisible(busy)
        row.progress.setVisible(state in ("downloading", "verifying"))
        if state == "installed":
            row.progress.hide()
            row.set_fixed("installed")
            self.installed.emit(item_id)
        elif state == "failed":
            row.set_fixed("")
            row.status_label.setText(tr(self._errors.pop(item_id, "download.error.network")))
            row.status_label.show()
        elif state == "cancelled":
            row.set_fixed("")
            row.status_label.setText(tr("download.cancelled"))
            row.status_label.show()
        elif state in ("queued", "downloading", "verifying"):
            row.checkbox.setEnabled(False)
            if state != "downloading":
                row.status_label.setText(tr(f"download.{state}"))
                row.status_label.show()
        self._sync_footer()

    def _sync_footer(self) -> None:
        chosen = [item for item in self.items if item.id in self.selected_ids()]
        self.summary.setText(tr("download.selected", count=len(chosen),
                                size=format_size(sum(item.size for item in chosen))))
        busy = any(row.state in ("queued", "downloading", "verifying") for row in self.rows.values())
        self.download_button.setEnabled(bool(chosen))
        self.cancel_all_button.setVisible(busy)
        self.background_hint.setVisible(busy)

    def set_theme(self, theme) -> None:
        """Repaint the check boxes for a palette (settings windows do this for all their children)."""
        self.theme = theme
        for row in self.rows.values():
            row.checkbox.set_theme(theme)

    # Language -----------------------------------------------------------------------------------

    def retranslate(self) -> None:
        self.title.setText(tr("download.title"))
        self.load_button.setText(tr("download.load"))
        self.source_title.setText(tr("download.source"))
        self.source_control.set_texts({value: tr(f"download.source.{value}") for value in SOURCES})
        self.source_desc.setText(tr("download.source_desc"))
        self.download_button.setText(tr("download.start"))
        self.cancel_all_button.setText(tr("download.cancel_all"))
        self.background_hint.setText(tr("download.background"))
        self.notice.setText(tr("download.offline"))
        for row in self.rows.values():
            row.retranslate()
        self._sync_footer()
