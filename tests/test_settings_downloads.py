import json

import pytest
from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from voxflow import settings_window as settings_module
from voxflow import smart_editing, window as window_module
from voxflow.downloads import DownloadManager
from voxflow.rewriter import RewriteConfig
from voxflow.window import VoxFlowWindow

Q8 = "runtime/models/voxflow-rewrite-v4-q8_0.gguf"
Q4 = "runtime/models/voxflow-rewrite-v4-q4_k_m.gguf"


class Output:
    def remember_foreground(self, _hwnd):
        pass

    def paste(self, _text):
        return True


class FakeServer:
    problem = None
    failed = None

    def start(self):
        pass

    def ready(self):
        return False

    def stop(self):
        pass


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    for module in (settings_module, smart_editing, window_module):
        monkeypatch.setattr(module, "DATA_ROOT", tmp_path)
    return tmp_path


def make_window(root, start_worker=False, model_dir=None, rewrite=None):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(root / "voxflow.ini"), QSettings.Format.IniFormat)
    if rewrite is not None:
        rewrite.save(settings)
    window = VoxFlowWindow(model_dir=model_dir or root / "models" / "none", start_worker=start_worker,
                           settings=settings, text_output=Output(), downloads=DownloadManager(root),
                           local_server_factory=lambda _config: FakeServer())
    return window, settings


def install_models(root, *paths):
    record = {}
    for path, item_id in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"gguf")
        record[item_id] = {"group": "", "sha256": ["x"]}
    (root / "installed.json").write_text(json.dumps(record), encoding="utf-8")


def test_missing_speech_model_points_to_downloads(data_root):
    window, _settings = make_window(data_root, start_worker=True)
    assert window._status[0] == "status.asr_needed"
    window.reveal()
    QTest.mouseClick(window.status_label, Qt.MouseButton.LeftButton)
    assert window.settings_window.isVisible()
    assert window.settings_window.categories.currentRow() == 2  # smart editing page, where the downloads are
    window.close()


def test_speech_worker_starts_after_model_installed(data_root):
    window, _settings = make_window(data_root)
    started = []
    window.start_speech_worker = lambda: started.append(True)
    window.downloads.item_state.emit("asr-sensevoice", "installed")
    window.downloads.item_state.emit("asr-sensevoice", "downloading")
    assert started == [True]
    window.close()


def test_installing_a_model_selects_it_when_none_is_usable(data_root):
    window, settings = make_window(data_root, rewrite=RewriteConfig(enabled=True, provider="local", model_path=Q8))
    install_models(data_root, (Q4, "rewrite-v4-q4"))
    window.downloads.item_state.emit("rewrite-v4-q4", "installed")
    assert RewriteConfig.from_settings(settings).model_path == Q4
    window.close()


def test_deleting_model_in_use_switches_or_disables(data_root):
    install_models(data_root, (Q8, "rewrite-v4-q8"), (Q4, "rewrite-v4-q4"))
    window, settings = make_window(data_root, rewrite=RewriteConfig(enabled=True, provider="local", model_path=Q8))
    settings_window = window.settings_window
    assert settings_window.rewrite_delete_button.isEnabled()
    settings_window.rewrite_delete_button.click()
    assert not (data_root / Q8).exists()
    assert RewriteConfig.from_settings(settings).model_path == Q4
    settings_window.rewrite_delete_button.click()
    assert not (data_root / Q4).exists()
    assert window.smart.model_status()[0] == "model.not_installed"
    assert not settings_window.rewrite_delete_button.isEnabled()
    window.close()


def test_only_downloaded_models_can_be_deleted(data_root):
    own = data_root / "my-model.gguf"
    own.write_bytes(b"gguf")
    window, _settings = make_window(data_root, rewrite=RewriteConfig(enabled=True, provider="local",
                                                                    model_path=str(own)))
    assert not window.settings_window.rewrite_delete_button.isEnabled()
    window.close()


def test_missing_model_status_offers_downloads(data_root):
    window, _settings = make_window(data_root, rewrite=RewriteConfig(enabled=True, provider="local", model_path=Q8))
    settings_window = window.settings_window
    key, values = window.smart.model_status()
    settings_window.set_model_status(key, **values)
    assert not settings_window.rewrite_download_button.isHidden()
    settings_window.rewrite_download_button.click()
    assert settings_window.categories.currentRow() == 2
    window.close()


def test_settings_page_shows_the_download_panel(data_root):
    window, _settings = make_window(data_root)
    assert window.settings_window.download_panel is not None
    assert window.settings_window.download_panel.manager is window.downloads
    window.close()


