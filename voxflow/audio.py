"""Thread-safe recording buffer for mono microphone samples."""

from threading import Lock

import numpy as np


class AudioBuffer:
    def __init__(self, max_seconds: float = 30.0) -> None:
        if max_seconds <= 0:
            raise ValueError("max_seconds must be positive")
        self.max_seconds = max_seconds
        self._lock = Lock()
        self._chunks: list[np.ndarray] = []
        self._sample_count = 0
        self._sample_rate = 0
        self._recording = False
        self._recent_level = 0.0

    def start(self, sample_rate: int) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        with self._lock:
            self._chunks = []
            self._sample_count = 0
            self._sample_rate = sample_rate
            self._recording = True
            self._recent_level = 0.0

    def append(self, frames: np.ndarray) -> bool:
        data = np.asarray(frames, dtype=np.float32)
        if data.ndim == 2 and data.shape[1] == 1:
            data = data[:, 0]
        if data.ndim != 1:
            raise ValueError("expected mono audio")
        with self._lock:
            if not self._recording:
                raise RuntimeError("recording has not started")
            remaining = max(0, int(self.max_seconds * self._sample_rate) - self._sample_count)
            accepted = np.array(data[:remaining], dtype=np.float32, copy=True)
            if accepted.size:
                self._chunks.append(accepted)
                self._sample_count += accepted.size
                self._recent_level = float(np.sqrt(np.mean(np.square(accepted))))
            return self._sample_count >= int(self.max_seconds * self._sample_rate)

    def snapshot(self) -> np.ndarray:
        with self._lock:
            if not self._chunks:
                return np.empty(0, dtype=np.float32)
            return np.concatenate(self._chunks)

    def stop(self) -> np.ndarray:
        with self._lock:
            self._recording = False
        return self.snapshot()

    @property
    def sample_count(self) -> int:
        with self._lock:
            return self._sample_count

    @property
    def sample_rate(self) -> int:
        with self._lock:
            return self._sample_rate

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return self._sample_count / self._sample_rate if self._sample_rate else 0.0

    @property
    def recent_level(self) -> float:
        with self._lock:
            return self._recent_level
