"""Global shortcuts: "Ctrl+Shift+Space"-style text <-> Win32 RegisterHotKey arguments."""

import ctypes
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QSettings, Qt

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
ACTIONS = ("record", "continue")
DEFAULTS = {"record": "Ctrl+Shift+Space", "continue": "Ctrl+Alt+Shift+Space"}
HOTKEY_IDS = {"record": 0x564F, "continue": 0x5650}

_MODIFIERS = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))
_QT_MODIFIERS = ((Qt.KeyboardModifier.ControlModifier, "Ctrl"), (Qt.KeyboardModifier.AltModifier, "Alt"),
                 (Qt.KeyboardModifier.ShiftModifier, "Shift"), (Qt.KeyboardModifier.MetaModifier, "Win"))
# Without Ctrl, Alt or Win a global shortcut would swallow ordinary typing.
_REQUIRED = MOD_CONTROL | MOD_ALT | MOD_WIN

_KEY_NAMES: dict[int, str] = {
    0x20: "Space", 0x09: "Tab", 0x08: "Backspace", 0x13: "Pause", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home",
    0x23: "End", 0x21: "PgUp", 0x22: "PgDown", 0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0xC0: "`", 0xBD: "-", 0xBB: "=", 0xDB: "[", 0xDD: "]", 0xDC: "\\", 0xBA: ";", 0xDE: "'", 0xBC: ",",
    0xBE: ".", 0xBF: "/",
}
_KEY_NAMES.update({code: chr(code) for code in range(0x30, 0x3A)})
_KEY_NAMES.update({code: chr(code) for code in range(0x41, 0x5B)})
_KEY_NAMES.update({0x70 + index: f"F{index + 1}" for index in range(24)})
_KEY_CODES = {name.lower(): code for code, name in _KEY_NAMES.items()}

_QT_KEYS: dict[int, int] = {
    Qt.Key.Key_Space: 0x20, Qt.Key.Key_Tab: 0x09, Qt.Key.Key_Backspace: 0x08, Qt.Key.Key_Pause: 0x13,
    Qt.Key.Key_Insert: 0x2D, Qt.Key.Key_Delete: 0x2E, Qt.Key.Key_Home: 0x24, Qt.Key.Key_End: 0x23,
    Qt.Key.Key_PageUp: 0x21, Qt.Key.Key_PageDown: 0x22, Qt.Key.Key_Left: 0x25, Qt.Key.Key_Up: 0x26,
    Qt.Key.Key_Right: 0x27, Qt.Key.Key_Down: 0x28, Qt.Key.Key_QuoteLeft: 0xC0, Qt.Key.Key_Minus: 0xBD,
    Qt.Key.Key_Equal: 0xBB, Qt.Key.Key_BracketLeft: 0xDB, Qt.Key.Key_BracketRight: 0xDD,
    Qt.Key.Key_Backslash: 0xDC, Qt.Key.Key_Semicolon: 0xBA, Qt.Key.Key_Apostrophe: 0xDE,
    Qt.Key.Key_Comma: 0xBC, Qt.Key.Key_Period: 0xBE, Qt.Key.Key_Slash: 0xBF,
}
_QT_KEYS.update({Qt.Key.Key_0 + index: 0x30 + index for index in range(10)})
_QT_KEYS.update({Qt.Key.Key_A + index: 0x41 + index for index in range(26)})
_QT_KEYS.update({Qt.Key.Key_F1 + index: 0x70 + index for index in range(24)})

MODIFIER_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta, Qt.Key.Key_AltGr}


@dataclass(frozen=True)
class Hotkey:
    modifiers: int
    vk: int
    text: str = field(compare=False)


def _format(modifiers: int, vk: int) -> str:
    return "+".join([name for name, flag in _MODIFIERS if modifiers & flag] + [_KEY_NAMES[vk]])


def parse(text: str) -> Hotkey | None:
    """Read "Ctrl+Alt+K"-style text; None unless it has Ctrl, Alt or Win plus one supported key."""
    *modifier_names, key = [part.strip() for part in str(text).split("+")]
    modifiers = 0
    for name in modifier_names:
        flag = next((flag for known, flag in _MODIFIERS if known.lower() == name.lower()), None)
        if flag is None:
            return None
        modifiers |= flag
    vk = _KEY_CODES.get(key.lower())
    if vk is None or not modifiers & _REQUIRED:
        return None
    return Hotkey(modifiers, vk, _format(modifiers, vk))


def vk_from_qt(key: int) -> int:
    return _QT_KEYS.get(key, 0)


def compose(modifiers: Qt.KeyboardModifier, vk: int) -> str | None:
    """Text for a key press in the settings recorder, or None if it cannot be a global shortcut."""
    if vk not in _KEY_NAMES:
        return None
    names = [name for flag, name in _QT_MODIFIERS if modifiers & flag]
    hotkey = parse("+".join(names + [_KEY_NAMES[vk]]))
    return hotkey.text if hotkey else None


def held_modifiers(modifiers: Qt.KeyboardModifier) -> str:
    """Modifiers pressed so far, shown while the recorder waits for the main key."""
    return "".join(f"{name}+" for flag, name in _QT_MODIFIERS if modifiers & flag)


def saved(settings: QSettings, action: str) -> Hotkey:
    return parse(str(settings.value(f"hotkeys/{action}", DEFAULTS[action]))) or parse(DEFAULTS[action])


class Win32Hotkeys:
    """RegisterHotKey for a window; key repeat is suppressed so holding the keys toggles only once."""

    def register(self, hwnd: int, ident: int, hotkey: Hotkey) -> bool:
        if sys.platform != "win32":
            return False
        return bool(ctypes.windll.user32.RegisterHotKey(hwnd, ident, hotkey.modifiers | MOD_NOREPEAT, hotkey.vk))

    def unregister(self, hwnd: int, ident: int) -> None:
        if sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(hwnd, ident)
