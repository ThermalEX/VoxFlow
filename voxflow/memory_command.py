"""Recognize "remember …" at the start of a dictation, without the model, so it always works."""

import re

# 记住 / 请记住 / 帮我记住 / 你记一下 / 记下来 …, but not 记住了 / 记住没 (a reply, not a request).
_CHINESE = re.compile(r"^\s*(?:请|麻烦)?(?:你|帮我|给我)?(?:记住|记一下|记下来)(?![了没吗啦呀])(?:一下)?[，,：:、。\s]*")
# "remember that …", "remember, …" or "remember: …"; "remember to …" stays ordinary text.
_ENGLISH = re.compile(r"^\s*(?:please\s+)?remember(?:\s+that\b|\s*[,:])\s*", re.I)


def strip_command(text: str) -> str | None:
    """The text without the leading "remember" request, or None when the text is not one."""
    for pattern in (_CHINESE, _ENGLISH):
        match = pattern.match(text)
        if match:
            rest = text[match.end():].strip()
            if not rest:
                return None
            return rest[0].upper() + rest[1:] if pattern is _ENGLISH else rest
    return None
