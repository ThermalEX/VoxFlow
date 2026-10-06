import os
from types import SimpleNamespace

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt

from voxflow.window import VoxFlowWindow


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
    window.copy_button.click()
    assert app.clipboard().text() == "hello world"
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
    assert ripple.pixelColor(100, 160).alpha() < 5
    window._background_progress = 1
    window.update()
    app.processEvents()
    frame = window.grab().toImage()
    assert frame.pixelColor(window.width() // 2, window.height() // 2).alpha() > 20
    window.close()


def test_second_click_retracts_particles_and_keeps_result(tmp_path):
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
    assert window._background_retracting
    assert window._background_progress < 1.0
    assert window.record_button.icon_name == "mic"
    window._animate_particles()
    assert window._background_progress < 1.0
    for _ in range(80):
        window._animate_particles()
    assert window._background_progress == 0.0
    window.apply_transcript("final", "hello")
    assert window.transcript.toPlainText() == "hello"
    assert window.transcript.isVisible()
    assert not window.mask().contains(QPoint(5, 5))
    assert window.mask().contains(window.transcript.mapTo(window, window.transcript.rect().center()))
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
    assert first.pixelColor(3, window.height() // 2).alpha() < 8
    assert first.pixelColor(window.width() - 4, window.height() // 2).alpha() < 8
    assert any(abs(first.pixelColor(x, y).alpha() - second.pixelColor(x, y).alpha()) > 10 for x, y in points)
    window.close()
    assert app is not None
