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
