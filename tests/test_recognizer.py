from pathlib import Path

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


@pytest.mark.skipif(not (MODEL_DIR / "model.int8.onnx").exists(), reason="model not downloaded")
@pytest.mark.parametrize("language", ["zh", "en"])
def test_official_sample_audio_produces_text(language):
    audio, sample_rate = sf.read(MODEL_DIR / "test_wavs" / f"{language}.wav", dtype="float32")
    result = SenseVoiceRecognizer(MODEL_DIR).recognize(audio, sample_rate)
    assert isinstance(result, str)
    assert len(result.strip()) >= 5
    if language == "zh":
        assert result.endswith("。")
