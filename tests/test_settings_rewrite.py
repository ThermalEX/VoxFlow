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
    assert window.rewrite_model_path.text().endswith(".gguf")
    window.close()


def test_changes_are_saved_and_announced(tmp_path):
    window, settings = make(tmp_path)
    events = []
    window.rewrite_changed.connect(lambda: events.append("changed"))
    window.rewrite_enabled.setChecked(True)
    window.rewrite_provider.setCurrentIndex(window.rewrite_provider.findData("custom"))
    for field, value in ((window.rewrite_endpoint, "http://host:1234/v1"), (window.rewrite_model, "qwen"),
                         (window.rewrite_api_key, "secret")):
        field.setText(value)
        field.editingFinished.emit()
    config = RewriteConfig.from_settings(settings)
    assert (config.enabled, config.provider, config.endpoint, config.model, config.api_key) == (
        True, "custom", "http://host:1234/v1", "qwen", "secret")
    assert len(events) >= 5
    reopened = SettingsWindow(settings)
    assert reopened.rewrite_enabled.isChecked() and reopened.rewrite_model.text() == "qwen"
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
