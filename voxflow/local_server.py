"""Start and stop the WSL-hosted rewrite model server that backs the "VoxFlow local model" option."""

import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path, PureWindowsPath

HEALTH_INTERVAL = 2.0
DEFAULT_PORT = 8765


def windows_to_wsl_path(path: Path | str) -> str:
    windows = PureWindowsPath(path)
    if not windows.drive:
        return str(path).replace("\\", "/")
    rest = "/".join(windows.parts[1:])
    return f"/mnt/{windows.drive[0].lower()}/{rest}".rstrip("/")


def _bash_path(path: str) -> str:
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    if PureWindowsPath(path).drive:
        path = windows_to_wsl_path(path)
    return shlex.quote(path)


class LocalRewriteServer:
    def __init__(self, command: list[str], health_url: str, log_path: Path,
                 popen=subprocess.Popen, opener=urllib.request.urlopen, clock=time.monotonic) -> None:
        self.command = command
        self.health_url = health_url
        self.log_path = Path(log_path)
        self._popen = popen
        self._open = opener
        self._clock = clock
        self.process = None
        self._log = None
        self._ready = False
        self._next_check = 0.0
        self._start_error: str | None = None

    @staticmethod
    def wsl_command(repo_root: Path, distro: str, environment: str, adapter: str,
                    port: int = DEFAULT_PORT) -> list[str]:
        script = (f"source {_bash_path(environment.rstrip('/') + '/bin/activate')} && "
                  f"cd {_bash_path(windows_to_wsl_path(repo_root))} && "
                  f"exec python -m training.rewrite.serve --adapter {_bash_path(adapter)} --port {port}")
        prefix = ["wsl.exe", "-d", distro] if distro.strip() else ["wsl.exe"]
        return prefix + ["--", "bash", "-lc", script]

    def start(self) -> None:
        if self.process is not None or self._start_error:
            return
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(self.log_path, "w", encoding="utf-8")
            self.process = self._popen(self.command, stdin=subprocess.PIPE, stdout=self._log,
                                       stderr=subprocess.STDOUT, creationflags=flags)
        except OSError as exc:  # no WSL, broken PATH or unwritable log: report, never crash the app
            self._start_error = f"Could not start the local model ({exc})"
            if self._log is not None:
                self._log.close()
                self._log = None
            return
        self._ready = False
        self._next_check = 0.0

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
        if process is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
        if self._log is not None:
            self._log.close()
            self._log = None
