"""Download catalog items in the background: one at a time, resumable, verified by SHA-256 before install."""

import hashlib
import json
import shutil
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .catalog import INSTALLED_FILE, CatalogFile, CatalogItem, builtin_catalog, file_url, read_installed

CHUNK = 1024 * 1024
PROGRESS_INTERVAL = 0.2  # seconds between progress signals
SLOW_WINDOW = 10.0  # "auto" judges Hugging Face after this many seconds...
SLOW_BYTES_PER_SECOND = 200 * 1024  # ...and switches to the mirror below this average speed
DOWNLOADS_DIR = "downloads"  # archives wait here until they are unpacked


class _Cancelled(Exception):
    pass


class _DiskError(Exception):
    pass


class _NetworkError(Exception):
    pass


class _HashError(Exception):
    pass


class _SwitchToMirror(Exception):
    pass


def _keep_server_file(name: str) -> bool:
    """From a llama.cpp archive keep llama-server and the libraries it loads, not the other tools."""
    lower = name.lower()
    if lower.endswith(".exe"):
        return lower == "llama-server.exe"
    if lower.endswith("-impl.dll"):
        return lower == "llama-server-impl.dll"
    return True


class DownloadManager(QObject):
    progress = Signal(str, object, object, float)  # item id, bytes done, bytes total, bytes per second
    item_state = Signal(str, str)  # queued, downloading, verifying, installed, failed, cancelled
    item_failed = Signal(str, str)  # item id, i18n key of the reason
    all_done = Signal()

    def __init__(self, root: Path, opener=urllib.request.urlopen, clock=time.monotonic) -> None:
        super().__init__()
        self.root = Path(root)
        self._open = opener
        self._clock = clock
        self._lock = threading.Lock()
        self._queue: list[tuple[CatalogItem, str]] = []
        self._cancelled: set[str] = set()
        self._thread: threading.Thread | None = None

    # Public API ---------------------------------------------------------------------------------

    def start(self, items: list[CatalogItem], source: str) -> None:
        with self._lock:
            for item in items:
                self._cancelled.discard(item.id)
                self._queue.append((item, source))
                self.item_state.emit(item.id, "queued")
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, name="voxflow-downloads", daemon=True)
                self._thread.start()

    def cancel(self, item_id: str) -> None:
        with self._lock:
            self._cancelled.add(item_id)

    def cancel_all(self) -> None:
        with self._lock:
            self._cancelled.update(item.id for item, _source in self._queue)
            if self._current is not None:
                self._cancelled.add(self._current)

    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def remove(self, item: CatalogItem) -> None:
        """Delete an installed item's files and forget it."""
        for file in item.files:
            target = self.root / file.dest
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink()
        record = read_installed(self.root)
        record.pop(item.id, None)
        self._write_record(record)

    # Worker -------------------------------------------------------------------------------------

    _current: str | None = None

    def _work(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    self._current = None
                    break
                item, source = self._queue.pop(0)
                self._current = item.id
            if item.id in self._cancelled:
                self.item_state.emit(item.id, "cancelled")
                continue
            self._download_item(item, source)
        self.all_done.emit()

    def _download_item(self, item: CatalogItem, source: str) -> None:
        self.item_state.emit(item.id, "downloading")
        total = item.size
        done_before = 0
        self._last_emit = float("-inf")
        try:
            for file in item.files:
                part = self._part_path(file)
                self._fetch(item, file, part, source, done_before, total)
                self.item_state.emit(item.id, "verifying")
                if self._sha256(part) != file.sha256:
                    part.unlink(missing_ok=True)
                    raise _HashError()
                self._finish_file(file, part)
                done_before += file.size
            self._install(item)
        except _Cancelled:
            for file in item.files:
                self._part_path(file).unlink(missing_ok=True)
            self.item_state.emit(item.id, "cancelled")
            return
        except _HashError:
            self._fail(item, "download.error.hash")
            return
        except _NetworkError:
            self._fail(item, "download.error.network")
            return
        except (_DiskError, OSError, zipfile.BadZipFile):
            self._fail(item, "download.error.disk")
            return
        self.progress.emit(item.id, total, total, 0.0)
        self.item_state.emit(item.id, "installed")

    def _fail(self, item: CatalogItem, key: str) -> None:
        self.item_failed.emit(item.id, key)
        self.item_state.emit(item.id, "failed")

    def _part_path(self, file: CatalogFile) -> Path:
        if file.extract:
            return self.root / DOWNLOADS_DIR / (Path(file.path).name + ".part")
        return self.root / (file.dest + ".part")

    def _fetch(self, item: CatalogItem, file: CatalogFile, part: Path, source: str, done_before: int,
               total: int) -> None:
        current = "huggingface" if source == "auto" else source
        while True:
            try:
                self._fetch_from(item, file, part, current, source == "auto" and current == "huggingface",
                                 done_before, total)
                return
            except _SwitchToMirror:
                current = "mirror"

    def _fetch_from(self, item: CatalogItem, file: CatalogFile, part: Path, source: str, may_switch: bool,
                    done_before: int, total: int) -> None:
        try:
            part.parent.mkdir(parents=True, exist_ok=True)
            have = part.stat().st_size if part.exists() else 0
        except OSError as exc:
            raise _DiskError() from exc
        if have >= file.size > 0:
            return  # already complete; verification decides whether it is good
        headers = {"User-Agent": "VoxFlow"}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            response = self._open(urllib.request.Request(file_url(file, source), headers=headers), timeout=30)
        except Exception as exc:  # unreachable host, HTTP error, timeout
            if may_switch:
                raise _SwitchToMirror() from exc
            raise _NetworkError() from exc
        with response:
            status = getattr(response, "status", None) or response.getcode()
            mode = "ab" if have and status == 206 else "wb"
            if mode == "wb":
                have = 0
            try:
                output = part.open(mode)
            except OSError as exc:
                raise _DiskError() from exc
            with output:
                started, received = self._clock(), 0
                while True:
                    if item.id in self._cancelled:
                        raise _Cancelled()
                    try:
                        chunk = response.read(CHUNK)
                    except Exception as exc:  # connection reset, timeout
                        if may_switch:
                            raise _SwitchToMirror() from exc
                        raise _NetworkError() from exc
                    if not chunk:
                        break
                    try:
                        output.write(chunk)
                    except OSError as exc:
                        raise _DiskError() from exc
                    have += len(chunk)
                    received += len(chunk)
                    elapsed = self._clock() - started
                    speed = received / elapsed if elapsed > 0 else 0.0
                    self._report(item.id, done_before + have, total, speed)
                    if may_switch and elapsed >= SLOW_WINDOW and speed < SLOW_BYTES_PER_SECOND:
                        raise _SwitchToMirror()
        if have < file.size:
            raise _NetworkError()

    def _report(self, item_id: str, done: int, total: int, speed: float) -> None:
        now = time.monotonic()
        if now - self._last_emit >= PROGRESS_INTERVAL:
            self._last_emit = now
            self.progress.emit(item_id, done, total, speed)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(CHUNK), b""):
                digest.update(block)
        return digest.hexdigest()

    def _finish_file(self, file: CatalogFile, part: Path) -> None:
        final = part.with_name(part.name[: -len(".part")])
        try:
            final.parent.mkdir(parents=True, exist_ok=True)
            part.replace(final)
        except OSError as exc:
            raise _DiskError() from exc

    def _install(self, item: CatalogItem) -> None:
        archives = [file for file in item.files if file.extract]
        if archives:
            dest = self.root / archives[0].dest
            staging = dest.with_name(dest.name + ".new")
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True)
            for file in archives:
                archive_path = self.root / DOWNLOADS_DIR / Path(file.path).name
                with zipfile.ZipFile(archive_path) as archive:
                    for member in archive.infolist():
                        name = Path(member.filename).name
                        if member.is_dir() or not name or not _keep_server_file(name):
                            continue
                        with archive.open(member) as source, (staging / name).open("wb") as target:
                            shutil.copyfileobj(source, target)
            if dest.exists():
                shutil.rmtree(dest)
            staging.replace(dest)
            for file in archives:
                (self.root / DOWNLOADS_DIR / Path(file.path).name).unlink(missing_ok=True)
        record = read_installed(self.root)
        if item.group:
            groups = {known.id: known.group for known in builtin_catalog()}
            for other in list(record):
                other_group = record[other].get("group") if isinstance(record[other], dict) else groups.get(other)
                if other != item.id and other_group == item.group:
                    del record[other]
        record[item.id] = {"group": item.group, "sha256": [file.sha256 for file in item.files]}
        self._write_record(record)

    def _write_record(self, record: dict) -> None:
        path = self.root / INSTALLED_FILE
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
        temporary.replace(path)

