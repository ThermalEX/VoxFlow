"""Paste a confirmed transcript into the last foreground Windows application."""

import ctypes
import os
import sys
from ctypes import wintypes

from PySide6.QtWidgets import QApplication


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class InputUnion(ctypes.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]


class WindowsPasteTarget:
    """Remember external focus and paste only if that window can be reactivated."""

    def __init__(self, user32=None) -> None:
        self.user32 = user32
        if self.user32 is None and sys.platform == "win32":
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.user32.GetForegroundWindow.restype = wintypes.HWND
            self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            self.user32.IsWindow.argtypes = [wintypes.HWND]
            self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.target_hwnd: int | None = None

    def remember_foreground(self, own_hwnd: int) -> None:
        if self.user32 is None:
            return
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd or int(hwnd) == own_hwnd or not self.user32.IsWindow(hwnd):
            return
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == os.getpid():
            return
        class_name = ctypes.create_unicode_buffer(128)
        self.user32.GetClassNameW(hwnd, class_name, len(class_name))
        if class_name.value in {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}:
            return
        self.target_hwnd = int(hwnd)

    def paste(self, text: str) -> bool:
        if not text.strip() or self.user32 is None or not self.target_hwnd:
            return False
        hwnd = self.target_hwnd
        if not self.user32.IsWindow(hwnd):
            return False
        if not self.user32.SetForegroundWindow(hwnd):
            return False
        if int(self.user32.GetForegroundWindow() or 0) != hwnd:
            return False
        QApplication.clipboard().setText(text)
        events = (Input * 4)()
        for index, (key, flags) in enumerate(((VK_CONTROL, 0), (VK_V, 0),
                                               (VK_V, KEYEVENTF_KEYUP), (VK_CONTROL, KEYEVENTF_KEYUP))):
            events[index].type = INPUT_KEYBOARD
            events[index].data.ki = KeyboardInput(key, 0, flags, 0, 0)
        return self.user32.SendInput(len(events), events, ctypes.sizeof(Input)) == len(events)
