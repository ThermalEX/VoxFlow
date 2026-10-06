import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from voxflow.overlay_widgets import GlowCapsule


def test_capsule_light_moves_with_audio_level():
    app = QApplication.instance() or QApplication([])
    capsule = GlowCapsule()
    capsule.show()
    app.processEvents()
    quiet = capsule.grab().toImage()
    assert quiet.pixelColor(116, 18).lightness() < 70
    lower = quiet.pixelColor(116, 62)
    assert lower.blue() > 170
    assert lower.blue() > lower.red() + 40
    for _ in range(60):
        capsule.tick(1 / 60)
    app.processEvents()
    breathing = capsule.grab().toImage()
    samples = [(x, y) for x in range(40, 200, 10) for y in range(40, 67, 2)]
    assert any(abs(quiet.pixelColor(x, y).blue() - breathing.pixelColor(x, y).blue()) > 4 for x, y in samples)
    for _ in range(5):
        capsule.set_level(0.12)
        capsule.tick(1 / 60)
    app.processEvents()
    speaking = capsule.grab().toImage()
    assert any(abs(breathing.pixelColor(x, y).red() - speaking.pixelColor(x, y).red()) > 16 for x, y in samples)
    capsule.close()


def test_idle_wave_is_subtle_and_has_no_traveling_white_spot():
    app = QApplication.instance() or QApplication([])
    capsule = GlowCapsule()
    capsule.show()
    app.processEvents()
    first = capsule.grab().toImage()
    for _ in range(36):
        capsule.tick(1 / 60)
    app.processEvents()
    second = capsule.grab().toImage()
    changes = [max(abs(first.pixelColor(x, y).red() - second.pixelColor(x, y).red()),
                   abs(first.pixelColor(x, y).green() - second.pixelColor(x, y).green()),
                   abs(first.pixelColor(x, y).blue() - second.pixelColor(x, y).blue()))
               for x in range(20, 213, 4) for y in range(30, 69, 3)]
    assert 4 < max(changes) < 35
    def brightness_center(image):
        weights = [max(0, image.pixelColor(x, 48).green() - 38) for x in range(20, 212)]
        return sum(x * weight for x, weight in zip(range(20, 212), weights)) / sum(weights)
    assert abs(brightness_center(first) - brightness_center(second)) < 25
    capsule.close()


def test_recording_capsule_is_brighter_than_idle():
    app = QApplication.instance() or QApplication([])
    capsule = GlowCapsule()
    capsule.show()
    app.processEvents()
    idle = capsule.grab().toImage().pixelColor(116, 60)
    capsule.set_recording(True)
    app.processEvents()
    active = capsule.grab().toImage().pixelColor(116, 60)
    assert active.red() > idle.red() + 20
    assert active.green() > idle.green() + 20
    capsule.close()


def test_recording_wave_responds_to_sound_then_settles():
    app = QApplication.instance() or QApplication([])
    capsule = GlowCapsule()
    capsule.set_recording(True)
    capsule.show()
    app.processEvents()
    silent = capsule.grab().toImage()
    for _ in range(20):
        capsule.set_level(0.12)
        capsule.tick(1 / 60)
    app.processEvents()
    speaking = capsule.grab().toImage()
    samples = [(x, y) for x in range(40, 200, 10) for y in range(42, 67, 2)]
    assert any(abs(silent.pixelColor(x, y).red() - speaking.pixelColor(x, y).red()) > 10 for x, y in samples)
    for _ in range(45):
        capsule.set_level(0)
        capsule.tick(1 / 60)
    assert capsule.level < 0.01
    capsule.close()


def test_quiet_microphone_speech_has_visible_activity():
    app = QApplication.instance() or QApplication([])
    capsule = GlowCapsule()
    capsule.set_recording(True)
    capsule.set_level(0.00022)
    for _ in range(20):
        capsule.tick(1 / 60)
    assert capsule.level < 0.08
    capsule.show()
    capsule.phase = 1.25
    app.processEvents()
    quiet = capsule.grab().toImage()
    capsule.set_level(0.003)
    for _ in range(12):
        capsule.tick(1 / 60)
    assert capsule.level > 0.5
    capsule.phase = 1.25
    app.processEvents()
    speaking = capsule.grab().toImage()
    assert max(abs(speaking.pixelColor(x, y).blue() - quiet.pixelColor(x, y).blue())
               for x in range(35, 198, 4) for y in range(30, 47, 2)) > 35
    assert max(abs(speaking.pixelColor(x, y).blue() - quiet.pixelColor(x, y).blue())
               for x in range(35, 198, 4) for y in range(20, 32, 2)) > 25
    assert max(abs(speaking.pixelColor(x, y).blue() - quiet.pixelColor(x, y).blue())
               for x in range(35, 198, 4) for y in range(10, 20, 2)) > 15
    capsule.set_level(0.00022)
    for _ in range(30):
        capsule.tick(1 / 60)
    assert capsule.level < 0.08
    capsule.close()
    assert app is not None