def test_about_restart_tutorial_emits_signal(data_root):
    window, _settings = make_window(data_root)
    seen = []
    window.settings_window.tutorial_requested.connect(lambda: seen.append(True))
    window.settings_window.restart_tutorial_button.click()
    assert seen == [True]
    window.close()


class CountingServerFactory:
    """Starts fake servers and remembers which model each running one holds open."""

    def __init__(self):
        self.started = 0
        self.running = []

    def __call__(self, config):
        factory = self

        class Server(FakeServer):
            def start(self):
                factory.started += 1
                factory.running.append(config.model_path)

            def stop(self):
                if config.model_path in factory.running:
                    factory.running.remove(config.model_path)

        return Server()


def make_counting_window(root, rewrite):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(root / "voxflow.ini"), QSettings.Format.IniFormat)
    rewrite.save(settings)
    factory = CountingServerFactory()
    window = VoxFlowWindow(model_dir=root / "models" / "none", start_worker=False, settings=settings,
                           text_output=Output(), downloads=DownloadManager(root), local_server_factory=factory)
    return window, settings, factory


def test_deleting_model_in_use_stops_its_server_first(data_root, monkeypatch):
    install_models(data_root, (Q8, "rewrite-v4-q8"), (Q4, "rewrite-v4-q4"))
    window, settings, factory = make_counting_window(
        data_root, RewriteConfig(enabled=True, provider="local", model_path=Q8))
    window.smart.reload()
    assert Q8 in factory.running
    held = []
    original = window.downloads.remove_installed

    def remove_installed(item_id):
        held.append(list(factory.running))
        original(item_id)

    monkeypatch.setattr(window.downloads, "remove_installed", remove_installed)
    window.settings_window.rewrite_delete_button.click()
    assert held and Q8 not in held[0]  # llama-server had let go of the file before it was deleted
    assert RewriteConfig.from_settings(settings).model_path == Q4
    window.close()


def test_delete_failure_is_reported(data_root, monkeypatch):
    install_models(data_root, (Q8, "rewrite-v4-q8"))
    window, _settings = make_window(data_root, rewrite=RewriteConfig(enabled=True, provider="local", model_path=Q8))

    def locked(_item_id):
        raise PermissionError(32, "The process cannot access the file because it is being used")

    monkeypatch.setattr(window.downloads, "remove_installed", locked)
    window.settings_window.rewrite_delete_button.click()
    status = window.settings_window.rewrite_status
    assert not status.isHidden() and status.text().startswith("Could not delete the model")
    window.close()


def test_installing_llama_restarts_the_local_server(data_root):
    install_models(data_root, (Q8, "rewrite-v4-q8"))
    window, _settings, factory = make_counting_window(
        data_root, RewriteConfig(enabled=True, provider="local", model_path=Q8))
    window.smart.reload()
    before = factory.started
    window.downloads.item_state.emit("llama-vulkan", "installed")
    assert factory.started == before + 1
    window.close()


def test_runtime_install_stops_the_server_and_answers(data_root):
    install_models(data_root, (Q8, "rewrite-v4-q8"))
    window, _settings, factory = make_counting_window(
        data_root, RewriteConfig(enabled=True, provider="local", model_path=Q8))
    window.smart.reload()
    assert factory.running
    window.downloads.release_runtime.emit()
    assert factory.running == [] and window.smart.server is None
    assert window.downloads._released.is_set()
    window.close()


def test_online_only_model_can_be_deleted_and_is_selected_after_install(data_root):
    v5 = "runtime/models/voxflow-rewrite-v5-q8_0.gguf"
    target = data_root / v5
    target.parent.mkdir(parents=True)
    target.write_bytes(b"gguf")
    (data_root / "installed.json").write_text(json.dumps(
        {"rewrite-v5-q8": {"group": "", "kind": "rewrite", "sha256": ["x"], "dest": [v5]}}), encoding="utf-8")
    window, settings = make_window(data_root, rewrite=RewriteConfig(enabled=True, provider="local", model_path=Q8))
    window.downloads.item_state.emit("rewrite-v5-q8", "installed")
    assert RewriteConfig.from_settings(settings).model_path == v5
    assert window.settings_window.rewrite_delete_button.isEnabled()
    window.settings_window.rewrite_delete_button.click()
    assert not target.exists()
    window.close()


def test_show_downloads_loads_the_list(data_root, monkeypatch):
    from voxflow import download_panel as panel_module
    from voxflow.catalog import builtin_catalog

    monkeypatch.setattr(panel_module, "fetch_catalog", lambda source: (builtin_catalog(), True))
    window, _settings = make_window(data_root)
    window.settings_window.show_downloads()
    panel = window.settings_window.download_panel
    import time
    deadline = time.monotonic() + 3
    while not panel.rows and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert panel.rows
    window.close()
