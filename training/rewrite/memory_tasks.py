"""Seeds for the memory tasks (extract, fill, summary): validation and conversion to chat examples.

Memory rows only go to train and valid; the memory tasks are tested with the separate memory_eval set, so the
clean and suggest test split stays exactly as it was.
"""

import json
import re
from datetime import date

from voxflow.rewrite_prompts import (
    MEMORY_EXTRACT_SYSTEM_PROMPT, MEMORY_FILL_SYSTEM_PROMPT, MEMORY_SUMMARY_SYSTEM_PROMPT,
    memory_extract_message, memory_fill_message, memory_summary_message,
)

from .schema import detect_lang

TASKS = ("extract", "fill", "summary")
KINDS = ("person", "term", "event", "fact")
MAX_SUMMARY_CHARS = 300
_NUMBER = re.compile(r"\d+")


def _day(record: dict, key: str, errors: list[str]) -> date | None:
    try:
        return date.fromisoformat(str(record.get(key)))
    except ValueError:
        errors.append(f"{key} must be an ISO date")
        return None


def _strings(record: dict, key: str, errors: list[str], allow_empty: bool = False) -> list[str]:
    values = record.get(key)
    if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
        errors.append(f"{key} must be a list of non-empty strings")
        return []
    if not values and not allow_empty:
        errors.append(f"{key} must not be empty")
    return values


def validate_memory(record: dict) -> list[str]:
    errors: list[str] = []
    task = record.get("task")
    if not isinstance(record.get("id"), str) or not record.get("id"):
        errors.append("id must be a non-empty string")
    if task not in TASKS:
        return errors + [f"task must be one of {TASKS}"]
    if task == "extract":
        text = record.get("text")
        _day(record, "today", errors)
        if not isinstance(text, str) or not text.strip():
            return errors + ["text must be a non-empty string"]
        items = record.get("items")
        if not isinstance(items, list):
            return errors + ["items must be a list"]
        for index, item in enumerate(items, 1):
            if not isinstance(item, dict) or item.get("kind") not in KINDS:
                errors.append(f"item {index} needs a kind from {KINDS}")
                continue
            if not isinstance(item.get("content"), str) or not item["content"].strip():
                errors.append(f"item {index} needs content")
            allowed = {"kind", "content", "time"} if item["kind"] == "event" else {"kind", "content"}
            if set(item) - allowed:
                errors.append(f"item {index} has fields {sorted(set(item) - allowed)} not allowed for {item['kind']}")
            if "time" in item and (not isinstance(item["time"], str) or item["time"] not in text):
                errors.append(f"item {index} time must be copied from the text")
    elif task == "fill":
        memories = _strings(record, "memories", errors)
        text, output = record.get("text"), record.get("output")
        if not isinstance(text, str) or not text.strip() or not isinstance(output, str) or not output.strip():
            return errors + ["text and output must be non-empty strings"]
        added = set(_NUMBER.findall(output)) - set(_NUMBER.findall(text + " ".join(memories)))
        if added:
            errors.append(f"output adds numbers found in neither text nor memories: {sorted(added)}")
    else:
        _day(record, "day", errors)
        texts = _strings(record, "texts", errors)
        memories = _strings(record, "memories", errors, allow_empty=True)
        output = record.get("output")
        if not isinstance(output, str) or not output.strip():
            return errors + ["output must be a non-empty string"]
        if len(output) > MAX_SUMMARY_CHARS:
            errors.append(f"output is longer than {MAX_SUMMARY_CHARS} characters")
        added = set(_NUMBER.findall(output)) - set(_NUMBER.findall(" ".join(texts + memories) + record["day"]))
        if added:
            errors.append(f"output adds numbers found in neither the texts nor memories: {sorted(added)}")
    return errors


def memory_example(record: dict) -> tuple[str, str, str, str]:
    """(system, user, assistant, language) for one memory seed."""
    task = record["task"]
    if task == "extract":
        user = memory_extract_message(record["text"], date.fromisoformat(record["today"]))
        return (MEMORY_EXTRACT_SYSTEM_PROMPT, user, json.dumps(record["items"], ensure_ascii=False),
                detect_lang(record["text"]))
    if task == "fill":
        return (MEMORY_FILL_SYSTEM_PROMPT, memory_fill_message(record["text"], record["memories"]), record["output"],
                detect_lang(record["text"]))
    user = memory_summary_message(date.fromisoformat(record["day"]), record["texts"], record["memories"])
    return MEMORY_SUMMARY_SYSTEM_PROMPT, user, record["output"], detect_lang(" ".join(record["texts"]))


def texts_of(record: dict) -> list[str]:
    """The spoken texts a seed contains, for leak checks against the evaluation set."""
    return record.get("texts") or [record["text"]]
