"""Local SenseVoice recognition and process-pool entry points."""

from pathlib import Path

import numpy as np


SEGMENT_MIN_SECONDS = 6
SEGMENT_MAX_SECONDS = 10


class SenseVoiceRecognizer:
    def __init__(self, model_dir: str | Path) -> None:
        model_dir = Path(model_dir)
        model = model_dir / "model.int8.onnx"
        tokens = model_dir / "tokens.txt"
        for path in (model, tokens):
            if not path.is_file():
                raise FileNotFoundError(f"Missing ASR model file: {path}")

        import sherpa_onnx

        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model),
            tokens=str(tokens),
            num_threads=4,
            language="auto",
            use_itn=True,
        )
        self._cache_token: int | None = None
        self._cache_rate = 0
        self._cached_until = 0
        self._cached_texts: list[str] = []

    def recognize(self, samples: np.ndarray, sample_rate: int) -> str:
        audio = np.asarray(samples, dtype=np.float32)
        if audio.ndim != 1:
            raise ValueError("expected mono audio")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        return self._decode_segment(audio, sample_rate)

    def recognize_incremental(
        self, samples: np.ndarray, sample_rate: int, session_token: int, final: bool = False
    ) -> str:
        audio = np.asarray(samples, dtype=np.float32)
        if audio.ndim != 1:
            raise ValueError("expected mono audio")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if (getattr(self, "_cache_token", None) != session_token
                or getattr(self, "_cache_rate", 0) != sample_rate
                or audio.size < getattr(self, "_cached_until", 0)):
            self._cache_token = session_token
            self._cache_rate = sample_rate
            self._cached_until = 0
            self._cached_texts = []
        while audio.size - self._cached_until >= SEGMENT_MAX_SECONDS * sample_rate:
            boundary = self._quiet_boundary(audio, self._cached_until, sample_rate)
            self._cached_texts.append(self._decode_segment(audio[self._cached_until:boundary], sample_rate))
            self._cached_until = boundary
        tail = self._decode_segment(audio[self._cached_until:], sample_rate) if audio.size > self._cached_until else ""
        parts = (*self._cached_texts, tail)
        result = ""
        for part in parts:
            if not part:
                continue
            codepoint = ord(part[0])
            cjk_start = (0x4E00 <= codepoint <= 0x9FFF
                         or 0x3040 <= codepoint <= 0x30FF
                         or 0xAC00 <= codepoint <= 0xD7AF)
            if result and not cjk_start:
                result += " "
            result += part
        if final:
            self._cache_token = None
            self._cached_until = 0
            self._cached_texts = []
        return result

    @staticmethod
    def _quiet_boundary(audio: np.ndarray, start: int, sample_rate: int) -> int:
        frame = max(1, int(sample_rate * 0.12))
        lower = start + SEGMENT_MIN_SECONDS * sample_rate
        upper = start + SEGMENT_MAX_SECONDS * sample_rate - frame
        quietest = lower
        lowest_energy = float("inf")
        for offset in range(lower, upper + 1, frame):
            segment = audio[offset:offset + frame]
            energy = float(np.mean(np.square(segment)))
            if energy < lowest_energy:
                lowest_energy = energy
                quietest = offset
        return quietest + frame // 2

    def _decode_segment(self, audio: np.ndarray, sample_rate: int) -> str:
        if audio.size == 0:
            return ""
        # A long pause must not dilute the average below the speech threshold.
        window = max(1, int(sample_rate * 0.25))
        if not any(float(np.mean(np.square(audio[start:start + window]))) >= 0.003 ** 2
                   for start in range(0, audio.size, window)):
            return ""
        stream = self._recognizer.create_stream()
        stream.accept_waveform(sample_rate, audio)
        self._recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        return text if any(character.isalnum() for character in text) else ""


_worker_recognizer: SenseVoiceRecognizer | None = None


def initialize_worker(model_dir: str) -> None:
    global _worker_recognizer
    _worker_recognizer = SenseVoiceRecognizer(model_dir)


def worker_ready() -> bool:
    return _worker_recognizer is not None


def transcribe_in_worker(
    samples: np.ndarray, sample_rate: int, session_token: int | None = None, final: bool = False
) -> str:
    if _worker_recognizer is None:
        raise RuntimeError("ASR worker is not initialized")
    if session_token is None:
        return _worker_recognizer.recognize(samples, sample_rate)
    return _worker_recognizer.recognize_incremental(samples, sample_rate, session_token, final)
