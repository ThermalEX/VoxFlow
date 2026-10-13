"""Scores for rewrite-model predictions (spec section 8); pure Python so they run anywhere."""

import json
import re
from collections import defaultdict

from .schema import INSTRUCTION_WORDS, NEGATIVE_CATEGORIES, normalize, validate_suggestion

_NUMBER = re.compile(r"\d+")


def char_error_rate(prediction: str, gold: str) -> float:
    previous = list(range(len(gold) + 1))
    for row, pred_char in enumerate(prediction, 1):
        current = [row]
        for column, gold_char in enumerate(gold, 1):
            current.append(min(previous[column] + 1, current[column - 1] + 1,
                               previous[column - 1] + (pred_char != gold_char)))
        previous = current
    return previous[-1] / max(1, len(gold))


def new_numbers(text: str, source: str) -> list[str]:
    known = set(_NUMBER.findall(source))
    found: list[str] = []
    for number in _NUMBER.findall(text):
        if number not in known and number not in found:
            found.append(number)
    return found


def _rate(hits: int, total: int) -> float | None:
    return hits / total if total else None


def _parts(record: dict) -> tuple[str, str, str, list[str]]:
    messages = record["messages"]
    return messages[1]["content"], messages[2]["content"], record["prediction"], record["meta"]["categories"]


def clean_metrics(records: list[dict]) -> dict:
    exact = cer = invented = 0.0
    negatives = kept = others = residue = 0
    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for record in records:
        source, gold, prediction, categories = _parts(record)
        hit = normalize(prediction) == normalize(gold)
        exact += hit
        cer += char_error_rate(prediction, gold)
        invented += bool(new_numbers(prediction, source))
        for category in categories:
            by_category[category][0] += 1
            by_category[category][1] += hit
        if categories and set(categories) <= NEGATIVE_CATEGORIES:
            negatives += 1
            kept += normalize(prediction) == normalize(source)
        else:
            others += 1
            residue += any(word in prediction.casefold() and word not in gold.casefold()
                           for word in INSTRUCTION_WORDS)
    total = len(records)
    return {
        "count": total,
        "exact": _rate(int(exact), total),
        "cer": cer / total if total else None,
        "negative_kept": _rate(kept, negatives),
        "instruction_residue": _rate(residue, others),
        "new_numbers": _rate(int(invented), total),
        "by_category": {name: {"count": count, "exact": hits / count}
                        for name, (count, hits) in sorted(by_category.items())},
    }


def suggest_metrics(records: list[dict]) -> dict:
    valid = rules_ok = invented = count_match = items = 0
    for record in records:
        source, gold, prediction, _categories = _parts(record)
        try:
            parsed = json.loads(prediction)
        except json.JSONDecodeError:
            parsed = None
        if not isinstance(parsed, list):
            continue
        valid += 1
        items += len(parsed)
        count_match += len(parsed) == len(json.loads(gold))
        rules_ok += not validate_suggestion({"id": "prediction", "scene": "daily", "input": source,
                                             "suggestions": parsed})
        texts = [item.get("text", "") for item in parsed if isinstance(item, dict)]
        invented += any(new_numbers(text, source) for text in texts if isinstance(text, str))
    total = len(records)
    return {
        "count": total,
        "json_valid": _rate(valid, total),
        "rules_ok": _rate(rules_ok, total),
        "count_match": _rate(count_match, total),
        "new_numbers": _rate(invented, total),
        "mean_items": items / valid if valid else None,
    }
