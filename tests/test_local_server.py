import subprocess
import sys
from pathlib import Path

from voxflow import local_server
from voxflow.local_server import LocalRewriteServer


class FakeStdin:
    closed = False

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStdin()
        self.returncode = None
        self.terminated = self.killed = False
        self.hang = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.hang and not self.terminated:
            raise subprocess.TimeoutExpired("wsl.exe", timeout)
        self.returncode = 0
        return 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class FakePopen:
    def __init__(self):
        self.calls = []
        self.process = FakeProcess()

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return self.process


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def make(tmp_path, healthy=True):
    popen, clock, checks = FakePopen(), [100.0], []

    def opener(url, timeout):
        checks.append(url)
        if not healthy:
            raise OSError("connection refused")
        return Response()

    server = LocalRewriteServer(["wsl.exe"], "http://127.0.0.1:8765/v1/models", tmp_path / "serve.log",
                                popen=popen, opener=opener, clock=lambda: clock[0])
    return server, popen, clock, checks


def test_windows_to_wsl_path():
    assert local_server.windows_to_wsl_path(Path("F:/project/VoxFlow")) == "/mnt/f/project/VoxFlow"


def test_wsl_command_runs_the_server_in_the_training_env():
    command = LocalRewriteServer.wsl_command(Path("F:/project/VoxFlow"), "Ubuntu-26.04", "~/voxflow-train",
                                             "training/rewrite/runs/qwen3.5-2b/adapter", 8765)
    assert command[:5] == ["wsl.exe", "-d", "Ubuntu-26.04", "--", "bash"]
    script = command[-1]
    assert '"$HOME"/voxflow-train/bin/activate' in script
    assert "cd /mnt/f/project/VoxFlow" in script
    assert "--adapter training/rewrite/runs/qwen3.5-2b/adapter" in script and "--port 8765" in script
    default = LocalRewriteServer.wsl_command(Path("F:/project/VoxFlow"), "", "/opt/env", "F:/models/a", 8765)
    assert default[:3] == ["wsl.exe", "--", "bash"]
    assert "--adapter /mnt/f/models/a" in default[-1]


def test_start_launches_once_without_a_window(tmp_path):
    server, popen, _clock, _checks = make(tmp_path)
    server.start()
    server.start()
    assert len(popen.calls) == 1
    kwargs = popen.calls[0][1]
    assert kwargs["stdin"] == subprocess.PIPE
    if sys.platform == "win32":
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
    server.stop()


def test_ready_checks_health_at_most_every_two_seconds(tmp_path):
    server, _popen, clock, checks = make(tmp_path, healthy=False)
    assert not server.ready()
    server.start()
    assert not server.ready() and len(checks) == 1
    assert not server.ready() and len(checks) == 1
    clock[0] += 2.1
    assert not server.ready() and len(checks) == 2
    server._open = lambda url, timeout: Response()
    clock[0] += 2.1
    assert server.ready()
    assert server.ready()
    server.stop()


def test_server_that_exits_is_reported_not_respawned(tmp_path):
    server, popen, clock, _checks = make(tmp_path)
    server.start()
    popen.process.returncode = 1
    clock[0] += 5
    assert not server.ready()
    assert "exited" in server.failed and "serve.log" in server.failed
    server.start()
    assert len(popen.calls) == 1


def test_stop_closes_stdin_then_terminates_a_hung_server(tmp_path):
    server, popen, _clock, _checks = make(tmp_path)
    server.start()
    popen.process.hang = True
    server.stop()
    assert popen.process.stdin.closed and popen.process.terminated
    assert not server.ready()


def test_missing_wsl_is_reported_instead_of_crashing(tmp_path):
    def no_wsl(command, **kwargs):
        raise FileNotFoundError("wsl.exe not found")

    server = LocalRewriteServer(["wsl.exe"], "http://127.0.0.1:8765/v1/models", tmp_path / "serve.log", popen=no_wsl)
    server.start()
    assert not server.ready()
    assert "wsl.exe not found" in server.failed
    server.start()
    server.stop()
