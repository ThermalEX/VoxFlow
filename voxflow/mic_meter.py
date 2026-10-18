"""A live microphone level for the tutorial: computed in memory from each audio block, never recorded or saved."""

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Signal

SAMPLE_RATE = 16000
BLOCK = 800  # 50 ms
GAIN = 6.0  # maps speech RMS (about 0.02-0.15) onto most of the 0-1 meter


class MicMeter(QObject):
    level = Signal(float)  # 0-1, about every 50 ms
    failed = Signal(str)

    def __init__(self, stream_factory=sd.InputStream) -> None:
        super().__init__()
        self._factory = stream_factory
        self._stream = None

    def start(self, device_id) -> None:
        self.stop()
        try:
            self._stream = self._factory(device=device_id, channels=1, samplerate=SAMPLE_RATE, blocksize=BLOCK,
                                         dtype="float32", callback=self._on_audio)
            self._stream.start()
        except Exception as exc:  # no microphone, device busy, permission denied
            self._stream = None
            self.failed.emit(str(exc))

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _on_audio(self, frames, _count, _time, _status) -> None:
        rms = float(np.sqrt(np.mean(np.square(frames)))) if len(frames) else 0.0
        self.level.emit(min(1.0, rms * GAIN))
