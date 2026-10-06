"""Orders provisional and final ASR requests across recording sessions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RecognitionJob:
    session_id: int
    kind: str
    sample_count: int


class RecognitionScheduler:
    def __init__(self, sample_rate: int, interval_seconds: float = 1.2) -> None:
        if sample_rate <= 0 or interval_seconds <= 0:
            raise ValueError("sample rate and interval must be positive")
        self.sample_rate = sample_rate
        self.interval_samples = max(1, int(sample_rate * interval_seconds))
        self.session_id = 0
        self.state = "idle"
        self._last_submitted = 0
        self._inflight: RecognitionJob | None = None

    def start(self) -> None:
        self.session_id += 1
        self.state = "recording"
        self._last_submitted = 0
        self._inflight = None

    def stop(self) -> None:
        if self.state != "recording":
            raise RuntimeError("no recording to stop")
        self.state = "finalizing"

    def next_job(self, sample_count: int) -> RecognitionJob | None:
        if self._inflight is not None or sample_count <= 0:
            return None
        if self.state == "recording":
            if sample_count - self._last_submitted < self.interval_samples:
                return None
            kind = "partial"
        elif self.state == "finalizing":
            kind = "final"
        else:
            return None
        self._last_submitted = sample_count
        self._inflight = RecognitionJob(self.session_id, kind, sample_count)
        return self._inflight

    def complete(self, job: RecognitionJob, text: str) -> tuple[str, str] | None:
        if job != self._inflight:
            return None
        self._inflight = None
        if job.session_id != self.session_id:
            return None
        if job.kind == "final":
            self.state = "done"
            return ("final", text)
        if self.state == "recording":
            return ("partial", text)
        return None
