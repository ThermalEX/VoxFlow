import os

from PySide6.QtWidgets import QApplication

from voxflow.input_target import WindowsPasteTarget


class FakeUser32:
    def __init__(self):
        self.foreground = 101
        self.activated = []
        self.sent = 0
        self.activation_allowed = True

    def GetForegroundWindow(self):
        return self.foreground

    def IsWindow(self, hwnd):
        return hwnd in (42, 101, 102)

    def GetWindowThreadProcessId(self, hwnd, pid_pointer):
        pid_pointer._obj.value = os.getpid() if hwnd == 42 else 12345
        return 1

    def GetClassNameW(self, hwnd, buffer, size):
        name = "Shell_TrayWnd" if hwnd == 102 else "TextApp"
        buffer.value = name[:size - 1]
        return len(buffer.value)

    def SetForegroundWindow(self, hwnd):
        self.activated.append(hwnd)
        if self.activation_allowed:
            self.foreground = hwnd
        return self.activation_allowed

    def SendInput(self, count, _inputs, _size):
        self.sent += count
        return count


def test_paste_returns_to_last_external_window_without_losing_target(preserve_clipboard):
    app = QApplication.instance() or QApplication([])
    user32 = FakeUser32()
    output = WindowsPasteTarget(user32=user32)
    output.remember_foreground(42)
    user32.foreground = 42
    output.remember_foreground(42)
    user32.foreground = 102
    output.remember_foreground(42)
    assert output.paste("你好, world")
    assert user32.activated == [101]
    assert user32.sent == 4
    assert app.clipboard().text() == "你好, world"


def test_paste_does_not_send_to_an_unavailable_target():
    QApplication.instance() or QApplication([])
    user32 = FakeUser32()
    output = WindowsPasteTarget(user32=user32)
    output.remember_foreground(42)
    user32.activation_allowed = False
    assert not output.paste("text")
    assert user32.sent == 0
