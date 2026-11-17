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


def review_hunks(old: str, new: str) -> list[tuple]:
    """Split a rewrite into kept text and separate changes a reviewer can accept or reject.

    Returns ("same", text) and ("change", old_part, new_part) items in order. A heavy rewrite is one
    change; a single character or bare whitespace between two changes joins them, so a reworded
    phrase stays one decision instead of a scatter of letters."""
    if similarity(old, new) < LARGE_CHANGE_SIMILARITY:
        return [("change", old, new)]
    items: list[list] = []
    for kind, text in diff_segments(old, new):
        if kind == "same":
            items.append(["same", text])
            continue
        if not items or items[-1][0] != "change":
            items.append(["change", "", ""])
        items[-1][1 if kind == "removed" else 2] += text
    merged: list[list] = []
    for index, item in enumerate(items):
        between = 0 < index < len(items) - 1 and item[0] == "same" and len(item[1].strip()) <= 1
        if between and merged and merged[-1][0] == "change" and items[index + 1][0] == "change":
            merged[-1][1] += item[1]
            merged[-1][2] += item[1]
            continue
        if item[0] == "change" and merged and merged[-1][0] == "change":
            merged[-1][1] += item[1]
            merged[-1][2] += item[2]
            continue
        merged.append(list(item))
    # Spacing alone (e.g. between Chinese and Latin script) is formatting, not a decision: apply it quietly.
    result: list[list] = []
    for item in merged:
        if item[0] == "change" and "".join(item[1].split()) == "".join(item[2].split()):
            item = ["same", item[2]]
        if item[0] == "same" and result and result[-1][0] == "same":
            result[-1][1] += item[1]
            continue
        result.append(item)
    return [tuple(item) for item in result]


def resolve_review(hunks: list[tuple], accepted: list[bool]) -> str:
    """The text with each change taken from the rewrite if accepted, else from what was said."""
    parts, change = [], 0
    for item in hunks:
        if item[0] == "same":
            parts.append(item[1])
        else:
            parts.append(item[2] if accepted[change] else item[1])
            change += 1
    return "".join(parts)


def review_html(hunks: list[tuple], accepted: list[bool], text_rgb, removed_rgb, added_rgb) -> str:
    """Show every change in place: the version in use is underlined, the other is struck through,
    and each change is a link the reviewer clicks to switch it."""
    parts, change = [], 0
    for item in hunks:
        if item[0] == "same":
            parts.append(_span(item[1], text_rgb, 1.0))
            continue
        old, new = item[1], item[2]
        if accepted[change]:
            dropped, kept, kept_rgb = old, new, added_rgb
        else:
            dropped, kept, kept_rgb = new, old, text_rgb
        inner = ""
        if dropped:
            inner += _span(dropped, removed_rgb, 0.75, strike=True)
        if kept:
            inner += (f'<span style="color: rgb({kept_rgb[0]},{kept_rgb[1]},{kept_rgb[2]});'
                      f' text-decoration: underline;">{html.escape(kept)}</span>')
        parts.append(f'<a href="change:{change}" style="text-decoration: none;">{inner}</a>')
        change += 1
    return f'<div style="white-space: pre-wrap;">{"".join(parts)}</div>'


def highlight_html(text: str, progress: float, text_rgb, accent_rgb) -> str:
    """One frame of the "remembered" pulse: the text glows in the accent color and fades back."""
    progress = min(1.0, max(0.0, progress))
    weight = 1 - abs(2 * progress - 1)  # 0 → 1 → 0
    rgb = tuple(round(base + (accent - base) * weight) for base, accent in zip(text_rgb, accent_rgb))
    return f'<div style="white-space: pre-wrap;">{_span(text, rgb, 1.0)}</div>'


def same_text(first: str, second: str) -> bool:
    def key(text: str) -> str:
        text = unicodedata.normalize("NFKC", text).casefold()
        return "".join(ch for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P"))

    return key(first) == key(second)


def join_continuation(prefix: str, addition: str) -> str:
    """Append newly dictated text: Chinese joins directly, text after Latin script gets a space."""
    prefix, addition = prefix.rstrip(), addition.strip()
    if not addition:
        return prefix
    if not prefix:
        return addition
    return prefix + (" " if prefix[-1].isascii() else "") + addition
