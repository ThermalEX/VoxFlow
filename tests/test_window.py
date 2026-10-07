import os
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtTest import QTest

from voxflow.window import VoxFlowWindow
import voxflow.window as window_module


@pytest.fixture(autouse=True)
def isolated_window_settings(tmp_path, monkeypatch):
    settings_path = tmp_path / "default-settings.ini"
    monkeypatch.setattr(
        window_module, "QSettings",
        lambda *_args: QSettings(str(settings_path), QSettings.Format.IniFormat),
    )


def test_transcript_stays_provisional_until_final_result(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    assert not window.isVisible()
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    window.reveal()
    assert window.isVisible()
    assert window.particle_timer.isActive()
    assert window.particle_timer.interval() <= 16
    assert window.y() > app.primaryScreen().availableGeometry().center().y()
    assert window.capsule.width() >= 200
    assert not hasattr(window, "waveform")
    assert not window.status_label.isVisible()
    assert abs(window.capsule.mapTo(window, window.capsule.rect().center()).x() - window.width() / 2) < 25
    assert len(window.action_buttons) == 4
    app.processEvents()
    preview = window.grab().toImage()
    assert preview.pixelColor(2, 2).alpha() < 5
    assert preview.pixelColor(window.width() // 2, window.height() // 2).alpha() < 5
    assert not window.mask().contains(QPoint(window.width() // 2, window.height() // 2))
    assert window.mask().contains(window.capsule.mapTo(window, window.capsule.rect().center()))
    assert preview.pixelColor(2, 45).alpha() < 20
    before_geometry = (window.pos(), window.size(), window.capsule.mapToGlobal(window.capsule.rect().center()))
    window.particles.step((1, window.height() / 2))
    window.update()
    app.processEvents()
    edge = window.grab().toImage()
    assert edge.pixelColor(0, window.height() // 2).alpha() < 5
    assert edge.pixelColor(window.width() - 1, window.height() // 2).alpha() < 5
    assert edge.pixelColor(window.width() // 2, 0).alpha() < 5
    assert edge.pixelColor(window.width() // 2, window.height() - 1).alpha() < 5
    window.model_ready = True
    window.capsule.setEnabled(True)
    clicks = []
    window._start_recording = lambda: clicks.append("start")
    window.capsule.click()
    window.record_button.setEnabled(True)
    window.record_button.click()
    assert clicks == ["start", "start"]
    window.apply_transcript("partial", "hello")
    assert (window.pos(), window.size(), window.capsule.mapToGlobal(window.capsule.rect().center())) == before_geometry
    assert window.mask().isEmpty()
    assert window.transcript.toPlainText() == "hello"
    assert window.transcript.isReadOnly()
    assert "Listening" in window.status_label.text()
    window.apply_transcript("final", "hello world")
    assert window.transcript.toPlainText() == "hello world"
    assert not window.transcript.isReadOnly()
    assert window.confirm_button.isEnabled()
    window.hide_overlay()
    assert not window.isVisible()
    assert not window.particle_timer.isActive()
    window.close()
    assert app is not None


def test_recording_reveals_background_from_the_capsule(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    assert window._background_progress == 0
    window._set_mode("recording")
    assert window._background_progress == 0
    window._animate_particles()
    assert window._background_progress > 0
    window._background_progress = 0.4
    window.update()
    app.processEvents()
    ripple = window.grab().toImage()
    assert ripple.pixelColor(100, 80).alpha() < 5
    window._background_progress = 1
    window.update()
    app.processEvents()
    frame = window.grab().toImage()
    assert frame.pixelColor(window.width() // 2, window.height() // 2).alpha() > 20
    window.close()


def test_reveal_mask_expands_from_capsule_shape_not_circle(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    app.processEvents()
    capsule = window.capsule.geometry().adjusted(3, 7, -3, -3)
    mask = window._make_reveal_mask(0.12)
    assert mask.pixelColor(capsule.left() - 20, capsule.center().y()).alpha() > 200
    assert mask.pixelColor(capsule.center().x(), capsule.top() - 50).alpha() < 5
    window.close()


def test_live_text_waits_until_background_has_expanded(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    window.apply_transcript("partial", "hello")
    assert not window.status_label.isVisible()
    assert not window.transcript.isVisible()
    window._background_progress = 0.24
    window._animate_particles()
    assert not window.status_label.isVisible()
    window._background_progress = 0.55
    window._animate_particles()
    assert window.status_label.isVisible()
    assert window.transcript.isVisible()
    window.close()


def test_final_result_expands_and_stays_visible(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    window._set_mode("recording")
    window._background_progress = 1.0
    bottom = window.geometry().bottom()
    window.audio.start(16000)
    window.audio.append(np.full(4800, 0.03, dtype=np.float32))
    window.stream = SimpleNamespace(stop=lambda: None, close=lambda: None)
    window._stop_recording()
    assert not window._background_retracting
    assert window._background_progress == 1.0
    window.apply_transcript("final", "word " * 700)
    assert window.height() == 310
    QTest.qWait(320)
    app.processEvents()
    assert window.height() >= min(650, app.primaryScreen().availableGeometry().height() - 24)
    assert window.geometry().bottom() == bottom
    assert window.transcript.isVisible()
    assert window.transcript.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert window.transcript.verticalScrollBar().maximum() > 0
    assert window.transcript.verticalScrollBar().value() == 0
    assert window.confirm_button.isEnabled()
    window.close()


def test_second_click_keeps_background_open_for_final_result(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    window._set_mode("recording")
    assert window.record_button.icon_name == "stop"
    window._background_progress = 1.0
    window.audio.start(16000)
    window.audio.append(np.full(4800, 0.03, dtype=np.float32))
    window.stream = SimpleNamespace(stop=lambda: None, close=lambda: None)
    window.capsule.setEnabled(True)
    window.capsule.click()
    assert not window._background_retracting
    assert window._background_progress == 1.0
    assert window.record_button.icon_name == "mic"
    window.apply_transcript("final", "hello")
    assert window.transcript.toPlainText() == "hello"
    assert window.transcript.isVisible()
    assert window.status_label.isVisible()
    window.close()
    assert app is not None


def test_animation_interval_tracks_high_refresh_displays():
    assert VoxFlowWindow._frame_interval(0) == 16
    assert VoxFlowWindow._frame_interval(60) == 16
    assert VoxFlowWindow._frame_interval(120) == 8
    assert VoxFlowWindow._frame_interval(180) == 8


def test_record_again_replays_background_reveal(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    window._set_mode("recording")
    window._background_progress = 1.0
    window._background_retracting = True
    window._set_mode("result")
    window._set_mode("recording")
    assert window._background_progress == 0.0
    assert window._background_revealing
    assert not window._background_retracting
    window._animate_particles()
    assert window._background_progress > 0
    window.close()


def test_record_again_interrupts_result_expansion(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    window._set_mode("recording")
    window._background_progress = 1.0
    window.apply_transcript("final", "long result " * 500)
    window._result_animation.setCurrentTime(80)
    assert window.height() > 310
    window._set_mode("recording")
    assert window.height() == 310
    QTest.qWait(300)
    assert window.height() == 310
    window.close()
    assert app is not None


def test_confirm_inserts_edited_result_into_previous_input(tmp_path):
    class FakeOutput:
        def __init__(self):
            self.calls = []
            self.remembered = []

        def remember_foreground(self, own_hwnd):
            self.remembered.append(own_hwnd)

        def paste(self, text):
            self.calls.append(text)
            return True

    app = QApplication.instance() or QApplication([])
    output = FakeOutput()
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, text_output=output)
    window.reveal()
    remembered_on_reveal = len(output.remembered)
    window._poll()
    assert len(output.remembered) == remembered_on_reveal
    window._background_progress = 1.0
    window.apply_transcript("final", "hello")
    window.transcript.setPlainText("edited text")
    window.confirm_button.click()
    assert output.calls == ["edited text"]
    assert not window.isVisible()
    window.close()


def test_failed_confirm_keeps_result_and_copies_for_manual_paste(tmp_path, preserve_clipboard):
    class UnavailableOutput:
        def remember_foreground(self, _own_hwnd):
            pass

        def paste(self, _text):
            return False

    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, text_output=UnavailableOutput())
    window.reveal()
    window.apply_transcript("final", "keep this text")
    window.confirm_button.click()
    assert window.isVisible()
    assert window.transcript.toPlainText() == "keep this text"
    assert app.clipboard().text() == "keep this text"
    assert "manual paste" in window.status_label.text()
    window.close()


def test_standalone_settings_saves_alignment_without_revealing_overlay(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings)
    window.device_button.click()
    assert window.settings_window.isVisible()
    assert not window.isVisible()
    assert window.settings_window.pages.count() == 2
    assert window.settings_window.categories.item(0).text() == "Personalization"
    assert window.settings_window.categories.item(1).text() == "App settings"
    window.settings_window.categories.setCurrentRow(1)
    window.alignment_box.setCurrentIndex(window.alignment_box.findData("right"))
    assert window.transcript_alignment == "right"
    window.close()
    reopened = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings)
    assert reopened.transcript_alignment == "right"
    reopened.open_settings()
    assert not reopened.isVisible()
    assert reopened.settings_window.isVisible()
    reopened.close()
    assert app is not None


def test_settings_window_remembers_microphone(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    devices = [
        {"name": "First mic", "hostapi": 0, "max_input_channels": 1},
        {"name": "Second mic", "hostapi": 0, "max_input_channels": 1},
    ]
    monkeypatch.setattr(window_module.sd, "query_devices", lambda *_args: devices)
    monkeypatch.setattr(window_module.sd, "query_hostapis", lambda _index: {"name": "WASAPI"})
    settings = QSettings(str(tmp_path / "microphone.ini"), QSettings.Format.IniFormat)
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings)
    window.device_box.setCurrentIndex(0)
    window.device_box.setCurrentIndex(1)
    assert settings.value("microphone/name") == "Second mic · WASAPI"
    window.close()
    reopened = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings)
    assert reopened.device_box.currentIndex() == 1
    reopened.close()


def test_personalization_preview_and_persistence(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings)
    window.open_settings()
    app.processEvents()
    assert not window.isVisible()
    assert window.settings_window.isVisible()
    white = window.settings_window.grab().toImage().pixelColor(700, 470)
    assert min(white.red(), white.green(), white.blue()) > 240

    window.settings_window.font_box.setCurrentFont(QFont("Arial"))
    window.settings_window.text_size_box.setValue(32)
    window.settings_window.set_color("background", QColor("#e84759"))
    window.settings_window.set_color("capsule", QColor("#43bf70"))
    assert window.transcript.font().family() == window.settings_window.font_box.currentFont().family()
    assert window.transcript.font().pixelSize() == 32
    assert window.transcript.document().defaultFont().pixelSize() == 32
    assert window.background_color.name() == "#e84759"
    assert window.capsule.accent_color.name() == "#43bf70"
    assert window._make_backdrop().pixelColor(410, 240).red() > window._make_backdrop().pixelColor(410, 240).blue()
    window.capsule.show()
    app.processEvents()
    capsule_color = window.capsule.grab().toImage().pixelColor(116, 62)
    assert capsule_color.green() > capsule_color.blue()
    window.close()

    reopened = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings)
    assert settings.value("appearance/font") == window.settings_window.font_box.currentFont().family()
    assert reopened.transcript.font().family() == window.transcript.font().family()
    assert reopened.transcript.font().pixelSize() == 32
    assert reopened.background_color.name() == "#e84759"
    assert reopened.capsule.accent_color.name() == "#43bf70"
    reopened.close()


def test_live_transcript_is_wide_and_alignment_can_change(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "alignment.ini"), QSettings.Format.IniFormat)
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings)
    window.reveal()
    window.apply_transcript("partial", "The spoken words appear here")
    window._background_progress = 0.55
    window._animate_particles()
    app.processEvents()
    assert window.transcript.width() >= min(640, window.width() - 96)
    assert window.transcript.x() >= 55
    assert window.transcript.geometry().right() <= window.width() - 55
    backdrop = window._make_backdrop()
    line_y = window.transcript.y() + 30
    assert backdrop.pixelColor(window.transcript.x() + 12, line_y).alpha() >= 18
    assert backdrop.pixelColor(window.transcript.geometry().right() - 12, line_y).alpha() >= 18
    assert window.transcript.textCursor().blockFormat().alignment() == Qt.AlignmentFlag.AlignLeft
    window.set_transcript_alignment("center")
    window.apply_transcript("partial", "First line\nSecond line")
    assert window.transcript.textCursor().blockFormat().alignment() == Qt.AlignmentFlag.AlignCenter
    assert window.transcript.document().lastBlock().blockFormat().alignment() == Qt.AlignmentFlag.AlignCenter
    window.close()


def test_particles_fade_out_with_the_blue_background(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    window._background_progress = 1.0
    window.update()
    app.processEvents()
    rendered = window.grab().toImage()
    cloud = window._make_backdrop()
    stray = sum(
        1 for y in range(15, 180, 2) for x in range(30, window.width() - 30, 2)
        if cloud.pixelColor(x, y).alpha() < 10 and rendered.pixelColor(x, y).alpha() > 25
    )
    assert stray < 5
    window.close()


def test_long_live_transcript_scrolls_to_the_latest_words(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.reveal()
    window._set_mode("recording")
    window._background_progress = 1.0
    window.apply_transcript("partial", "earlier words " * 80 + "latest words")
    app.processEvents()
    scrollbar = window.transcript.verticalScrollBar()
    assert scrollbar.maximum() > 0
    assert scrollbar.maximum() - scrollbar.value() <= 5
    window.close()


def test_recording_continues_past_thirty_seconds(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.audio.start(16000)
    window.limit_reached = window.audio.append(np.zeros(45 * 16000, dtype=np.float32))
    window.stream = SimpleNamespace(stop=lambda: None, close=lambda: None)
    window._poll()
    assert window.stream is not None
    assert window.audio.duration_seconds == 45
    assert window.time_label.text() == "00:45 / 05:00"
    window.close()
    assert app is not None


def test_ambient_glow_has_a_moving_organic_contour(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False)
    window.particles.time = 0.0
    first = window._make_backdrop()
    window.particles.time = 2.0
    second = window._make_backdrop()
    points = [(x, y) for x in range(80, window.width() - 80, 40) for y in (55, 85, 115)]
    assert max(first.pixelColor(x, 105).alpha() for x in range(80, window.width() - 80, 40)) - min(
        first.pixelColor(x, 105).alpha() for x in range(80, window.width() - 80, 40)
    ) > 25
    edge_mask = window._make_edge_mask()
    mid_y = window.height() // 2
    assert first.pixelColor(3, mid_y).alpha() * edge_mask.pixelColor(3, mid_y).alpha() // 255 < 8
    right_x = window.width() - 4
    assert first.pixelColor(right_x, mid_y).alpha() * edge_mask.pixelColor(right_x, mid_y).alpha() // 255 < 8
    assert any(abs(first.pixelColor(x, y).alpha() - second.pixelColor(x, y).alpha()) > 10 for x, y in points)
    window.close()
    assert app is not None
