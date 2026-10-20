"""What VoxFlow remembers, kept in a SQLite file on this computer.

Three kinds of rows: remembered entries (names, terms, events, facts), the texts the user confirmed, and daily
summaries. Every row is kept either for a week or forever, and can be moved between the two.
"""

import json
import sqlite3
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

WEEK = "week"
FOREVER = "forever"
KEEPS = (WEEK, FOREVER)
KEEP_SECONDS = 7 * 24 * 3600
KINDS = ("person", "term", "event", "fact")
SOURCES = ("explicit", "auto", "manual")
TABLES = ("entries", "records", "summaries")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, content TEXT NOT NULL, normalized TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL, keep TEXT NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY, text TEXT NOT NULL, day TEXT NOT NULL, keep TEXT NOT NULL,
    extracted INTEGER NOT NULL DEFAULT 0, explicit INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY, day TEXT NOT NULL UNIQUE, text TEXT NOT NULL, keep TEXT NOT NULL,
    created_at REAL NOT NULL);
"""


def normalize(text: str) -> str:
    """Compare entries ignoring case, width, spaces and punctuation."""
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P"))


def day_of(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class Entry:
    id: int
    kind: str
    content: str
    source: str
    keep: str
    created_at: float
    updated_at: float
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Record:
    id: int
    text: str
    day: str
    keep: str
    extracted: bool
    created_at: float
    explicit: bool = False  # the user asked VoxFlow to remember this text


@dataclass(frozen=True)
class Summary:
    id: int
    day: str
    text: str
    keep: str
    created_at: float


class MemoryStore:
    def __init__(self, path: str | Path, clock=time.time) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _run(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._db.execute(sql, args)
            self._db.commit()
            return cursor

    def _rows(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    # Entries -----------------------------------------------------------------------------------

    @staticmethod
    def _entry(row: tuple) -> Entry:
        id_, kind, content, _normalized, detail, source, keep, created_at, updated_at = row
        return Entry(id_, kind, content, source, keep, created_at, updated_at, json.loads(detail or "{}"))

    def add_entry(self, content: str, kind: str = "fact", source: str = "manual", keep: str | None = None,
                  detail: dict | None = None) -> Entry | None:
        """Remember something; mentioning a known entry again refreshes it instead of adding a copy.

        Entries the user asked for (explicit or manual) are kept forever unless told otherwise; extracted ones
        for a week. A repeated mention never shortens how long an entry is kept.
        """
        content = content.strip()
        key = normalize(content)
        if not key:
            return None
        kind = kind if kind in KINDS else "fact"
        source = source if source in SOURCES else "manual"
        keep = keep if keep in KEEPS else (WEEK if source == "auto" else FOREVER)
        now = self._clock()
        existing = self._rows("SELECT * FROM entries WHERE normalized = ?", (key,))
        if existing:
            entry = self._entry(existing[0])
            keep = FOREVER if FOREVER in (keep, entry.keep) else WEEK
            source = entry.source if entry.source != "auto" else source
            merged = entry.detail | (detail or {})
            self._run("UPDATE entries SET keep = ?, source = ?, detail = ?, updated_at = ? WHERE id = ?",
                      (keep, source, json.dumps(merged, ensure_ascii=False), now, entry.id))
            return self.entry(entry.id)
        cursor = self._run(
            "INSERT INTO entries (kind, content, normalized, detail, source, keep, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, content, key, json.dumps(detail or {}, ensure_ascii=False), source, keep, now, now))
        return self.entry(cursor.lastrowid)

    def entry(self, entry_id: int) -> Entry | None:
        rows = self._rows("SELECT * FROM entries WHERE id = ?", (entry_id,))
        return self._entry(rows[0]) if rows else None

    def update_entry(self, entry_id: int, content: str | None = None, kind: str | None = None) -> None:
        current = self.entry(entry_id)
        if current is None:
            return
        content = current.content if content is None or not normalize(content) else content.strip()
        kind = kind if kind in KINDS else current.kind
        self._run("UPDATE entries SET content = ?, normalized = ?, kind = ?, updated_at = ? WHERE id = ?",
                  (content, normalize(content), kind, self._clock(), entry_id))

    def entries(self, search: str = "") -> list[Entry]:
        rows = self._rows("SELECT * FROM entries ORDER BY updated_at DESC, id DESC")
        entries = [self._entry(row) for row in rows]
        key = normalize(search)
        return [entry for entry in entries if key in normalize(entry.content)] if key else entries

    def names(self) -> list[str]:
        """People and terms, the entries used to correct misheard words."""
        return [row[0] for row in self._rows("SELECT content FROM entries WHERE kind IN ('person', 'term')")]

    # Records -----------------------------------------------------------------------------------

    def add_record(self, text: str, keep: str = WEEK, explicit: bool = False) -> Record | None:
        text = text.strip()
        if not text:
            return None
        now = self._clock()
        cursor = self._run("INSERT INTO records (text, day, keep, explicit, created_at) VALUES (?, ?, ?, ?, ?)",
                           (text, day_of(now), keep if keep in KEEPS else WEEK, int(explicit), now))
        return self.record(cursor.lastrowid)

    _RECORD_COLUMNS = "SELECT id, text, day, keep, extracted, created_at, explicit FROM records"

    @staticmethod
    def _record(row: tuple) -> Record:
        id_, text, day, keep, extracted, created_at, explicit = row
        return Record(id_, text, day, keep, bool(extracted), created_at, bool(explicit))

    def record(self, record_id: int) -> Record | None:
        rows = self._rows(self._RECORD_COLUMNS + " WHERE id = ?", (record_id,))
        return self._record(rows[0]) if rows else None

    def records(self, day: str | None = None) -> list[Record]:
        rows = self._rows(self._RECORD_COLUMNS + (" WHERE day = ?" if day else "") + " ORDER BY created_at, id",
                          (day,) if day else ())
        return [self._record(row) for row in rows]

    def entries_since(self, timestamp: float) -> list[Entry]:
        """Entries added or mentioned again since a moment, oldest first (what a day brought)."""
        rows = self._rows("SELECT * FROM entries WHERE updated_at >= ? ORDER BY updated_at, id", (timestamp,))
        return [self._entry(row) for row in rows]

    def days(self) -> list[str]:
        """Days with confirmed texts or a summary, newest first."""
        rows = self._rows("SELECT day FROM records UNION SELECT day FROM summaries ORDER BY day DESC")
        return [row[0] for row in rows]

    def pending_records(self) -> list[Record]:
        return [record for record in self.records() if not record.extracted]

    def mark_extracted(self, record_id: int) -> None:
        self._run("UPDATE records SET extracted = 1 WHERE id = ?", (record_id,))

    # Summaries ---------------------------------------------------------------------------------

    def save_summary(self, day: str, text: str) -> Summary:
        """Store a day's summary, replacing an older one; a summary moved to forever stays there."""
        existing = self.summary(day)
        keep = existing.keep if existing else WEEK
        self._run("INSERT OR REPLACE INTO summaries (day, text, keep, created_at) VALUES (?, ?, ?, ?)",
                  (day, text.strip(), keep, self._clock()))
        return self.summary(day)

    def summary(self, day: str) -> Summary | None:
        rows = self._rows("SELECT id, day, text, keep, created_at FROM summaries WHERE day = ?", (day,))
        return Summary(*rows[0]) if rows else None

    # Keeping and forgetting --------------------------------------------------------------------

    def set_keep(self, table: str, row_id: int, keep: str) -> None:
        if table not in TABLES or keep not in KEEPS:
            raise ValueError(f"cannot keep {table} rows as {keep!r}")
        # Moving a row back to a week starts its week now, so it is not forgotten the same moment.
        stamp = "updated_at" if table == "entries" else "created_at"
        extra = f", {stamp} = ?" if keep == WEEK else ""
        args = (keep, self._clock(), row_id) if keep == WEEK else (keep, row_id)
        self._run(f"UPDATE {table} SET keep = ?{extra} WHERE id = ?", args)

    def delete(self, table: str, row_id: int) -> None:
        if table not in TABLES:
            raise ValueError(f"unknown table {table}")
        self._run(f"DELETE FROM {table} WHERE id = ?", (row_id,))

    def delete_day(self, day: str) -> None:
        self._run("DELETE FROM records WHERE day = ?", (day,))
        self._run("DELETE FROM summaries WHERE day = ?", (day,))

    def purge(self) -> int:
        """Forget what was kept for a week and is now older than that; returns how many rows went."""
        cutoff = self._clock() - KEEP_SECONDS
        removed = 0
        for table, stamp in (("entries", "updated_at"), ("records", "created_at"), ("summaries", "created_at")):
            removed += self._run(f"DELETE FROM {table} WHERE keep = ? AND {stamp} < ?", (WEEK, cutoff)).rowcount
        return removed

    def clear(self) -> None:
        for table in TABLES:
            self._run(f"DELETE FROM {table}")
