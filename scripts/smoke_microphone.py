"""Manual two-second microphone and GUI integration check; saves no audio."""

import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from voxflow.window import VoxFlowWindow


MODEL_DIR = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
)


def main() -> int:
    app = QApplication([])
    window = VoxFlowWindow(MODEL_DIR)
    window.reveal()
    started_at: float | None = None
    stopped = False
    deadline = time.monotonic() + 25

    def check() -> None:
        nonlocal started_at, stopped
        if time.monotonic() >= deadline:
            print(f"TIMEOUT: {window.status_label.text()}")
            window.close()
            app.exit(1)
        elif started_at is None and window.model_ready:
            print("MODEL_READY")
            window.toggle_recording()
            if window.stream is None:
                print(f"MICROPHONE_ERROR: {window.status_label.text()}")
                window.close()
                app.exit(1)
            else:
                started_at = time.monotonic()
        elif started_at is not None and not stopped and time.monotonic() - started_at >= 2:
            window.toggle_recording()
            stopped = True
            print(f"CAPTURED_SECONDS: {window.audio.duration_seconds:.2f}")
            samples = window.audio.snapshot()
            print(f"CAPTURED_RMS: {float(np.sqrt(np.mean(np.square(samples)))):.5f}")
        elif stopped and window.scheduler and window.scheduler.state == "done":
            print(f"FINAL_TEXT: {window.transcript.toPlainText()!r}")
            window.close()
            app.exit(0)

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(check)
    timer.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
