"""Inject spoken noise into clean text; the clean text stays the training target."""

import random
import re

from .schema import detect_lang


ZH_FILLERS = ("额", "嗯", "呃", "啊", "那个", "就是", "然后")
EN_FILLERS = ("um", "uh", "like", "you know")
ZH_CORRECTION_MARKERS = ("不对", "不是", "哦不", "说错了")
EN_CORRECTION_MARKERS = ("no wait", "sorry", "I mean")
_ZH_DIGITS = "一二三四五六日"
_EN_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_ZH_TARGET = re.compile(r"(周|星期)([一二三四五六日天])|(\d{1,2})点")
_EN_TARGET = re.compile(r"\b(" + "|".join(_EN_WEEKDAYS) + r")\b|\b(\d{1,2})(?=\s?(?:am|pm)\b)")
_CJK_CHAR = re.compile(r"[㐀-鿿]")


def _clause_starts(text: str, separator: str) -> list[int]:
    starts = [0]
    index = text.find(separator)
    while index != -1:
        start = index + len(separator)
        if start < len(text):
            starts.append(start)
        index = text.find(separator, start)
    return starts


def inject_fillers(text: str, rng: random.Random) -> str | None:
    if "\n" in text:
        return None
    if detect_lang(text) == "en":
        starts = _clause_starts(text, ", ")
        position = rng.choice(starts)
        filler = rng.choice(EN_FILLERS)
        insert = f"{filler.capitalize()}, " if position == 0 else f"{filler}, "
    else:
        starts = _clause_starts(text, "，")
        position = rng.choice(starts)
        insert = f"{rng.choice(ZH_FILLERS)}，"
    return text[:position] + insert + text[position:]


def inject_repetition(text: str, rng: random.Random) -> str | None:
    if "\n" in text:
        return None
    if detect_lang(text) == "en":
        position = rng.choice(_clause_starts(text, ", "))
        match = re.match(r"[A-Za-z']+", text[position:])
        if not match:
            return None
        word = match.group(0)
        return text[:position] + word + " " + word.lower() + text[position + len(word):]
    candidates = [start for start in _clause_starts(text, "，") if _CJK_CHAR.match(text, start)]
    if not candidates:
        return None
    position = rng.choice(candidates)
    size = 2 if _CJK_CHAR.match(text, position + 1) and rng.random() < 0.3 else 1
    piece = text[position:position + size]
    return text[:position] + piece * rng.choice((1, 2)) + text[position:]


def inject_correction(text: str, rng: random.Random) -> str | None:
    if "\n" in text:
        return None
    if detect_lang(text) == "en":
        matches = list(_EN_TARGET.finditer(text))
        if not matches:
            return None
        match = rng.choice(matches)
        right = match.group(0)
        if match.group(1):
            wrong = rng.choice([day for day in _EN_WEEKDAYS if day != right])
        else:
            wrong = str(int(right) % 12 + 1)
        marker = rng.choice(EN_CORRECTION_MARKERS)
        return text[:match.start()] + f"{wrong}, {marker}, {right}" + text[match.end():]
    matches = list(_ZH_TARGET.finditer(text))
    if not matches:
        return None
    match = rng.choice(matches)
    right = match.group(0)
    if match.group(1):
        day = match.group(2)
        wrong = match.group(1) + rng.choice([d for d in _ZH_DIGITS if d != day and not (day == "天" and d == "日")])
    else:
        wrong = f"{int(match.group(3)) % 12 + 1}点"
    marker = rng.choice(ZH_CORRECTION_MARKERS)
    return text[:match.start()] + f"{wrong}，{marker}，{right}" + text[match.end():]


OPERATIONS = (
    ("filler", inject_fillers),
    ("repetition", inject_repetition),
    ("immediate_correction", inject_correction),
)


def augment_text(text: str, rng: random.Random, max_variants: int = 2) -> list[tuple[str, list[str]]]:
    variants: list[tuple[str, list[str]]] = []
    seen = {text}
    for size in range(1, max_variants + 1):
        noisy, applied = text, []
        for name, operation in rng.sample(OPERATIONS, k=len(OPERATIONS)):
            if len(applied) == size:
                break
            result = operation(noisy, rng)
            if result is not None and result != noisy:
                noisy, applied = result, applied + [name]
        if applied and noisy not in seen:
            seen.add(noisy)
            variants.append((noisy, sorted(applied)))
    return variants
