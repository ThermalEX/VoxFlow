import subprocess
import sys
from pathlib import Path

from voxflow.local_server import LocalRewriteServer


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = self.killed = False
        self.hang = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.hang and not self.killed:
            raise subprocess.TimeoutExpired("llama-server.exe", timeout)
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
    popen, clock, checks, attached = FakePopen(), [100.0], [], []

    def opener(url, timeout):
        checks.append(url)
        if not healthy:
            raise OSError("connection refused")
        return Response()

    server = LocalRewriteServer(["llama-server.exe"], "http://127.0.0.1:8765/health", tmp_path / "serve.log",
                                popen=popen, opener=opener, clock=lambda: clock[0],
                                attach=attached.append)
    return server, popen, clock, checks, attached


def test_llama_command_serves_the_model_without_thinking():
    command = LocalRewriteServer.llama_command(Path("F:/runtime/llama.cpp/llama-server.exe"),
                                               Path("F:/models/voxflow-rewrite-q8_0.gguf"), 8765)
    assert command[0] == str(Path("F:/runtime/llama.cpp/llama-server.exe"))
    joined = " ".join(command)
    assert f"-m {Path('F:/models/voxflow-rewrite-q8_0.gguf')}" in joined
    assert "--host 127.0.0.1" in joined and "--port 8765" in joined
    assert "--alias voxflow-rewrite" in joined
    assert '{"enable_thinking":false}' in command


def test_start_launches_once_without_a_window_and_ties_it_to_voxflow(tmp_path):
    server, popen, _clock, _checks, attached = make(tmp_path)
    server.start()
    server.start()
    assert len(popen.calls) == 1
    kwargs = popen.calls[0][1]
    assert kwargs["stdin"] == subprocess.DEVNULL
    if sys.platform == "win32":
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
    assert attached == [popen.process]
    server.stop()


def test_ready_checks_health_at_most_every_two_seconds(tmp_path):
    server, _popen, clock, checks, _attached = make(tmp_path, healthy=False)
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
    server, popen, clock, _checks, _attached = make(tmp_path)
    server.start()
    popen.process.returncode = 1
    clock[0] += 5
    assert not server.ready()
    assert "exited" in server.failed and "serve.log" in server.failed
    server.start()
    assert len(popen.calls) == 1


def test_stop_terminates_and_kills_a_hung_server(tmp_path):
    server, popen, _clock, _checks, _attached = make(tmp_path)
    server.start()
    popen.process.hang = True
    server.stop()
    assert popen.process.terminated and popen.process.killed
    assert not server.ready()


def test_missing_server_binary_is_reported_instead_of_crashing(tmp_path):
    def missing(command, **kwargs):
        raise FileNotFoundError("llama-server.exe not found")

    server = LocalRewriteServer(["llama-server.exe"], "http://127.0.0.1:8765/health", tmp_path / "serve.log",
                                popen=missing)
    server.start()
    assert not server.ready()
    assert "llama-server.exe not found" in server.failed
    server.start()
    server.stop()
