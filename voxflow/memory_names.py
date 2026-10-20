"""Fix misheard names and terms by sound: a remembered 张三 turns a transcribed 张叁 back into 张三."""

import re

_HAN = re.compile(r"[㐀-鿿]")
MIN_LENGTH = 2
MAX_LENGTH = 8


def _sounds(char: str) -> frozenset[str]:
    from pypinyin import Style, pinyin  # loaded only once memory is in use

    return frozenset(pinyin(char, style=Style.NORMAL, heteronym=True)[0])


def _correctable(name: str) -> bool:
    return MIN_LENGTH <= len(name) <= MAX_LENGTH and all(_HAN.fullmatch(ch) for ch in name)


def correct_names(text: str, names: list[str]) -> str:
    """Replace runs of Chinese characters that sound exactly like a remembered name but are written differently.

    Two-character names must keep their first character (李明 may fix 李敏, but never the word 黎明), since
    short words that sound like a name are common; longer names only need to sound the same.
    """
    names = sorted({name for name in names if _correctable(name)}, key=len, reverse=True)
    if not names or not _HAN.search(text):
        return text
    chars = list(text)
    sounds: dict[str, frozenset[str]] = {}

    def sound(ch: str) -> frozenset[str]:
        if ch not in sounds:
            sounds[ch] = _sounds(ch)
        return sounds[ch]

    fixed = [False] * len(chars)
    for name in names:
        size = len(name)
        for start in range(len(chars) - size + 1):
            window = chars[start:start + size]
            if any(fixed[start:start + size]) or "".join(window) == name:
                continue
            if not all(_HAN.fullmatch(ch) for ch in window):
                continue
            if size == MIN_LENGTH and window[0] != name[0]:
                continue
            if all(sound(a) & sound(b) for a, b in zip(window, name)):
                chars[start:start + size] = list(name)
                fixed[start:start + size] = [True] * size
    return "".join(chars)
