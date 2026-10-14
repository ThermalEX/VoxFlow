"""Start and stop the native llama.cpp server that backs the "VoxFlow local model" option."""

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .process_guard import kill_on_close_job

HEALTH_INTERVAL = 2.0
DEFAULT_PORT = 8765
MODEL_ALIAS = "voxflow-rewrite"


def attach_to_job(process) -> None:
    """Put the server in a Windows job that closes with VoxFlow, so a crash never leaves it running."""
    job = kill_on_close_job(int(process._handle))
    if job:
        process._voxflow_job = job  # keep the handle open for the life of VoxFlow


class LocalRewriteServer:
    def __init__(self, command: list[str], health_url: str, log_path: Path,
                 popen=subprocess.Popen, opener=urllib.request.urlopen, clock=time.monotonic,
                 attach=attach_to_job, required: list[tuple[str, Path]] = ()) -> None:
        self.command = command
        self.health_url = health_url
        self.log_path = Path(log_path)
        self._popen = popen
        self._open = opener
        self._clock = clock
        self._attach = attach
        self._required = list(required)
        self.process = None
        self._log = None
        self._ready = False
        self._next_check = 0.0
        self._start_error: str | None = None
        self._problem: tuple[str, str] | None = None

    @staticmethod
    def llama_command(server_path: Path, model_path: Path, port: int = DEFAULT_PORT) -> list[str]:
        return [
            str(server_path), "-m", str(model_path),
            "--host", "127.0.0.1", "--port", str(port), "--alias", MODEL_ALIAS,
            "--n-gpu-layers", "99", "--ctx-size", "4096", "--parallel", "1",
            "--jinja", "--chat-template-kwargs", '{"enable_thinking":false}',
        ]

    def start(self) -> None:
        if self.process is not None or self._start_error:
            return
        for kind, path in self._required:
            if not Path(path).is_file():
                self._problem = (kind, str(path))
                self._start_error = f"Required file not found: {path}"
                return
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(self.log_path, "w", encoding="utf-8")
            self.process = self._popen(self.command, stdin=subprocess.DEVNULL, stdout=self._log,
                                       stderr=subprocess.STDOUT, creationflags=flags)
        except OSError as exc:  # missing binary or unwritable log: report, never crash the app
            self._start_error = f"Could not start the local model ({exc})"
            self._problem = ("launch", str(exc))
            if self._log is not None:
                self._log.close()
                self._log = None
            return
        try:
            self._attach(self.process)
        except OSError:
            pass  # the server still works; it just is not tied to VoxFlow's lifetime
        self._ready = False
        self._next_check = 0.0

    @property
    def problem(self) -> tuple[str, str] | None:
        """Why the server is unavailable, as (kind, detail): missing_server, missing_model, launch or exited."""
        if self._problem is not None:
            return self._problem
        if self.process is not None and self.process.poll() is not None:
            return ("exited", str(self.process.returncode))
        return None

    @property
    def failed(self) -> str | None:
        if self._start_error:
            return self._start_error
        if self.process is None or self.process.poll() is None:
            return None
        return f"Local model server exited (code {self.process.returncode}). See {self.log_path}"

    def ready(self) -> bool:
        if self.process is None or self.failed:
            return False
        if self._ready:
            return True
        now = self._clock()
        if now < self._next_check:
            return False
        self._next_check = now + HEALTH_INTERVAL
        try:
            with self._open(self.health_url, timeout=0.5) as response:
                self._ready = response.status == 200
        except OSError:
            self._ready = False
        return self._ready

    def stop(self) -> None:
        process, self.process = self.process, None
        self._ready = False
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        if self._log is not None:
            self._log.close()
            self._log = None
