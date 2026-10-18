import hashlib
import io
import json
import time
import urllib.error
import zipfile

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from voxflow.catalog import CatalogFile, CatalogItem, read_installed
from voxflow.downloads import DownloadManager


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_item(item_id, path, data, dest, group="", extract=False, kind="rewrite", sha256=None):
    file = CatalogFile("ThermalEX/voxflow-rewrite", "v4", path, len(data), sha256 or sha(data), dest, extract)
    return CatalogItem(item_id, kind, group, False, False, False, {"en": item_id, "zh": item_id},
                       {"en": "", "zh": ""}, (file,), dest)


class FakeResponse:
    def __init__(self, data: bytes, status: int, fail_after: int | None, delay=None):
        self._stream = io.BytesIO(data)
        self.status = status
        self._fail_after = fail_after
        self._sent = 0
        self._delay = delay

    def read(self, size=-1):
        if self._delay:
            self._delay()
        chunk = self._stream.read(min(size, 64 * 1024) if size and size > 0 else -1)
        self._sent += len(chunk)
        if self._fail_after is not None and self._sent > self._fail_after:
            raise ConnectionError("connection reset")
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def close(self):
        pass


class FakeNet:
    """Serves bytes by URL path; can drop the connection, ignore Range, refuse a host or be slow."""

    def __init__(self, files: dict, fail_after=None, honor_range=True, down_hosts=(), slow_hosts=(), clock=None,
                 pause=0.0):
        self.files = files
        self.fail_after = dict(fail_after or {})
        self.honor_range = honor_range
        self.down_hosts = set(down_hosts)
        self.slow_hosts = set(slow_hosts)
        self.clock = clock
        self.pause = pause  # real seconds per read, so a cancel can arrive mid-download
        self.requests = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.requests.append((url, request.get_header("Range")))
        host = url.split("/")[2]
        if host in self.down_hosts:
            raise urllib.error.URLError("unreachable")
        data = self.files[url.split("/resolve/")[1].split("/", 1)[1]]
        start = 0
        status = 200
        if request.get_header("Range") and self.honor_range:
            start = int(request.get_header("Range").split("=")[1].rstrip("-"))
            status = 206
        fail = self.fail_after.pop(url.rsplit("/", 1)[1], None)
        delay = (lambda: self.clock.advance(1.0)) if host in self.slow_hosts else None
        if self.pause:
            delay = lambda: time.sleep(self.pause)
        return FakeResponse(data[start:], status, fail, delay)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def advance(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


def run(manager, items, source="huggingface", timeout=10.0):
    QApplication.instance() or QApplication([])
    states, failures, progress = {}, {}, []
    manager.item_state.connect(lambda item_id, state: states.__setitem__(item_id, state))
    manager.item_failed.connect(lambda item_id, key: failures.__setitem__(item_id, key))
    manager.progress.connect(lambda *values: progress.append(values))
    finished = []
    manager.all_done.connect(lambda: finished.append(True))
    manager.start(items, source)
    deadline = time.monotonic() + timeout
    while not finished and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    assert finished, "downloads did not finish"
    QCoreApplication.processEvents()
    return states, failures, progress


def test_downloads_verifies_and_installs(tmp_path):
    first, second = b"a" * 300_000, b"b" * 1000
    net = FakeNet({"one.gguf": first, "two.gguf": second})
    items = [make_item("one", "one.gguf", first, "runtime/models/one.gguf"),
             make_item("two", "two.gguf", second, "runtime/models/two.gguf")]
    states, failures, progress = run(DownloadManager(tmp_path, opener=net), items)
    assert states == {"one": "installed", "two": "installed"} and not failures
    assert (tmp_path / "runtime/models/one.gguf").read_bytes() == first
    assert set(read_installed(tmp_path)) == {"one", "two"}
    last_one = [values for values in progress if values[0] == "one"][-1]
    assert last_one[1] == last_one[2] == len(first)
    assert not list(tmp_path.rglob("*.part"))


def test_resumes_from_partial_file(tmp_path):
    data = bytes(range(256)) * 1000
    part = tmp_path / "runtime/models/m.gguf.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(data[:100_000])
    net = FakeNet({"m.gguf": data})
    states, _failures, _progress = run(DownloadManager(tmp_path, opener=net), [make_item("m", "m.gguf", data, "runtime/models/m.gguf")])
    assert states["m"] == "installed"
    assert net.requests[0][1] == "bytes=100000-"
    assert (tmp_path / "runtime/models/m.gguf").read_bytes() == data


def test_server_without_range_support_restarts_the_file(tmp_path):
    data = b"x" * 50_000
    part = tmp_path / "runtime/models/m.gguf.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"x" * 10_000)
    net = FakeNet({"m.gguf": data}, honor_range=False)
    states, _failures, _progress = run(DownloadManager(tmp_path, opener=net), [make_item("m", "m.gguf", data, "runtime/models/m.gguf")])
    assert states["m"] == "installed"
    assert (tmp_path / "runtime/models/m.gguf").read_bytes() == data


def test_interrupted_download_is_not_installed(tmp_path):
    data = b"z" * 400_000
    net = FakeNet({"m.gguf": data}, fail_after={"m.gguf": 150_000})
    states, failures, _progress = run(DownloadManager(tmp_path, opener=net), [make_item("m", "m.gguf", data, "runtime/models/m.gguf")])
    assert states["m"] == "failed" and failures["m"] == "download.error.network"
    assert not (tmp_path / "runtime/models/m.gguf").exists()
    assert (tmp_path / "runtime/models/m.gguf.part").stat().st_size > 0  # kept for resuming
    assert "m" not in read_installed(tmp_path)


def test_hash_mismatch_discards_file(tmp_path):
    data = b"tampered" * 1000
    net = FakeNet({"m.gguf": data})
    item = make_item("m", "m.gguf", data, "runtime/models/m.gguf", sha256="0" * 64)
    states, failures, _progress = run(DownloadManager(tmp_path, opener=net), [item])
    assert failures["m"] == "download.error.hash"
    assert not (tmp_path / "runtime/models/m.gguf").exists()
    assert not (tmp_path / "runtime/models/m.gguf.part").exists()


def test_write_error_fails_item(tmp_path):
    (tmp_path / "runtime").write_text("not a folder")  # the destination folder cannot be created
    data, other = b"m" * 1000, b"o" * 1000
    net = FakeNet({"m.gguf": data, "o.onnx": other})
    items = [make_item("m", "m.gguf", data, "runtime/models/m.gguf"),
             make_item("o", "o.onnx", other, "models/o.onnx", kind="asr")]
    states, failures, _progress = run(DownloadManager(tmp_path, opener=net), items)
    assert failures["m"] == "download.error.disk"
    assert states["o"] == "installed"


def test_auto_switches_to_mirror_when_slow(tmp_path):
    clock = FakeClock()
    data = b"s" * (64 * 1024 * 40)
    net = FakeNet({"m.gguf": data}, slow_hosts={"huggingface.co"}, clock=clock)
    manager = DownloadManager(tmp_path, opener=net, clock=clock)
    states, _failures, _progress = run(manager, [make_item("m", "m.gguf", data, "runtime/models/m.gguf")], source="auto")
    assert states["m"] == "installed"
    hosts = [url.split("/")[2] for url, _range in net.requests]
    assert hosts[0] == "huggingface.co" and hosts[-1] == "hf-mirror.com"
    assert net.requests[-1][1] is not None  # continues from where the slow download stopped


def test_auto_switches_to_mirror_when_unreachable(tmp_path):
    data = b"u" * 1000
    net = FakeNet({"m.gguf": data}, down_hosts={"huggingface.co"})
    states, _failures, _progress = run(DownloadManager(tmp_path, opener=net),
                                       [make_item("m", "m.gguf", data, "runtime/models/m.gguf")], source="auto")
    assert states["m"] == "installed"


def test_mirror_only_never_touches_hugging_face(tmp_path):
    data = b"u" * 1000
    net = FakeNet({"m.gguf": data})
    run(DownloadManager(tmp_path, opener=net), [make_item("m", "m.gguf", data, "runtime/models/m.gguf")], source="mirror")
    assert all(url.startswith("https://hf-mirror.com/") for url, _range in net.requests)


def test_cancel_removes_partial_file(tmp_path):
    QApplication.instance() or QApplication([])
    data = b"c" * (64 * 1024 * 50)
    manager = DownloadManager(tmp_path, opener=FakeNet({"m.gguf": data}, pause=0.01))
    manager.progress.connect(lambda item_id, *_rest: manager.cancel(item_id))
    states, _failures, _progress = run(manager, [make_item("m", "m.gguf", data, "runtime/models/m.gguf")])
    assert states["m"] == "cancelled"
    assert not list(tmp_path.rglob("m.gguf*"))


def test_zip_install_keeps_only_server_files_and_replaces_other_variant(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in ("llama-server.exe", "llama-cli.exe", "ggml.dll", "ggml-vulkan.dll", "llama-cli-impl.dll",
                     "llama-server-impl.dll"):
            archive.writestr(name, name)
    data = buffer.getvalue()
    old = tmp_path / "runtime/llama.cpp"
    old.mkdir(parents=True)
    (old / "ggml-cuda.dll").write_bytes(b"old build")
    (tmp_path / "installed.json").write_text(json.dumps({"llama-cuda": ["x"]}), encoding="utf-8")
    item = make_item("llama-vulkan", "runtime/llama.zip", data, "runtime/llama.cpp", group="llama", extract=True,
                     kind="runtime")
    states, failures, _progress = run(DownloadManager(tmp_path, opener=FakeNet({"runtime/llama.zip": data})), [item])
    assert states["llama-vulkan"] == "installed", failures
    assert sorted(path.name for path in old.iterdir()) == [
        "ggml-vulkan.dll", "ggml.dll", "llama-server-impl.dll", "llama-server.exe"]
    assert set(read_installed(tmp_path)) == {"llama-vulkan"}  # the recorded CUDA build shared the "llama" group


def test_remove_deletes_files_and_record(tmp_path):
    data = b"r" * 1000
    item = make_item("m", "m.gguf", data, "runtime/models/m.gguf")
    manager = DownloadManager(tmp_path, opener=FakeNet({"m.gguf": data}))
    run(manager, [item])
    manager.remove(item)
    assert not (tmp_path / "runtime/models/m.gguf").exists()
    assert "m" not in read_installed(tmp_path)
