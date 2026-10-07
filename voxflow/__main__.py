"""Launch the desktop app or transcribe an audio file from the command line."""

import argparse
import ctypes
import sys
from pathlib import Path

import soundfile as sf
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .recognizer import SenseVoiceRecognizer
from .ui_icons import app_icon
from .window import VoxFlowWindow


MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / MODEL_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description="VoxFlow local speech recognition")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--file", type=Path, help="Transcribe a WAV/FLAC/OGG file instead of opening the GUI")
    args = parser.parse_args()

    if args.file:
        audio, sample_rate = sf.read(args.file, dtype="float32", always_2d=True)
        samples = audio.mean(axis=1)
        print(SenseVoiceRecognizer(args.model_dir).recognize(samples, sample_rate))
        return 0

    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VoxFlow.Desktop")
    app = QApplication([])
    app.setApplicationName("VoxFlow")
    icon = app_icon()
    app.setWindowIcon(icon)
    app.setQuitOnLastWindowClosed(False)
    window = VoxFlowWindow(args.model_dir)
    tray = QSystemTrayIcon(icon)
    tray.setToolTip("VoxFlow · Ctrl+Shift+Space to speak")
    menu = QMenu()
    menu.addAction("Show VoxFlow", window.reveal)
    menu.addAction("Start voice input", window.toggle_recording)
    menu.addAction("Settings", window.open_settings)
    menu.addSeparator()
    def quit_app() -> None:
        window.close()
        tray.hide()
        app.quit()

    menu.addAction("Quit", quit_app)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.reveal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
        if not window.register_hotkey():
            window.status_label.setText("Shortcut unavailable · click the microphone")
            tray.showMessage("VoxFlow shortcut unavailable", "Ctrl+Shift+Space is in use. Open VoxFlow from the tray.")
    else:
        app.setQuitOnLastWindowClosed(True)
        window.reveal()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
