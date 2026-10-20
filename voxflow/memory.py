"""Memory for the overlay: remember requests, fixes for misheard names, the texts the user confirms, and
what the rewrite model makes of them (remembered entries, fill-ins, daily summaries).

Off by default. Until it is turned on nothing that was said is written to disk.
"""

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QTimer, Signal

from .i18n import describe_error
from .memory_command import strip_command
from .memory_names import correct_names
from .memory_store import FOREVER, WEEK, Entry, MemoryStore, Record, day_of
from .paths import DATA_ROOT
from .rewriter import RewriteConfig, RewriteError

SETTING = "memory/enabled"
PURGE_INTERVAL_MS = 60 * 60 * 1000
RETRY_SECONDS = 60  # after the model could not be reached, wait before extracting again
MAX_RELATED = 5
MIN_OVERLAP = 2
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")
_HAN_RUN = re.compile(r"[㐀-鿿]+")


def memory_path(root: Path | None = None) -> Path:
    return (root if root is not None else DATA_ROOT) / "memory" / "memory.db"


def _keys(text: str) -> set[str]:
    """Character pairs of Chinese runs and longer Latin words: enough to tell what a text is about."""
    keys = {word.casefold() for word in _LATIN_WORD.findall(text)}
    for run in _HAN_RUN.findall(text):
        keys.update(run[index:index + 2] for index in range(len(run) - 1))
    return keys


def describe_entry(entry: Entry) -> str:
    when = entry.detail.get("time")
    return f"{entry.content}（{when}）" if when and when not in entry.content else entry.content


class Memory(QObject):
    changed = Signal()  # rows were added, edited or forgotten
    summary_ready = Signal(str)  # day
    summary_failed = Signal(str, str)  # day, reason

    def __init__(self, settings: QSettings, store: MemoryStore | None = None, root: Path | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._store = store
        self._root = root
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="memory")
        self._client_source = lambda: None
        self._idle = lambda: True
        self._extracting: tuple[Future, Record] | None = None
        self._summaries: dict[str, Future] = {}
        self._retry_at = 0.0
        self._purge_timer = QTimer(self)
        self._purge_timer.setInterval(PURGE_INTERVAL_MS)
        self._purge_timer.timeout.connect(self.purge)
        self._purge_timer.start()
        self.purge()

    @property
    def enabled(self) -> bool:
        return self.settings.value(SETTING, False, type=bool)

    def set_enabled(self, enabled: bool) -> None:
        self.settings.setValue(SETTING, bool(enabled))
        if enabled:
            self.purge()
        self.changed.emit()

    @property
    def store(self) -> MemoryStore | None:
        """The database, opened on first use; it is never created while memory is off."""
        if self._store is None and (self.enabled or memory_path(self._root).is_file()):
            self._store = MemoryStore(memory_path(self._root))
        return self._store

    def location(self) -> Path:
        return memory_path(self._root).parent

    def remote_endpoint(self) -> str:
        """Where memory text goes when smart editing uses an online model, or "" when it stays local."""
        config = RewriteConfig.from_settings(self.settings)
        return config.base_url if config.enabled and config.provider == "custom" else ""

    def connect_model(self, client_source, idle) -> None:
        """`client_source()` gives a ready rewrite client or None; `idle()` says the overlay will not need the
        model for a while, so background extraction never delays the polishing of the next sentence."""
        self._client_source = client_source
        self._idle = idle

    def close(self) -> None:
        self._purge_timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self._store is not None:
            self._store.close()
            self._store = None

    # Used by the overlay -----------------------------------------------------------------------

    def strip_command(self, text: str) -> str | None:
        """The dictation without a leading "remember …", or None when memory is off or it is no request."""
        return strip_command(text) if self.enabled else None

    def correct(self, text: str) -> str:
        if not self.enabled or self.store is None:
            return text
        return correct_names(text, self.store.names())

    def remember(self, text: str, explicit: bool = False) -> None:
        """Keep a confirmed text; a "remember …" request also becomes an entry kept forever."""
        if not self.enabled or not text.strip():
            return
        self.store.add_record(text, explicit=explicit)
        if explicit:
            self.store.add_entry(strip_command(text) or text, source="explicit")
        self.changed.emit()

    def related(self, text: str) -> list[str]:
        """Remembered entries that share words with a text, best first, as lines for the fill-in task."""
        if not self.enabled or self.store is None:
            return []
        keys = _keys(text)
        scored = []
        for entry in self.store.entries():
            overlap = len(keys & _keys(describe_entry(entry)))
            if overlap >= MIN_OVERLAP:
                scored.append((overlap, entry.updated_at, describe_entry(entry)))
        scored.sort(reverse=True)
        return [line for _overlap, _when, line in scored[:MAX_RELATED]]

    def purge(self) -> None:
        if self.store is not None and self.store.purge():
            self.changed.emit()

    # Background work ---------------------------------------------------------------------------

    def poll(self) -> None:
        """Collect finished model calls and start the next extraction; driven by the overlay's timer."""
        self._finish_extraction()
        self._finish_summaries()
        if (not self.enabled or self._extracting is not None or time.monotonic() < self._retry_at
                or not self._idle()):
            return
        store = self.store
        pending = store.pending_records() if store is not None else []
        client = self._client_source() if pending else None
        if client is None:
            return
        record = pending[0]
        future = self.executor.submit(client.extract, record.text, date.fromtimestamp(record.created_at))
        self._extracting = (future, record)

    def _finish_extraction(self) -> None:
        if self._extracting is None or not self._extracting[0].done():
            return
        future, record = self._extracting
        self._extracting = None
        try:
            items = future.result()
        except RewriteError as exc:
            if exc.kind in ("unreachable", "timeout", "starting"):
                self._retry_at = time.monotonic() + RETRY_SECONDS  # the record waits for the model
                return
            items = []  # an unusable answer: do not ask about this text again
        except Exception:  # noqa: BLE001 - any other failure of one text must not stop the others
            items = []
        store = self.store
        if store is None or store.record(record.id) is None:
            return
        keep = FOREVER if record.explicit else WEEK
        for item in items:
            detail = {"time": item["time"]} if item.get("time") else None
            store.add_entry(item["content"], kind=item["kind"], source="auto", keep=keep, detail=detail)
        store.mark_extracted(record.id)
        self.changed.emit()

    def summarizing(self, day: str) -> bool:
        return day in self._summaries

    def summarize(self, day: str) -> bool:
        """Start summarizing a day in the background; summary_ready or summary_failed follows."""
        store = self.store
        texts = [record.text for record in store.records(day)] if store is not None else []
        client = self._client_source()
        if self.summarizing(day):
            return False
        if not texts:
            self.summary_failed.emit(day, "empty")
            return False
        if client is None:
            self.summary_failed.emit(day, "model")
            return False
        start = datetime.strptime(day, "%Y-%m-%d").timestamp()
        memories = [describe_entry(entry) for entry in store.entries_since(start) if day_of(entry.updated_at) == day]
        self._summaries[day] = self.executor.submit(client.summarize, date.fromisoformat(day), texts, memories)
        return True

    def _finish_summaries(self) -> None:
        for day, future in list(self._summaries.items()):
            if not future.done():
                continue
            del self._summaries[day]
            try:
                text = future.result()
            except Exception as exc:  # noqa: BLE001 - shown to the user, who can try again
                self.summary_failed.emit(day, describe_error(exc))
                continue
            if self.store is not None:
                self.store.save_summary(day, text)
                self.summary_ready.emit(day)
                self.changed.emit()
