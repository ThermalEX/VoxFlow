"""Seed record rules for the spoken-text rewrite dataset."""

import json
import re
import unicodedata
from pathlib import Path


CATEGORIES = frozenset({
    "filler", "repetition", "immediate_correction",
    "edit_delete", "edit_replace", "edit_insert", "implicit_reason",
    "spoken_format", "instr_translate", "instr_style", "instr_combo",
    "neg_instruction_like", "neg_code_switch", "neg_clean",
})
NEGATIVE_CATEGORIES = frozenset({"neg_instruction_like", "neg_code_switch", "neg_clean"})
INSTRUCTION_CATEGORIES = frozenset({"instr_translate", "instr_style", "instr_combo"})
INSTRUCTION_POSITIONS = frozenset({"prefix", "suffix", "infix"})
SCENES = frozenset({
    "work_chat", "email", "family_friends", "customer_service", "shopping",
    "schedule", "tech", "school", "social_media", "daily",
})
# Phrases that should disappear once an instruction or edit has been applied.
INSTRUCTION_WORDS = (
    "翻译成", "翻成", "译成", "正式一点", "委婉一点", "简洁一点", "礼貌一点", "口语一点",
    "去掉", "删掉", "换成", "改成", "translate", "more formal", "more polite",
)
MAX_SUGGESTIONS = 3
MAX_LABEL_CHARS = 6
MAX_LABEL_WORDS = 3

_CJK = re.compile(r"[㐀-鿿]")
_LATIN_WORD = re.compile(r"[A-Za-z]+")


def load_jsonl(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{number}: {exc}") from exc
    return records


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P"))


def detect_lang(text: str) -> str:
    has_cjk = bool(_CJK.search(text))
    has_latin = bool(_LATIN_WORD.search(text))
    if has_cjk and has_latin:
        return "mixed"
    return "zh" if has_cjk else "en"


def label_ok(label: str) -> bool:
    label = label.strip()
    if not label:
        return False
    if _CJK.search(label):
        return len(label) <= MAX_LABEL_CHARS
    return len(label.split()) <= MAX_LABEL_WORDS


def _text_field(record: dict, key: str, errors: list[str]) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key} must be a non-empty string")
        return ""
    return value


def _common_fields(record: dict, errors: list[str]) -> None:
    if not isinstance(record.get("id"), str) or not record["id"]:
        errors.append("id must be a non-empty string")
    if record.get("scene") not in SCENES:
        errors.append(f"unknown scene: {record.get('scene')!r}")


def validate_clean_case(record: dict) -> list[str]:
    errors: list[str] = []
    _common_fields(record, errors)
    raw = _text_field(record, "raw", errors)
    output = _text_field(record, "output", errors)
    categories = record.get("categories")
    if not isinstance(categories, list) or not categories or not all(isinstance(c, str) for c in categories):
        errors.append("categories must be a non-empty list of strings")
        categories = []
    category_set = set(categories)
    unknown = sorted(category_set - CATEGORIES)
    if unknown:
        errors.append(f"unknown categories: {', '.join(unknown)}")

    position = record.get("instr_position")
    if category_set & INSTRUCTION_CATEGORIES:
        if position not in INSTRUCTION_POSITIONS:
            errors.append("instruction cases need instr_position prefix, suffix or infix")
    elif position is not None:
        errors.append("instr_position is only for instruction cases")

    if category_set and category_set <= NEGATIVE_CATEGORIES and raw and output:
        if normalize(raw) != normalize(output):
            errors.append("negative cases must keep the text unchanged apart from punctuation")
    if output and not category_set & NEGATIVE_CATEGORIES and not record.get("keeps_instruction_words"):
        residue = [word for word in INSTRUCTION_WORDS if word in output.casefold()]
        if residue:
            errors.append(f"output still contains instruction words: {', '.join(residue)}")
    return errors


def validate_suggestion(record: dict) -> list[str]:
    errors: list[str] = []
    _common_fields(record, errors)
    source = _text_field(record, "input", errors)
    suggestions = record.get("suggestions")
    if not isinstance(suggestions, list):
        errors.append("suggestions must be a list")
        return errors
    if len(suggestions) > MAX_SUGGESTIONS:
        errors.append(f"suggestions must have at most {MAX_SUGGESTIONS} items")
    seen = {normalize(source)} if source else set()
    for index, item in enumerate(suggestions, 1):
        if not isinstance(item, dict) or set(item) != {"label", "text"}:
            errors.append(f"suggestion {index} must have exactly label and text")
            continue
        label, text = item["label"], item["text"]
        if not isinstance(label, str) or not label_ok(label):
            errors.append(f"suggestion {index} label is empty or too long: {label!r}")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"suggestion {index} text must be a non-empty string")
            continue
        key = normalize(text)
        if key in seen:
            errors.append(f"suggestion {index} repeats the input or another suggestion")
        seen.add(key)
    return errors


def duplicate_ids(*record_lists: list[dict]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for records in record_lists:
        for record in records:
            record_id = record.get("id")
            if record_id in seen and record_id not in duplicates:
                duplicates.append(record_id)
            seen.add(record_id)
    return duplicates
