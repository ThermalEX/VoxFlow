"""Turn the way a time was said ("周三下午三点", "next Monday") into a calendar date, by rule.

The rewrite model only copies the words that were said; working out which day they mean is done here, where it
can be tested, because small models often get weekday arithmetic wrong.
"""

import re
from datetime import date, timedelta

_WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6, "七": 6}
_ENGLISH_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december")
_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUMBER = r"[0-9]{1,2}|[零〇一二两三四五六七八九十]{1,3}"
WEEKDAY_NAMES = "一二三四五六日"


def _number(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    if "十" in text:
        tens, _, ones = text.partition("十")
        value = (_DIGITS.get(tens, 0) if tens else 1) * 10 + (_DIGITS.get(ones, 0) if ones else 0)
        return value if all(ch in _DIGITS for ch in tens + ones) else None
    return _DIGITS.get(text) if len(text) == 1 else None


def _valid(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _upcoming_month_day(month: int, day: int, today: date) -> date | None:
    """A month and day said without a year: this year's, or next year's once it is well past."""
    found = _valid(today.year, month, day)
    if found is not None and (today - found).days > 60:
        found = _valid(today.year + 1, month, day)
    return found


def resolve(phrase: str, today: date) -> date | None:
    """The date a spoken time points to, or None when the words do not name one day."""
    text = phrase.strip()
    lowered = text.casefold()
    for words, offset in ((("大后天",), 3), (("后天",), 2), (("明天", "明早", "明晚", "明儿"), 1),
                          (("今天", "今晚", "今早", "今儿", "今日"), 0), (("day after tomorrow",), 2),
                          (("tomorrow",), 1), (("today", "tonight"), 0)):
        if any(word in lowered for word in words):
            return today + timedelta(days=offset)
    match = re.search(r"(下下|下|这|本)?(?:个)?(?:周|星期|礼拜)([一二三四五六日天七])", text)
    if match and "每" not in text[:match.start() + 1]:
        weekday = _WEEKDAY[match.group(2)]
        monday = today - timedelta(days=today.weekday())
        weeks = {"下下": 2, "下": 1}.get(match.group(1) or "", 0)
        found = monday + timedelta(weeks=weeks, days=weekday)
        if not match.group(1) and found < today:  # a bare 周一 that has passed means the next one
            found += timedelta(weeks=1)
        return found
    match = re.search(r"(next\s+)?(" + "|".join(_ENGLISH_DAYS) + r")", lowered)
    if match and "every" not in lowered:
        weekday = _ENGLISH_DAYS.index(match.group(2))
        days = (weekday - today.weekday()) % 7
        if match.group(1):
            days = days + 7 if days == 0 or weekday >= today.weekday() else days
        return today + timedelta(days=days)
    match = re.search(rf"(下个?月|({_NUMBER})月)\s*({_NUMBER})\s*[日号]", text)
    if match:
        day = _number(match.group(3))
        if day is None:
            return None
        if match.group(1).startswith("下"):
            year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
            return _valid(year, month, day)
        month = _number(match.group(2))
        return _upcoming_month_day(month, day, today) if month else None
    match = re.search(r"(" + "|".join(_MONTHS) + r"|" + "|".join(m[:3] for m in _MONTHS) + r")\.?\s+(\d{1,2})", lowered)
    if match:
        month = next(index for index, name in enumerate(_MONTHS, 1) if name.startswith(match.group(1)[:3]))
        return _upcoming_month_day(month, int(match.group(2)), today)
    return None


def describe_date(day: date) -> str:
    return f"{day.month}月{day.day}日周{WEEKDAY_NAMES[day.weekday()]}"
