from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest
import soundfile as sf

from voxflow.recognizer import initialize_worker, transcribe_in_worker, worker_ready


MODEL_DIR = (
    Path(__file__).parents[1]
    / "models"
    / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
)


@pytest.mark.skipif(not (MODEL_DIR / "model.int8.onnx").exists(), reason="model not downloaded")
def test_background_process_transcribes_without_ui_thread():
    audio, sample_rate = sf.read(MODEL_DIR / "test_wavs" / "en.wav", dtype="float32")
    with ProcessPoolExecutor(
        max_workers=1,
        initializer=initialize_worker,
        initargs=(str(MODEL_DIR),),
    ) as executor:
        assert executor.submit(worker_ready).result(timeout=20)
        result = executor.submit(transcribe_in_worker, audio, sample_rate).result(timeout=20)
    assert "chieftain" in result.lower()
