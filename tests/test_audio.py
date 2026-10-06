import numpy as np
import pytest

from voxflow.audio import AudioBuffer


def test_recent_level_tracks_latest_audio():
    audio = AudioBuffer()
    audio.start(16000)
    audio.append(np.ones((1600, 1), dtype=np.float32) * 0.5)
    assert 0.49 <= audio.recent_level <= 0.51
    audio.append(np.zeros((1600, 1), dtype=np.float32))
    assert audio.recent_level == 0.0


def test_audio_buffer_copies_microphone_chunks_and_limits_duration():
    buffer = AudioBuffer(max_seconds=2)
    buffer.start(sample_rate=4)
    first = np.array([[0.1], [0.2], [0.3]], dtype=np.float32)
    assert buffer.append(first) is False
    first[:] = 0
    assert buffer.append(np.ones((7, 1), dtype=np.float32)) is True
    assert buffer.sample_count == 8
    np.testing.assert_allclose(buffer.snapshot()[:3], [0.1, 0.2, 0.3])
    assert buffer.duration_seconds == 2


def test_audio_buffer_restarts_and_rejects_invalid_state():
    buffer = AudioBuffer(max_seconds=2)
    with pytest.raises(RuntimeError):
        buffer.append(np.ones((1, 1), dtype=np.float32))
    buffer.start(sample_rate=16000)
    buffer.append(np.ones((4, 1), dtype=np.float32))
    np.testing.assert_equal(buffer.stop(), np.ones(4, dtype=np.float32))
    with pytest.raises(RuntimeError):
        buffer.append(np.ones((1, 1), dtype=np.float32))
    buffer.start(sample_rate=8000)
    assert buffer.sample_count == 0
    assert buffer.sample_rate == 8000
