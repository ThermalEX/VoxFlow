"""Validate rewrite seeds, add spoken-noise variants and export train/valid/test chat files."""

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .augment import augment_text
from .prompts import CLEAN_SYSTEM_PROMPT, SUGGEST_SYSTEM_PROMPT
from .schema import (
    CATEGORIES,
    NEGATIVE_CATEGORIES,
    detect_lang,
    duplicate_ids,
    load_jsonl,
    validate_clean_case,
    validate_suggestion,
)


ROOT = Path(__file__).resolve().parent
SEEDS_DIR = ROOT / "seeds"
BUILD_DIR = ROOT / "build"
SPLIT_LIMITS = (("train", 85), ("valid", 90), ("test", 100))
AUGMENT_RATIO = 1.4
RANDOM_SEED = 20261013
NEAR_DUPLICATE_THRESHOLD = 0.8
EDIT_CATEGORIES = {"immediate_correction", "edit_delete", "edit_replace", "edit_insert", "implicit_reason"}
PLAN_MINIMUMS = (
    ("edits", EDIT_CATEGORIES, 250),
    ("instr_translate", {"instr_translate"}, 120),
    ("instr_style", {"instr_style"}, 140),
    ("instr_combo", {"instr_combo"}, 40),
    ("spoken_format", {"spoken_format"}, 60),
    ("negatives", set(NEGATIVE_CATEGORIES), 150),
    ("filler/repetition", {"filler", "repetition"}, 100),
)
SUGGESTION_MINIMUM = 400
FEW_SUGGESTIONS_MINIMUM = 40


class DatasetError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"{len(errors)} seed error(s)")
        self.errors = errors


@dataclass
class BuildReport:
    counts: dict[str, int] = field(default_factory=dict)
    hand_total: int = 0
    augmented_total: int = 0
    warnings: list[str] = field(default_factory=list)
    coverage: list[str] = field(default_factory=list)


def split_for(group_id: str) -> str:
    bucket = int(hashlib.sha256(group_id.encode("utf-8")).hexdigest(), 16) % 100
    for name, limit in SPLIT_LIMITS:
        if bucket < limit:
            return name
    raise AssertionError("unreachable")


def _example(system: str, user: str, assistant: str, meta: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "meta": meta,
    }


def _validate(cases: list[dict], tips: list[dict]) -> list[str]:
    errors = [f"{name} line {index}: each line must be a JSON object"
              for name, records in (("clean_cases", cases), ("suggestions", tips))
              for index, record in enumerate(records, 1) if not isinstance(record, dict)]
    if errors:
        return errors
    for record in cases:
        errors += [f"clean_cases {record.get('id')!r}: {error}" for error in validate_clean_case(record)]
    for record in tips:
        errors += [f"suggestions {record.get('id')!r}: {error}" for error in validate_suggestion(record)]
    errors += [f"duplicate id: {record_id}" for record_id in duplicate_ids(cases, tips)]
    return errors


def _trigrams(text: str) -> set[str]:
    return {text[index:index + 3] for index in range(max(1, len(text) - 2))}


def _near_duplicates(items: list[tuple[str, str]]) -> list[str]:
    grams = [(record_id, _trigrams(text)) for record_id, text in items]
    warnings = []
    for index, (first_id, first) in enumerate(grams):
        for second_id, second in grams[index + 1:]:
            if len(first | second) and len(first & second) / len(first | second) >= NEAR_DUPLICATE_THRESHOLD:
                warnings.append(f"near-duplicate seeds: {first_id} ~ {second_id}")
    return warnings


def _coverage(cases: list[dict], tips: list[dict]) -> tuple[list[str], list[str]]:
    category_counts = Counter(category for record in cases for category in record["categories"])
    lines = [f"{name}: {category_counts.get(name, 0)}" for name in sorted(CATEGORIES)]
    lines += [f"scene {name}: {count}" for name, count in sorted(Counter(
        record["scene"] for record in cases + tips).items())]
    lines += [f"lang {name}: {count}" for name, count in sorted(Counter(
        detect_lang(record.get("raw") or record["input"]) for record in cases + tips).items())]
    lines += [f"instr_position {name}: {count}" for name, count in sorted(Counter(
        record["instr_position"] for record in cases if "instr_position" in record).items())]
    few = sum(1 for record in tips if len(record["suggestions"]) <= 1)
    lines.append(f"suggestions: {len(tips)} (0-1 items: {few})")

    warnings = []
    for name, group, minimum in PLAN_MINIMUMS:
        count = sum(1 for record in cases if group & set(record["categories"]))
        if count < minimum:
            warnings.append(f"coverage {name}: {count} < planned {minimum}")
    if len(tips) < SUGGESTION_MINIMUM:
        warnings.append(f"coverage suggestions: {len(tips)} < planned {SUGGESTION_MINIMUM}")
    if few < FEW_SUGGESTIONS_MINIMUM:
        warnings.append(f"coverage short suggestions: {few} < planned {FEW_SUGGESTIONS_MINIMUM}")
    return lines, warnings


