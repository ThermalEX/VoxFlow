from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from voxflow.rewriter import RewriteConfig, RewriteError
from voxflow.settings_window import SettingsWindow


def make(tmp_path):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return SettingsWindow(settings), settings


def test_smart_editing_page_exists_with_safe_defaults(tmp_path):
    window, _settings = make(tmp_path)
    assert window.categories.item(2).text() == "Smart editing"
    assert not window.rewrite_enabled.isChecked()
    assert window.rewrite_provider.currentData() == "local"
    assert window.rewrite_server_path.text().endswith("llama-server.exe")
    assert window.rewrite_config().model_path.endswith(".gguf")
    window.close()


def test_changes_are_saved_and_announced(tmp_path):
    window, settings = make(tmp_path)
    events = []
    window.rewrite_changed.connect(lambda: events.append("changed"))
    window.rewrite_enabled.setChecked(True)
    window.rewrite_provider.setCurrentIndex(window.rewrite_provider.findData("custom"))
    for field, value in ((window.rewrite_endpoint, "http://host:1234/v1"), (window.rewrite_model.lineEdit(), "qwen"),
                         (window.rewrite_api_key, "secret")):
        field.setText(value)
        field.editingFinished.emit()
    config = RewriteConfig.from_settings(settings)
    assert (config.enabled, config.provider, config.endpoint, config.model, config.api_key) == (
        True, "custom", "http://host:1234/v1", "qwen", "secret")
    assert len(events) >= 5
    reopened = SettingsWindow(settings)
    assert reopened.rewrite_enabled.isChecked() and reopened.rewrite_model.currentText() == "qwen"
    reopened.close()
    window.close()


def test_provider_switch_shows_matching_fields(tmp_path):
    window, _settings = make(tmp_path)
    assert window.rewrite_endpoint_row.isHidden() and not window.rewrite_model_path_row.isHidden()
    window.rewrite_provider.setCurrentIndex(window.rewrite_provider.findData("custom"))
    assert not window.rewrite_endpoint_row.isHidden() and window.rewrite_model_path_row.isHidden()
    assert window.rewrite_api_key.echoMode() == window.rewrite_api_key.EchoMode.Password
    window.close()


def test_connection_test_uses_the_injected_tester(tmp_path):
    window, _settings = make(tmp_path)
    seen = []
    window.set_rewrite_tester(lambda config: seen.append(config) or "voxflow-rewrite")
    window.rewrite_test_button.click()
    assert window.rewrite_status.text() == "Connected · voxflow-rewrite"
    assert isinstance(seen[0], RewriteConfig)

    def refuse(_config):
        raise RewriteError("connection refused")

    window.set_rewrite_tester(refuse)
    window.rewrite_test_button.click()
    assert "connection refused" in window.rewrite_status.text()
    window.close()


def make_gguf(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * 64)
    return path


def test_local_model_dropdown_lists_found_models_and_browses(tmp_path, monkeypatch):
    from voxflow import settings_window as module

    gguf = tmp_path / "training/rewrite/runs/run/gguf"
    make_gguf(gguf / "voxflow-rewrite-q8_0.gguf")
    make_gguf(gguf / "voxflow-rewrite-q4_k_m.gguf")
    outside = make_gguf(tmp_path / "elsewhere" / "custom.gguf")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    window, settings = make(tmp_path)
    box = window.rewrite_model_path
    labels = [box.itemText(i) for i in range(box.count())]
    assert labels[0].startswith("Q8 ·") and labels[1].startswith("Q4 ·") and labels[-1] == "Browse…"
    box.setCurrentIndex(1)
    assert RewriteConfig.from_settings(settings).model_path == "training/rewrite/runs/run/gguf/voxflow-rewrite-q4_k_m.gguf"
    window.choose_file = lambda *_args: ""
    box.setCurrentIndex(box.count() - 1)
    assert box.currentIndex() == 1
    window.choose_file = lambda *_args: str(outside)
    box.setCurrentIndex(box.count() - 1)
    assert RewriteConfig.from_settings(settings).model_path == "elsewhere/custom.gguf"
    assert box.currentText().startswith("custom ·")
    window.close()


def test_missing_configured_model_is_still_shown(tmp_path, monkeypatch):
    from voxflow import settings_window as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    RewriteConfig(model_path="gone/old.gguf").save(settings)
    window = SettingsWindow(settings)
    assert window.rewrite_model_path.currentText() == "old.gguf (not found)"
    assert window.rewrite_config().model_path == "gone/old.gguf"
    window.close()


def test_refresh_lists_models_from_the_endpoint(tmp_path):
    window, settings = make(tmp_path)
    window.rewrite_provider.setCurrentIndex(window.rewrite_provider.findData("custom"))
    window.set_model_lister(lambda config: ["qwen-a", "qwen-b"])
    refresh = window.rewrite_model_row.control_layout.itemAt(1).widget()
    refresh.click()
    assert [window.rewrite_model.itemText(i) for i in range(2)] == ["qwen-a", "qwen-b"]
    assert window.rewrite_model.currentText() == "qwen-a"
    assert window.rewrite_status.text() == "2 models found"
    assert RewriteConfig.from_settings(settings).model == "qwen-a"

    def refuse(_config):
        raise RewriteError("down", kind="unreachable")

    window.set_model_lister(refuse)
    refresh.click()
    assert window.rewrite_status.text() == "Could not list models · the model server is not reachable"
    window.close()


def test_switch_and_rows_follow_the_theme(tmp_path):
    from voxflow import settings_theme

    window, _settings = make(tmp_path)
    window.apply_theme(settings_theme.DARK)
    assert settings_theme.DARK.window in window.styleSheet()
    assert window.rewrite_enabled.theme is settings_theme.DARK
    window.close()
