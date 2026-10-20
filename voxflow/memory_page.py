"""The Memory page of the settings window: the switch and privacy notes, the table of what VoxFlow remembers,
and each day's confirmed texts with its summary. Everything here can be kept for a week or forever."""

from datetime import datetime

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QWidget

from .i18n import tr
from .memory_store import FOREVER, KEEPS, KINDS, WEEK
from .settings_widgets import SegmentedControl, SettingRow, SettingsCard, SettingsComboBox, ToggleSwitch

MAX_ROWS = 200
KEEP_KEYS = {WEEK: "memory.keep.week", FOREVER: "memory.keep.forever"}


def _when(timestamp: float, with_date: bool = True) -> str:
    moment = datetime.fromtimestamp(timestamp)
    return moment.strftime("%m-%d %H:%M" if with_date else "%H:%M")


class MemoryPage:
    def __init__(self, owner) -> None:
        self.owner = owner
        self.memory = None
        self._day = ""
        self._summary_message: tuple[str, dict] | None = None
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
        self.open_button = owner._button("button.open_folder", self._open_folder)
        self.clear_button = owner._button("button.clear_memory", self._clear_all)
        self.location_row = owner._row(card, "field.memory_location", None, self.open_button, self.clear_button)
        self.remote_note = QLabel()
        self.remote_note.setObjectName("warning")
        self.remote_note.setWordWrap(True)
        self.remote_note.hide()
        layout.addSpacing(6)
        layout.addWidget(self.remote_note)

        self.search = QLineEdit()
        owner._bind(self.search.setPlaceholderText, "placeholder.memory_search")
        self.search.textChanged.connect(lambda _text: self._fill_entries())
        self.new_entry = QLineEdit()
        owner._bind(self.new_entry.setPlaceholderText, "placeholder.memory_new")
        self.new_entry.returnPressed.connect(self._add_entry)
        self.new_kind = SettingsComboBox()
        for kind in KINDS:
            self.new_kind.addItem(tr(f"memory.kind.{kind}"), kind)
        self.add_button = owner._button("button.add", self._add_entry)
        card = owner._section(layout, "section.memory_entries")
        owner._row(card, "field.memory_search", None, owner._sized(self.search, 260))
        owner._row(card, "field.memory_add", "desc.memory_add", owner._sized(self.new_entry, 220),
                   owner._sized(self.new_kind, 110), self.add_button)
        self.entry_card = SettingsCard()
        layout.addSpacing(8)
        layout.addWidget(self.entry_card)

        self.day_box = SettingsComboBox()
        self.day_box.currentIndexChanged.connect(self._day_chosen)
        self.delete_day_button = owner._button("button.delete_day", self._delete_day)
        card = owner._section(layout, "section.memory_days")
        owner._row(card, "field.memory_day", "desc.memory_day", owner._sized(self.day_box, 180),
                   self.delete_day_button)
        self.summary_card = SettingsCard()
        layout.addSpacing(8)
        layout.addWidget(self.summary_card)
        self.record_card = SettingsCard()
        layout.addSpacing(8)
        layout.addWidget(self.record_card)
        layout.addStretch()
        self.widget = page
        owner.rewrite_changed.connect(self.refresh)

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

    def refresh(self) -> None:
        on = self.memory.enabled if self.memory is not None else self.enabled.isChecked()
        if self.enabled.isChecked() != on:
            self.enabled.blockSignals(True)
            self.enabled.setChecked(on)
            self.enabled.blockSignals(False)
        location = str(self.memory.location()) if self.memory is not None else ""
        self.location_row.set_desc(tr("desc.memory_location", path=location) if location else "")
        endpoint = self.memory.remote_endpoint() if self.memory is not None else ""
        self.remote_note.setText(tr("memory.remote_note", endpoint=endpoint))
        self.remote_note.setVisible(bool(on and endpoint))
        self.clear_button.setEnabled(self.store is not None)
        self.open_button.setEnabled(self.store is not None)
        for index, kind in enumerate(KINDS):
            self.new_kind.setItemText(index, tr(f"memory.kind.{kind}"))
        self.add_button.setEnabled(on)
        self.new_entry.setEnabled(on)
        self._fill_entries()
        self._fill_days()

    def _keep_control(self, table: str, row_id: int, keep: str) -> SegmentedControl:
        control = SegmentedControl([(value, tr(KEEP_KEYS[value])) for value in KEEPS])
        control.buttons[keep].setChecked(True)
        control.changed.connect(lambda value: self._set_keep(table, row_id, value))
        return control

    def _small_button(self, key: str, handler) -> QPushButton:
        button = QPushButton(tr(key))
        button.setObjectName("secondary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(handler)
        return button

    @staticmethod
    def _text_row(text: str, desc: str, *controls: QWidget) -> SettingRow:
        row = SettingRow()
        row.title.setText(text)
        row.title.setObjectName("entryText")
        row.title.setWordWrap(True)
        row.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.set_desc(desc)
        for control in controls:
            row.control_layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    @staticmethod
    def _placeholder(card: SettingsCard, key: str, **values) -> None:
        row = SettingRow()
        row.title.setObjectName("rowDesc")
        row.title.setWordWrap(True)
        row.title.setText(tr(key, **values))
        card.add_row(row)

    def _fill_entries(self) -> None:
        self.entry_card.clear()
        entries = self.store.entries(self.search.text()) if self.store is not None else []
        if not entries:
            self._placeholder(self.entry_card, "memory.no_matches" if self.search.text().strip() else "memory.empty")
            return
        for entry in entries[:MAX_ROWS]:
            parts = [tr(f"memory.kind.{entry.kind}"), tr(f"memory.source.{entry.source}")]
            if entry.detail.get("time"):
                parts.append(tr("memory.time", time=entry.detail["time"]))
            parts.append(_when(entry.updated_at))
            self.entry_card.add_row(self._text_row(
                entry.content, " · ".join(parts), self._keep_control("entries", entry.id, entry.keep),
                self._small_button("button.edit", lambda _checked=False, e=entry: self._edit_entry(e)),
                self._small_button("button.delete", lambda _checked=False, e=entry: self._delete("entries", e.id))))
        if len(entries) > MAX_ROWS:
            self._placeholder(self.entry_card, "memory.more", count=len(entries) - MAX_ROWS)

    def _fill_days(self) -> None:
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
        self.summary_card.clear()
        self.record_card.clear()
        store, day = self.store, self._day
        if store is None or not day:
            self._placeholder(self.record_card, "memory.no_records")
            return
        records = store.records(day)
        summary = store.summary(day)
        busy = self.memory.summarizing(day)
        generate = QPushButton(tr("button.summarizing" if busy else
                                  "button.summarize_again" if summary else "button.summarize"))
        generate.setObjectName("primary")
        generate.setCursor(Qt.CursorShape.PointingHandCursor)
        generate.setEnabled(bool(records) and not busy)
        generate.clicked.connect(lambda: self._summarize(day))
        self.generate_button = generate
        controls = [generate]
        if summary is not None:
            controls += [self._keep_control("summaries", summary.id, summary.keep),
                         self._small_button("button.delete", lambda: self._delete("summaries", summary.id))]
        message = tr(self._summary_message[0], **self._summary_message[1]) if self._summary_message else ""
        text = summary.text if summary is not None else tr("memory.no_summary")
        row = self._text_row(text, message or (tr("memory.summary_made", when=_when(summary.created_at))
                                               if summary is not None else ""), *controls)
        if summary is None:
            row.title.setObjectName("rowDesc")
        self.summary_card.add_row(row)
        if not records:
            self._placeholder(self.record_card, "memory.no_records")
        for record in records:
            desc = _when(record.created_at, with_date=False)
            if record.explicit:
                desc += " · " + tr("memory.source.explicit")
            self.record_card.add_row(self._text_row(
                record.text, desc, self._keep_control("records", record.id, record.keep),
                self._small_button("button.delete", lambda _checked=False, r=record: self._delete("records", r.id))))

    # Actions -------------------------------------------------------------------------------------

    def _set_enabled(self, on: bool) -> None:
        if self.memory is not None:
            self.memory.set_enabled(on)
        else:
            self.owner.settings.setValue("memory/enabled", on)
            self.refresh()

    def _open_folder(self) -> None:
        if self.memory is not None:
            self.owner.open_url(QUrl.fromLocalFile(str(self.memory.location())).toString())

    def _clear_all(self) -> None:
        if self.store is not None and self.confirm(tr("memory.confirm_clear")):
            self.store.clear()
            self.memory.changed.emit()

    def _add_entry(self) -> None:
        text = self.new_entry.text().strip()
        if not text or self.store is None:
            return
        self.store.add_entry(text, kind=str(self.new_kind.currentData()), source="manual")
        self.new_entry.clear()
        self.memory.changed.emit()

    def _edit_entry(self, entry) -> None:
        text, ok = self.ask_text(tr("button.edit"), entry.content)
        if ok and text.strip():
            self.store.update_entry(entry.id, content=text)
            self.memory.changed.emit()

    def _set_keep(self, table: str, row_id: int, keep: str) -> None:
        if self.store is not None:
            self.store.set_keep(table, row_id, keep)
            self.memory.changed.emit()

    def _delete(self, table: str, row_id: int) -> None:
        if self.store is not None:
            self.store.delete(table, row_id)
            self.memory.changed.emit()

    def _day_chosen(self, _index: int) -> None:
        self._day = str(self.day_box.currentData() or "")
        self._summary_message = None
        self.delete_day_button.setEnabled(self.store is not None and self._day in self.store.days())
        self._fill_day()

    def _delete_day(self) -> None:
        if self.store is not None and self._day and self.confirm(tr("memory.confirm_delete_day", day=self._day)):
            self.store.delete_day(self._day)
            self.memory.changed.emit()

    def _summarize(self, day: str) -> None:
        self._summary_message = None
        if self.memory is not None and self.memory.summarize(day):
            self._fill_day()

    def _summary_done(self, day: str, reason: str | None) -> None:
        if reason is None:
            self._summary_message = None
        elif reason in ("empty", "model"):
            self._summary_message = (f"memory.summary_{reason}", {})
        else:
            self._summary_message = ("memory.summary_failed", {"reason": reason})
        if day == self._day:
            self._fill_day()
