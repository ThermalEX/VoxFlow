from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from voxflow.recognizer import SenseVoiceRecognizer


MODEL_DIR = (
    Path(__file__).parents[1]
    / "models"
    / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
)


def test_missing_model_is_reported_before_loading(tmp_path):
    with pytest.raises(FileNotFoundError, match="model.int8.onnx"):
        SenseVoiceRecognizer(tmp_path)


def test_punctuation_only_decode_is_treated_as_no_speech():
    class FakeStream:
        result = type("Result", (), {"text": "."})()

        def accept_waveform(self, _sample_rate, _audio):
            pass

    class FakeRecognizer:
        def create_stream(self):
            return FakeStream()

        def decode_stream(self, _stream):
            pass

    recognizer = SenseVoiceRecognizer.__new__(SenseVoiceRecognizer)
    recognizer._recognizer = FakeRecognizer()
    assert recognizer.recognize([0.1] * 16000, 16000) == ""


def test_very_quiet_audio_skips_decoder():
    recognizer = SenseVoiceRecognizer.__new__(SenseVoiceRecognizer)
    recognizer._recognizer = None
    assert recognizer.recognize([0.002] * 16000, 16000) == ""


def test_long_recording_reuses_completed_audio_segments():
    class CountingRecognizer(SenseVoiceRecognizer):
        def __init__(self):
            self.decoded: list[int] = []

        def _decode_segment(self, samples, sample_rate):
            self.decoded.append(len(samples))
            return f"segment{len(self.decoded)}"

    recognizer = CountingRecognizer()
    sample_rate = 100
    first = recognizer.recognize_incremental(np.ones(25 * sample_rate), sample_rate, session_token=1)
    committed = recognizer._cached_until
    assert committed >= 18 * sample_rate
    assert len(recognizer._cached_texts) == 1
    assert first.startswith("segment1")
    before = len(recognizer.decoded)
    second = recognizer.recognize_incremental(np.ones(27 * sample_rate), sample_rate, session_token=1)
    assert len(recognizer.decoded) == before + 1
    assert recognizer._cached_until == committed
    assert second.startswith("segment1")
    recognizer.recognize_incremental(np.ones(27 * sample_rate), sample_rate, session_token=1, final=True)
    assert recognizer._cached_texts == []
    recognizer.recognize_incremental(np.ones(4 * sample_rate), sample_rate, session_token=2)
    assert recognizer._cached_until == 0
    assert recognizer._cached_texts == []


@pytest.mark.skipif(not (MODEL_DIR / "model.int8.onnx").exists(), reason="model not downloaded")
@pytest.mark.parametrize("language", ["zh", "en"])
def test_official_sample_audio_produces_text(language):
    audio, sample_rate = sf.read(MODEL_DIR / "test_wavs" / f"{language}.wav", dtype="float32")
    result = SenseVoiceRecognizer(MODEL_DIR).recognize(audio, sample_rate)
    assert isinstance(result, str)
    assert len(result.strip()) >= 5
    if language == "zh":
        assert result.endswith("。")
