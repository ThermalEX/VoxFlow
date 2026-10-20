"""Memory for the overlay: remember requests, fixes for misheard names, and the texts the user confirms.

Off by default. Until it is turned on nothing that was said is written to disk.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QTimer, Signal

from .memory_command import strip_command
from .memory_names import correct_names
from .memory_store import MemoryStore
from .paths import DATA_ROOT

SETTING = "memory/enabled"
PURGE_INTERVAL_MS = 60 * 60 * 1000


def memory_path(root: Path | None = None) -> Path:
    return (root if root is not None else DATA_ROOT) / "memory" / "memory.db"


class Memory(QObject):
    changed = Signal()  # rows were added, edited or forgotten

    def __init__(self, settings: QSettings, store: MemoryStore | None = None, root: Path | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._store = store
        self._root = root
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

    def close(self) -> None:
        self._purge_timer.stop()
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
        self.store.add_record(text)
        if explicit:
            self.store.add_entry(strip_command(text) or text, source="explicit")
        self.changed.emit()

    def purge(self) -> None:
        if self.store is not None and self.store.purge():
            self.changed.emit()
