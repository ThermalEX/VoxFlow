import time

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication

from voxflow import i18n
from voxflow.catalog import builtin_catalog
from voxflow.download_panel import DownloadPanel


class FakeManager(QObject):
    progress = Signal(str, object, object, float)
    item_state = Signal(str, str)
    item_failed = Signal(str, str)
    all_done = Signal()

    def __init__(self):
        super().__init__()
        self.started = []
        self.cancelled = []
        self.busy = False

    def start(self, items, source):
        self.started.append(([item.id for item in items], source))

    def cancel(self, item_id):
        self.cancelled.append(item_id)

    def cancel_all(self):
        self.cancelled.append("*")

    def states(self):
        return dict(getattr(self, "current_states", {}))

    def is_busy(self):
        return self.busy


def make_panel(tmp_path, online=True, nvidia=True, compact=False):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    manager = FakeManager()
    panel = DownloadPanel(settings, manager, root=tmp_path, fetch=lambda source: (builtin_catalog(), online),
                          has_nvidia=lambda: nvidia, compact=compact)
    return panel, manager, settings


def loaded(panel, timeout=3.0):
    panel.load()
    deadline = time.monotonic() + timeout
    while not panel.rows and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert panel.rows
    return panel


def test_load_lists_items_and_marks_installed(tmp_path):
    model = tmp_path / "runtime/models/voxflow-rewrite-v4-q4_k_m.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"")
    panel, _manager, _settings = make_panel(tmp_path)
    loaded(panel)
    assert set(panel.rows) == {item.id for item in builtin_catalog()}
    row = panel.rows["rewrite-v4-q4"]
    assert not row.checkbox.isEnabled() and row.status_label.text() == "Installed"
    assert panel.rows["rewrite-v4-q8"].checkbox.isEnabled()


def test_variants_in_same_group_are_exclusive(tmp_path):
    panel, _manager, _settings = loaded(make_panel(tmp_path)[0]), None, None
    panel.rows["llama-vulkan"].checkbox.setChecked(True)
    panel.rows["llama-cuda"].checkbox.setChecked(True)
    assert not panel.rows["llama-vulkan"].checkbox.isChecked()
    assert panel.selected_ids() == ["llama-cuda"]


def test_nvidia_build_disabled_without_nvidia_gpu(tmp_path):
    panel, _manager, _settings = make_panel(tmp_path, nvidia=False)
    loaded(panel)
    row = panel.rows["llama-cuda"]
    assert not row.checkbox.isEnabled()
    assert row.status_label.text() == "Needs an NVIDIA graphics card"


def test_download_selected_passes_items_and_source(tmp_path):
    panel, manager, settings = make_panel(tmp_path)
    loaded(panel)
    panel.source_control.set_value("mirror")
    panel.rows["asr-sensevoice"].checkbox.setChecked(True)
    panel.rows["rewrite-v4-q8"].checkbox.setChecked(True)
    assert panel.summary.text().startswith("2 selected")
    panel.download_button.click()
    assert manager.started == [(["asr-sensevoice", "rewrite-v4-q8"], "mirror")]
    assert settings.value("downloads/source") == "mirror"


def test_source_choice_is_remembered(tmp_path):
    panel, _manager, settings = make_panel(tmp_path)
    assert panel.source_control.value() == "auto"
    panel.source_control.set_value("huggingface")
    reopened = DownloadPanel(settings, FakeManager(), root=tmp_path, fetch=lambda source: (builtin_catalog(), True),
                             has_nvidia=lambda: True)
    assert reopened.source_control.value() == "huggingface"


def test_progress_text_shows_percent_size_speed_and_eta(tmp_path):
    panel, manager, _settings = make_panel(tmp_path)
    loaded(panel)
    manager.item_state.emit("rewrite-v4-q4", "downloading")
    total = 1312164288
    manager.progress.emit("rewrite-v4-q4", total // 2, total, 10 * 2**20)
    row = panel.rows["rewrite-v4-q4"]
    assert row.progress.value() == 50
    assert row.status_label.text() == "50% · 626 MB / 1.2 GB · 10.0 MB/s · about 1 min left"
    manager.item_state.emit("llama-vulkan", "queued")
    assert panel.rows["llama-vulkan"].status_label.text() == "Queued"


def test_installed_and_failed_states(tmp_path):
    panel, manager, _settings = make_panel(tmp_path)
    loaded(panel)
    seen = []
    panel.installed.connect(seen.append)
    manager.item_state.emit("rewrite-v4-q8", "installed")
    assert seen == ["rewrite-v4-q8"]
    assert not panel.rows["rewrite-v4-q8"].checkbox.isEnabled()
    manager.item_failed.emit("asr-sensevoice", "download.error.hash")
    manager.item_state.emit("asr-sensevoice", "failed")
    assert panel.rows["asr-sensevoice"].status_label.text() == i18n.tr("download.error.hash")
    assert panel.rows["asr-sensevoice"].checkbox.isEnabled()  # can retry


def test_offline_list_shows_notice(tmp_path):
    panel, _manager, _settings = make_panel(tmp_path, online=False)
    loaded(panel)
    assert not panel.notice.isHidden()
    assert panel.notice.text() == "Could not connect · showing the built-in list"


def test_preselect_checks_items_without_starting(tmp_path):
    panel, manager, _settings = make_panel(tmp_path, compact=True)
    loaded(panel)
    panel.preselect(["asr-sensevoice", "llama-vulkan", "rewrite-v4-q8"])
    assert panel.selected_ids() == ["asr-sensevoice", "llama-vulkan", "rewrite-v4-q8"]
    assert manager.started == []


def test_reloading_the_list_keeps_running_downloads(tmp_path):
    panel, manager, _settings = make_panel(tmp_path)
    manager.current_states = {"rewrite-v4-q8": "downloading", "rewrite-v4-q4": "queued"}
    loaded(panel)
    row = panel.rows["rewrite-v4-q8"]
    assert not row.checkbox.isEnabled()
    assert not row.cancel_button.isHidden()
    assert not panel.cancel_all_button.isHidden()
    assert panel.rows["rewrite-v4-q4"].status_label.text() == "Queued"
