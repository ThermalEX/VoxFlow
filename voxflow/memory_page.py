"""Memory in the settings window.

The page itself stays short: the switch, how many memories are saved, where they are kept. Managing them happens
in two windows: "Saved memories" (search, filter by kind and by how long they are kept, sort, add, edit, delete)
and "Daily records" (each day's confirmed texts and its summary).
"""

import time
from datetime import datetime

from PySide6.QtCore import QSize, QUrl, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from .i18n import tr
from .memory import describe_when
from .memory_store import FOREVER, KEEPS, KINDS, WEEK
from .settings_widgets import SegmentedControl, SettingRow, SettingsCard, SettingsComboBox, ToggleSwitch
from .ui_icons import line_icon

MAX_ROWS = 300
ALL = "all"
KEEP_KEYS = {WEEK: "memory.keep.week", FOREVER: "memory.keep.forever"}


def _when(timestamp: float, with_date: bool = True) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%m-%d %H:%M" if with_date else "%H:%M")


def _icon_button(icon: str, tooltip_key: str, color: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("iconButton")
    button.setIcon(line_icon(icon, color))
    button.setIconSize(QSize(18, 18))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(tr(tooltip_key))
    button.setAccessibleName(tr(tooltip_key))
    return button


class MemoryRow(QWidget):
    """One line of a memory list: the text, a muted line about it, and a ⋯ menu of actions."""

    def __init__(self, text: str, meta: str, actions: list[tuple[str, object]], icon_color: str) -> None:
        super().__init__()
        self.setObjectName("memoryRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 6, 10)
        layout.setSpacing(10)
        column = QVBoxLayout()
        column.setSpacing(3)
        self.text = QLabel(text)
        self.text.setObjectName("memoryText")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.meta = QLabel(meta)
        self.meta.setObjectName("memoryMeta")
        self.meta.setWordWrap(True)
        column.addWidget(self.text)
        column.addWidget(self.meta)
        layout.addLayout(column, 1)
        self.menu_button = _icon_button("more", "memory.actions", icon_color)
        self.menu = QMenu(self.menu_button)
        self.actions: dict[str, QAction] = {}
        for label, handler in actions:
            action = self.menu.addAction(label)
            action.triggered.connect(lambda _checked=False, h=handler: h())
            self.actions[label] = action
        self.menu_button.setMenu(self.menu)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(self.menu_button, 0, Qt.AlignmentFlag.AlignTop)


class MemoryList(QScrollArea):
    """A scrolling column of MemoryRows with a message when it is empty."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("memoryList")
        self._layout = QVBoxLayout(holder)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self.setWidget(holder)
        self.rows: list[MemoryRow] = []
        self.empty = QLabel()
        self.empty.setObjectName("rowDesc")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setContentsMargins(0, 30, 0, 30)
        self._layout.insertWidget(0, self.empty)

    def set_rows(self, rows: list[MemoryRow], empty_text: str) -> None:
        for row in self.rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self.rows = rows
        for index, row in enumerate(rows):
            self._layout.insertWidget(index, row)
        self.empty.setText(empty_text)
        self.empty.setVisible(not rows)


class _Dialog(QDialog):
    def __init__(self, page: "MemoryPage", title_key: str) -> None:
        super().__init__(page.owner)
        self.page = page
        self.setObjectName("memoryDialog")
        self.setWindowTitle(tr(title_key))
        self.resize(680, 720)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(26, 22, 26, 22)
        self.layout_.setSpacing(12)
        self.title = QLabel(tr(title_key))
        self.title.setObjectName("dialogTitle")
        self.layout_.addWidget(self.title)
        self._title_key = title_key

    @property
    def store(self):
        return self.page.store

    @property
    def icon_color(self) -> str:
        return self.page.owner.theme.icon

    def changed(self) -> None:
        self.page.memory.changed.emit()

    def retranslate(self) -> None:
        self.setWindowTitle(tr(self._title_key))
        self.title.setText(tr(self._title_key))


class MemoriesDialog(_Dialog):
    """Saved memories: search, filter by kind and by how long they are kept, sort, add, edit and delete."""

    def __init__(self, page: "MemoryPage") -> None:
        super().__init__(page, "memory.dialog_title")
        self.remote_note = QLabel()
        self.remote_note.setObjectName("warning")
        self.remote_note.setWordWrap(True)
        self.layout_.addWidget(self.remote_note)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("searchBox")
        self.search.setClearButtonEnabled(True)
        self.search_action = self.search.addAction(line_icon("search", self.icon_color),
                                                   QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda _text: self.refresh())
        tools.addWidget(self.search, 1)
        self.kind_filter = SettingsComboBox()
        self.kind_filter.setFixedWidth(130)
        self.kind_filter.currentIndexChanged.connect(lambda _index: self.refresh())
        tools.addWidget(self.kind_filter)
        self.keep_filter = SegmentedControl([(ALL, ""), (WEEK, ""), (FOREVER, "")])
        self.keep_filter.buttons[ALL].setChecked(True)
        self.keep_filter.changed.connect(lambda _value: self.refresh())
        tools.addWidget(self.keep_filter)
        self.sort_button = _icon_button("sort", "memory.sort_newest", self.icon_color)
        self.sort_button.setCheckable(True)  # checked: oldest first
        self.sort_button.toggled.connect(lambda _on: self.refresh())
        tools.addWidget(self.sort_button)
        self.more_button = _icon_button("more", "memory.more_actions", self.icon_color)
        self.more_menu = QMenu(self.more_button)
        self.add_action = self.more_menu.addAction("")
        self.add_action.triggered.connect(self.show_add)
        self.open_action = self.more_menu.addAction("")
        self.open_action.triggered.connect(page.open_folder)
        self.more_menu.addSeparator()
        self.clear_action = self.more_menu.addAction("")
        self.clear_action.triggered.connect(page.clear_all)
        self.more_button.setMenu(self.more_menu)
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        tools.addWidget(self.more_button)
        self.layout_.addLayout(tools)

        self.add_bar = QWidget()
        add = QHBoxLayout(self.add_bar)
        add.setContentsMargins(0, 0, 0, 0)
        add.setSpacing(8)
        self.new_entry = QLineEdit()
        self.new_entry.returnPressed.connect(self.add_entry)
        self.new_kind = SettingsComboBox()
        self.new_kind.setFixedWidth(130)
        for kind in KINDS:
            self.new_kind.addItem("", kind)
        self.save_button = QPushButton()
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.add_entry)
        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName("secondary")
        self.cancel_button.clicked.connect(lambda: self.add_bar.hide())
        add.addWidget(self.new_entry, 1)
        add.addWidget(self.new_kind)
        add.addWidget(self.save_button)
        add.addWidget(self.cancel_button)
        self.add_bar.hide()
        self.layout_.addWidget(self.add_bar)

        self.list = MemoryList()
        self.layout_.addWidget(self.list, 1)
        self.count = QLabel()
        self.count.setObjectName("memoryMeta")
        self.layout_.addWidget(self.count)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        self.search.setPlaceholderText(tr("placeholder.memory_search"))
        chosen = self.kind_filter.currentData()
        self.kind_filter.blockSignals(True)
        self.kind_filter.clear()
        self.kind_filter.addItem(tr("memory.kind.all"), ALL)
        for kind in KINDS:
            self.kind_filter.addItem(tr(f"memory.kind.{kind}"), kind)
        self.kind_filter.setCurrentIndex(max(0, self.kind_filter.findData(chosen)))
        self.kind_filter.blockSignals(False)
        for index, kind in enumerate(KINDS):
            self.new_kind.setItemText(index, tr(f"memory.kind.{kind}"))
        self.keep_filter.set_texts({ALL: tr("memory.keep.all"), WEEK: tr("memory.keep.week"),
                                    FOREVER: tr("memory.keep.forever")})
        self.add_action.setText(tr("memory.add"))
        self.open_action.setText(tr("button.open_folder"))
        self.clear_action.setText(tr("button.clear_memory"))
        self.new_entry.setPlaceholderText(tr("placeholder.memory_new"))
        self.save_button.setText(tr("button.save"))
        self.cancel_button.setText(tr("button.cancel"))
        self.refresh()

    def set_theme(self, _theme) -> None:
        color = self.icon_color
        self.search_action.setIcon(line_icon("search", color))
        self.sort_button.setIcon(line_icon("sort", color))
        self.more_button.setIcon(line_icon("more", color))
        self.refresh()

    def show_add(self) -> None:
        self.add_bar.show()
        self.new_entry.setFocus()

    def add_entry(self) -> None:
        text = self.new_entry.text().strip()
        if not text or self.store is None:
            return
        self.store.add_entry(text, kind=str(self.new_kind.currentData()), source="manual")
        self.new_entry.clear()
        self.add_bar.hide()
        self.changed()

    def refresh(self) -> None:
        endpoint = self.page.memory.remote_endpoint() if self.page.memory is not None else ""
        self.remote_note.setText(tr("memory.remote_note", endpoint=endpoint))
        self.remote_note.setVisible(bool(endpoint) and self.page.enabled_now())
        self.add_action.setEnabled(self.store is not None)
        self.clear_action.setEnabled(self.store is not None)
        self.sort_button.setToolTip(tr("memory.sort_oldest" if self.sort_button.isChecked() else "memory.sort_newest"))
        total = len(self.store.entries()) if self.store is not None else 0
        entries = self.store.entries(self.search.text()) if self.store is not None else []
        kind, keep = self.kind_filter.currentData(), self.keep_filter.value()
        entries = [entry for entry in entries
                   if kind in (None, ALL, entry.kind) and keep in ("", ALL, entry.keep)]
        if self.sort_button.isChecked():
            entries.reverse()
        rows = [self._row(entry) for entry in entries[:MAX_ROWS]]
        self.list.set_rows(rows, tr("memory.no_matches" if total else "memory.empty"))
        self.count.setText(tr("memory.count", shown=len(entries), total=total))

    def _row(self, entry) -> MemoryRow:
        parts = [tr(f"memory.kind.{entry.kind}"), tr(KEEP_KEYS[entry.keep])]
        if describe_when(entry.detail):
            parts.append(tr("memory.time", time=describe_when(entry.detail)))
        parts += [tr(f"memory.source.{entry.source}"), _when(entry.updated_at)]
        other = FOREVER if entry.keep == WEEK else WEEK
        actions = [(tr("button.edit"), lambda: self.edit_entry(entry)),
                   (tr("memory.move_forever" if other == FOREVER else "memory.move_week"),
                    lambda: self.page.set_keep("entries", entry.id, other)),
                   (tr("button.delete"), lambda: self.page.delete("entries", entry.id))]
        return MemoryRow(entry.content, " · ".join(parts), actions, self.icon_color)

    def edit_entry(self, entry) -> None:
        text, ok = self.page.ask_text(tr("button.edit"), entry.content)
        if ok and text.strip():
            self.store.update_entry(entry.id, content=text)
            self.changed()


class DaysDialog(_Dialog):
    """Each day's confirmed texts and its summary, made only when asked."""

    def __init__(self, page: "MemoryPage") -> None:
        super().__init__(page, "memory.days_title")
        self._day = ""
        self._message: tuple[str, dict, float] | None = None  # key, values, when it happened
        top = QHBoxLayout()
        top.setSpacing(8)
        self.day_box = SettingsComboBox()
        self.day_box.setFixedWidth(220)
        self.day_box.currentIndexChanged.connect(self._day_chosen)
        top.addWidget(self.day_box)
        top.addStretch(1)
        self.delete_day_button = QPushButton()
        self.delete_day_button.setObjectName("secondary")
        self.delete_day_button.clicked.connect(self.delete_day)
        top.addWidget(self.delete_day_button)
        self.layout_.addLayout(top)

        self.summary_card = SettingsCard()
        self.summary_header = SettingRow()
        self.generate_button = QPushButton()
        self.generate_button.setObjectName("primary")
        self.generate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_button.clicked.connect(lambda: self.summarize(self._day))
        self.summary_keep = SegmentedControl([(value, "") for value in KEEPS])
        self.summary_keep.changed.connect(self._summary_keep_chosen)
        self.summary_delete = QPushButton()
        self.summary_delete.setObjectName("secondary")
        self.summary_delete.clicked.connect(self._delete_summary)
        for control in (self.generate_button, self.summary_keep, self.summary_delete):
            self.summary_header.control_layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.summary_text = QLabel()
        self.summary_text.setObjectName("memoryText")
        self.summary_text.setWordWrap(True)
        self.summary_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary_text.setContentsMargins(16, 4, 16, 14)
        self.summary_card.add_row(self.summary_header)
        self.summary_card.add_row(self.summary_text)
        self.layout_.addWidget(self.summary_card)
        self.records_title = QLabel()
        self.records_title.setObjectName("sectionTitle")
        self.layout_.addWidget(self.records_title)
        self.list = MemoryList()
        self.layout_.addWidget(self.list, 1)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        self.delete_day_button.setText(tr("button.delete_day"))
        self.summary_header.title.setText(tr("field.memory_summary"))
        self.summary_keep.set_texts({value: tr(KEEP_KEYS[value]) for value in KEEPS})
        self.summary_delete.setText(tr("button.delete"))
        self.records_title.setText(tr("memory.records_title"))
        self.refresh()

    def set_theme(self, _theme) -> None:
        self.refresh()

    def refresh(self) -> None:
        days = self.store.days() if self.store is not None else []
        today = datetime.now().strftime("%Y-%m-%d")
        choices = days if today in days or not days else [today] + days
        chosen = self._day if self._day in choices else (choices[0] if choices else "")
        self.day_box.blockSignals(True)
        self.day_box.clear()
        for day in choices:
            self.day_box.addItem(tr("memory.today", day=day) if day == today else day, day)
        self.day_box.setCurrentIndex(max(0, self.day_box.findData(chosen)))
        self.day_box.blockSignals(False)
        self._day = chosen
        self.day_box.setEnabled(bool(choices))
        self.delete_day_button.setEnabled(bool(days) and chosen in days)
        self._fill_day()

    def _fill_day(self) -> None:
        store, day = self.store, self._day
        records = store.records(day) if store is not None and day else []
        summary = store.summary(day) if store is not None and day else None
        busy = self.page.memory is not None and self.page.memory.summarizing(day)
        self.generate_button.setText(tr("button.summarizing" if busy else
                                        "button.summarize_again" if summary else "button.summarize"))
        self.generate_button.setEnabled(bool(records) and not busy)
        message = ""
        if self._message is not None:
            key, values, when = self._message
            # A failure is old news once a newer summary exists.
            message = tr(key, **values) if summary is None or summary.created_at < when else ""
        made = tr("memory.summary_made", when=_when(summary.created_at)) if summary is not None else ""
        self.summary_header.set_desc(message or made)
        self.summary_keep.setVisible(summary is not None)
        self.summary_delete.setVisible(summary is not None)
        if summary is not None:
            self.summary_keep.buttons[summary.keep].setChecked(True)
        self.summary_text.setText(summary.text if summary is not None else tr("memory.no_summary"))
        self.summary_text.setObjectName("memoryText" if summary is not None else "rowDesc")
        self.summary_text.style().unpolish(self.summary_text)
        self.summary_text.style().polish(self.summary_text)
        rows = []
        for record in records:
            other = FOREVER if record.keep == WEEK else WEEK
            meta = [_when(record.created_at, with_date=False), tr(KEEP_KEYS[record.keep])]
            if record.explicit:
                meta.append(tr("memory.source.explicit"))
            actions = [(tr("memory.move_forever" if other == FOREVER else "memory.move_week"),
                        lambda r=record, o=other: self.page.set_keep("records", r.id, o)),
                       (tr("button.delete"), lambda r=record: self.page.delete("records", r.id))]
            rows.append(MemoryRow(record.text, " · ".join(meta), actions, self.icon_color))
        self.list.set_rows(rows, tr("memory.no_records"))

    def _day_chosen(self, _index: int) -> None:
        self._day = str(self.day_box.currentData() or "")
        self._message = None
        self.delete_day_button.setEnabled(self.store is not None and self._day in self.store.days())
        self._fill_day()

    def _summary_keep_chosen(self, keep: str) -> None:
        summary = self.store.summary(self._day) if self.store is not None else None
        if summary is not None and summary.keep != keep:
            self.page.set_keep("summaries", summary.id, keep)

    def _delete_summary(self) -> None:
        summary = self.store.summary(self._day) if self.store is not None else None
        if summary is not None:
            self.page.delete("summaries", summary.id)

    def delete_day(self) -> None:
        if self.store is not None and self._day and self.page.confirm(tr("memory.confirm_delete_day", day=self._day)):
            self.store.delete_day(self._day)
            self.changed()

    def summarize(self, day: str) -> None:
        self._message = None
        if self.page.memory is not None and self.page.memory.summarize(day):
            self._fill_day()

    def summary_done(self, day: str, reason: str | None) -> None:
        if reason is None:
            self._message = None
        elif reason in ("empty", "model"):
            self._message = (f"memory.summary_{reason}", {}, time.time())
        else:
            self._message = ("memory.summary_failed", {"reason": reason}, time.time())
        if day == self._day:
            self._fill_day()


class MemoryPage:
    def __init__(self, owner) -> None:
        self.owner = owner
        self.memory = None
        # Dialogs go through these hooks so tests can answer them.
        self.ask_text = lambda title, text: QInputDialog.getText(owner, title, title, QLineEdit.EchoMode.Normal, text)
        self.confirm = lambda text: QMessageBox.question(owner, tr("category.memory"), text) == \
            QMessageBox.StandardButton.Yes

        page, layout = owner._page("category.memory")
        self.enabled = ToggleSwitch()
        self.enabled.setChecked(owner.settings.value("memory/enabled", False, type=bool))
        self.enabled.toggled.connect(self._set_enabled)
        card = owner._section(layout)
        owner._row(card, "field.memory_enable", "desc.memory_enable", self.enabled)
        self.manage_button = owner._button("button.manage", self.show_memories)
        self.memories_row = owner._row(card, "field.memory_saved", None, self.manage_button)
        self.days_button = owner._button("button.view", self.show_days)
        owner._row(card, "field.memory_days", "desc.memory_days", self.days_button)
        self.open_button = owner._button("button.open_folder", self.open_folder)
        self.location_row = owner._row(card, "field.memory_location", None, self.open_button)
        self.remote_note = QLabel()
        self.remote_note.setObjectName("warning")
        self.remote_note.setWordWrap(True)
        self.remote_note.hide()
        layout.addSpacing(6)
        layout.addWidget(self.remote_note)
        layout.addStretch()
        self.widget = page
        self.memories_dialog: MemoriesDialog | None = None
        self.days_dialog: DaysDialog | None = None
        owner.rewrite_changed.connect(self.refresh)
        owner.palette_changed.connect(self._set_theme)

    # Data ----------------------------------------------------------------------------------------

    def set_memory(self, memory) -> None:
        self.memory = memory
        memory.changed.connect(self.refresh)
        memory.summary_ready.connect(lambda day: self._summary_done(day, None))
        memory.summary_failed.connect(self._summary_done)
        self.refresh()

    @property
    def store(self):
        return self.memory.store if self.memory is not None else None

    def enabled_now(self) -> bool:
        return self.memory.enabled if self.memory is not None else self.enabled.isChecked()

    def refresh(self) -> None:
        on = self.enabled_now()
        if self.enabled.isChecked() != on:
            self.enabled.blockSignals(True)
            self.enabled.setChecked(on)
            self.enabled.blockSignals(False)
        count = len(self.store.entries()) if self.store is not None else 0
        self.memories_row.set_desc(tr("desc.memory_saved", count=count))
        # A path has no spaces to wrap at; let it break after each folder so the row fits narrow windows.
        location = str(self.memory.location()).replace("\\", "\\​").replace("/", "/​") \
            if self.memory is not None else ""
        self.location_row.set_desc(tr("desc.memory_location", path=location) if location else "")
        endpoint = self.memory.remote_endpoint() if self.memory is not None else ""
        self.remote_note.setText(tr("memory.remote_note", endpoint=endpoint))
        self.remote_note.setVisible(bool(on and endpoint))
        self.open_button.setEnabled(self.store is not None)
        for dialog in (self.memories_dialog, self.days_dialog):
            if dialog is not None:
                dialog.refresh()

    def retranslate(self) -> None:
        for dialog in (self.memories_dialog, self.days_dialog):
            if dialog is not None:
                dialog.retranslate()
        self.refresh()

    def _set_theme(self, theme) -> None:
        for dialog in (self.memories_dialog, self.days_dialog):
            if dialog is not None:
                dialog.set_theme(theme)

    # Actions -------------------------------------------------------------------------------------

    def show_memories(self) -> None:
        if self.memories_dialog is None:
            self.memories_dialog = MemoriesDialog(self)
        self.memories_dialog.refresh()
        self.memories_dialog.show()
        self.memories_dialog.raise_()

    def show_days(self) -> None:
        if self.days_dialog is None:
            self.days_dialog = DaysDialog(self)
        self.days_dialog.refresh()
        self.days_dialog.show()
        self.days_dialog.raise_()

    def _set_enabled(self, on: bool) -> None:
        if self.memory is not None:
            self.memory.set_enabled(on)
        else:
            self.owner.settings.setValue("memory/enabled", on)
            self.refresh()

    def open_folder(self) -> None:
        if self.memory is not None:
            self.owner.open_url(QUrl.fromLocalFile(str(self.memory.location())).toString())

    def clear_all(self) -> None:
        if self.store is not None and self.confirm(tr("memory.confirm_clear")):
            self.store.clear()
            self.memory.changed.emit()

    def set_keep(self, table: str, row_id: int, keep: str) -> None:
        if self.store is not None:
            self.store.set_keep(table, row_id, keep)
            self.memory.changed.emit()

    def delete(self, table: str, row_id: int) -> None:
        if self.store is not None:
            self.store.delete(table, row_id)
            self.memory.changed.emit()

    def _summary_done(self, day: str, reason: str | None) -> None:
        if self.days_dialog is None:
            self.days_dialog = DaysDialog(self)
        self.days_dialog.summary_done(day, reason)