def build(seeds_dir: Path = SEEDS_DIR, out_dir: Path = BUILD_DIR) -> BuildReport:
    missing = [name for name in ("clean_cases.jsonl", "suggestions.jsonl") if not (seeds_dir / name).is_file()]
    if missing:
        raise DatasetError([f"missing seed file: {seeds_dir / name}" for name in missing])
    cases = load_jsonl(seeds_dir / "clean_cases.jsonl")
    tips = load_jsonl(seeds_dir / "suggestions.jsonl")
    errors = _validate(cases, tips)
    if errors:
        raise DatasetError(errors)

    rows: dict[str, list[dict]] = {name: [] for name, _limit in SPLIT_LIMITS}
    bases: list[tuple[str, str]] = []
    for record in sorted(cases, key=lambda item: item["id"]):
        split = split_for(record["id"])
        rows[split].append(_example(CLEAN_SYSTEM_PROMPT, record["raw"], record["output"], {
            "id": record["id"], "group": record["id"], "task": "clean", "source": "hand",
            "categories": record["categories"], "scene": record["scene"], "lang": detect_lang(record["raw"]),
        }))
        if split != "test" and "\n" not in record["output"]:
            bases.append((record["id"], record["output"]))
    for record in sorted(tips, key=lambda item: item["id"]):
        split = split_for(record["id"])
        assistant = json.dumps(record["suggestions"], ensure_ascii=False, separators=(",", ":"))
        rows[split].append(_example(SUGGEST_SYSTEM_PROMPT, record["input"], assistant, {
            "id": record["id"], "group": record["id"], "task": "suggest", "source": "hand",
            "categories": [], "scene": record["scene"], "lang": detect_lang(record["input"]),
        }))
        if split != "test":
            bases.append((record["id"], record["input"]))

    rng = random.Random(RANDOM_SEED)
    augmented = []
    for group, text in bases:
        for number, (noisy, applied) in enumerate(augment_text(text, rng), 1):
            augmented.append((group, number, noisy, text, applied))
    rng.shuffle(augmented)
    hand_total = len(cases) + len(tips)
    augmented = sorted(augmented[:int(hand_total * AUGMENT_RATIO)], key=lambda item: (item[0], item[1]))
    for group, number, noisy, text, applied in augmented:
        rows[split_for(group)].append(_example(CLEAN_SYSTEM_PROMPT, noisy, text, {
            "id": f"{group}#aug{number}", "group": group, "task": "clean", "source": "augmented",
            "categories": applied, "scene": None, "lang": detect_lang(text),
        }))

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, split_rows in rows.items():
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for row in split_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    coverage, warnings = _coverage(cases, tips)
    warnings += _near_duplicates([(record["id"], record["raw"]) for record in cases]
                                 + [(record["id"], record["input"]) for record in tips])
    return BuildReport(
        counts={name: len(split_rows) for name, split_rows in rows.items()},
        hand_total=hand_total,
        augmented_total=len(augmented),
        warnings=warnings,
        coverage=coverage,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the spoken-text rewrite dataset")
    parser.add_argument("--seeds", type=Path, default=SEEDS_DIR)
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    args = parser.parse_args()
    try:
        report = build(args.seeds, args.out)
    except (DatasetError, ValueError) as exc:
        for error in getattr(exc, "errors", [str(exc)]):
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    print(f"hand {report.hand_total} | augmented {report.augmented_total} | "
          + " | ".join(f"{name} {count}" for name, count in report.counts.items()))
    for line in report.coverage:
        print(f"  {line}")
    for warning in report.warnings:
        print(f"WARN {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
