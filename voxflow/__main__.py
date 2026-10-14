"""Launch the desktop app or transcribe an audio file from the command line."""

import argparse
import ctypes
import multiprocessing
import sys
from pathlib import Path

import soundfile as sf
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .i18n import tr
from .paths import APP_ROOT
from .process_guard import end_children_with_this_process
from .recognizer import SenseVoiceRecognizer
from .ui_icons import app_icon
from .window import VoxFlowWindow


MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
DEFAULT_MODEL_DIR = APP_ROOT / "models" / MODEL_NAME


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
        end_children_with_this_process()  # the speech worker and llama-server never outlive the app
    app = QApplication([])
    app.setApplicationName("VoxFlow")
    icon = app_icon()
    app.setWindowIcon(icon)
    app.setQuitOnLastWindowClosed(False)
    window = VoxFlowWindow(args.model_dir)
    tray = QSystemTrayIcon(icon)
    menu = QMenu()
    actions = {
        "tray.show": menu.addAction("", window.reveal),
        "tray.start": menu.addAction("", window.toggle_recording),
        "tray.settings": menu.addAction("", window.open_settings),
    }
    menu.addSeparator()
    def quit_app() -> None:
        window.close()
        tray.hide()
        app.quit()

    actions["tray.quit"] = menu.addAction("", quit_app)

    def retranslate_tray() -> None:
        tray.setToolTip(tr("tray.tooltip", hotkey=window.hotkeys["record"].text))
        for key, action in actions.items():
            action.setText(tr(key))

    retranslate_tray()
    window.settings_window.language_changed.connect(lambda _choice: retranslate_tray())
    window.hotkeys_changed.connect(retranslate_tray)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.reveal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
        if not window.register_hotkey():
            window.show_shortcut_problem()
            taken = " / ".join(window.hotkeys[action].text for action in window.hotkey_failures)
            tray.showMessage(tr("tray.shortcut_title"), tr("tray.shortcut_body", hotkey=taken))
    else:
        app.setQuitOnLastWindowClosed(True)
        window.reveal()
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # the packaged app re-launches itself for the speech worker
    raise SystemExit(main())
