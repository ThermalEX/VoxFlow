"""Recognize "remember …" in a dictation, without the model, so it always works.

The request may open the text ("记住明天开会") or follow a short opening such as a greeting ("你好，记住我是张三");
it never counts in the middle of a sentence ("我们要记住，安全第一").
"""

import re

# 记住 / 请记住 / 帮我记住 / 你记一下 / 记下来 …, but not 记住了 / 记住没 (a reply, not a request).
_CHINESE = re.compile(r"(?:请|麻烦)?(?:你|帮我|给我)?(?:记住|记一下|记下来)(?![了没吗啦呀])(?:一下)?[，,：:、。\s]*")
# "remember that …", "remember this: …", "please remember my name is …"; "remember to …", "remember when …" and
# "remember me" stay ordinary text.
_NOT_A_REQUEST = r"(?:to|when|how|what|where|why|who|whom|which|whether|if|me|us|him|her|them|it)\b"
_ENGLISH = re.compile(r"\b(?:please\s+|(?:can|could|would)\s+you\s+)?remember"
                      rf"(?:\s+that\b|(?:\s+this)?\s*[,:]|(?=\s+(?!{_NOT_A_REQUEST})[A-Za-z]))\s*", re.I)
_CLAUSE_END = "，,。.！!？?；;、：:"
MAX_OPENING = 12  # characters of a greeting or filler allowed before the request


def find_command(text: str) -> tuple[str, str] | None:
    """(opening, what to remember) for a "remember" request, or None when the text is not one."""
    for pattern, english in ((_CHINESE, False), (_ENGLISH, True)):
        for match in pattern.finditer(text):
            opening = text[:match.start()]
            said = opening.strip()
            if said and (len(said) > MAX_OPENING or said[-1] not in _CLAUSE_END):
                continue
            rest = text[match.end():].strip()
            if not rest:
                continue
            if english:
                rest = rest[0].upper() + rest[1:]
            return opening, rest
    return None


def strip_command(text: str) -> str | None:
    """The text without the "remember" request words, or None when the text is not one."""
    found = find_command(text)
    return None if found is None else found[0] + found[1]
