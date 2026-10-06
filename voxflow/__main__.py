"""Launch the desktop app or transcribe an audio file from the command line."""

import argparse
from pathlib import Path

import soundfile as sf
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .recognizer import SenseVoiceRecognizer
from .window import VoxFlowWindow


MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / MODEL_NAME


def tray_icon() -> QIcon:
    image = QPixmap(64, 64)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#79AFFF"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(8, 8, 48, 48, 16, 16)
    painter.setBrush(QColor("#0A1D47"))
    painter.drawRoundedRect(28, 17, 8, 20, 4, 4)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QColor("#0A1D47"))
    painter.drawArc(22, 23, 20, 21, 180 * 16, 180 * 16)
    painter.drawLine(32, 45, 32, 48)
    painter.end()
    return QIcon(image)


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

    app = QApplication([])
    app.setApplicationName("VoxFlow")
    app.setQuitOnLastWindowClosed(False)
    window = VoxFlowWindow(args.model_dir)
    icon = tray_icon()
    app.setWindowIcon(icon)
    tray = QSystemTrayIcon(icon)
    tray.setToolTip("VoxFlow · Ctrl+Shift+Space to speak")
    menu = QMenu()
    menu.addAction("Show VoxFlow", window.reveal)
    menu.addAction("Start voice input", window.toggle_recording)
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
