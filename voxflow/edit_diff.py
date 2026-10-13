"""Diff a spoken transcript against its rewrite and render the one-time edit animation."""

import html
import re
import unicodedata
from difflib import SequenceMatcher

LARGE_CHANGE_SIMILARITY = 0.5
_TOKEN = re.compile(r"[A-Za-z0-9']+|\s+|.", re.S)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def diff_segments(old: str, new: str) -> list[tuple[str, str]]:
    a, b = _tokens(old), _tokens(new)
    segments: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            segments.append(("same", "".join(a[i1:i2])))
            continue
        if i2 > i1:
            segments.append(("removed", "".join(a[i1:i2])))
        if j2 > j1:
            segments.append(("added", "".join(b[j1:j2])))
    return segments


def similarity(old: str, new: str) -> float:
    return SequenceMatcher(None, _tokens(old), _tokens(new), autojunk=False).ratio()


def _span(text: str, rgb, alpha: float, strike: bool = False) -> str:
    decoration = "text-decoration: line-through;" if strike else ""
    return (f'<span style="color: rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha:.2f});{decoration}">'
            f"{html.escape(text)}</span>")


def frame_html(old: str, new: str, progress: float, text_rgb, removed_rgb, added_rgb) -> str:
    progress = min(1.0, max(0.0, progress))
    if similarity(old, new) < LARGE_CHANGE_SIMILARITY:
        body = (_span(old, text_rgb, 1 - progress * 2) if progress < 0.5
                else _span(new, text_rgb, progress * 2 - 1))
    else:
        parts = []
        for kind, text in diff_segments(old, new):
            if kind == "same":
                parts.append(_span(text, text_rgb, 1.0))
            elif kind == "removed":
                parts.append(_span(text, removed_rgb, 1 - progress, strike=True))
            else:
                parts.append(_span(text, added_rgb, progress))
        body = "".join(parts)
    return f'<div style="white-space: pre-wrap;">{body}</div>'


def same_text(first: str, second: str) -> bool:
    def key(text: str) -> str:
        text = unicodedata.normalize("NFKC", text).casefold()
        return "".join(ch for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P"))

    return key(first) == key(second)
