import subprocess
import sys
import time

import pytest

PARENT = r"""
import subprocess, sys, time
from voxflow.process_guard import end_children_with_this_process
end_children_with_this_process()
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
print(child.pid, flush=True)
time.sleep(60)
"""


def alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job objects")
def test_children_end_when_the_app_is_killed():
    parent = subprocess.Popen([sys.executable, "-c", PARENT], stdout=subprocess.PIPE, text=True)
    child_pid = int(parent.stdout.readline())
    assert alive(child_pid)
    parent.kill()  # like a crash or Task Manager "End task"
    parent.wait()
    deadline = time.monotonic() + 5
    while alive(child_pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not alive(child_pid)
