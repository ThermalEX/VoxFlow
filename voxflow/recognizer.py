"""Local SenseVoice recognition and process-pool entry points."""

from pathlib import Path

import numpy as np


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

    def recognize(self, samples: np.ndarray, sample_rate: int) -> str:
        audio = np.asarray(samples, dtype=np.float32)
        if audio.ndim != 1:
            raise ValueError("expected mono audio")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if audio.size == 0:
            return ""
        if float(np.sqrt(np.mean(np.square(audio)))) < 0.003:
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


def transcribe_in_worker(samples: np.ndarray, sample_rate: int) -> str:
    if _worker_recognizer is None:
        raise RuntimeError("ASR worker is not initialized")
    return _worker_recognizer.recognize(samples, sample_rate)
