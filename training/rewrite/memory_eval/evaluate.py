"""Score a model on the memory tasks (extract, fill, summary) through an OpenAI-compatible endpoint.

Run: python -m training.rewrite.memory_eval.evaluate --endpoint http://127.0.0.1:8765/v1 --output <dir>
"""

import argparse
import json
import re
import statistics
import time
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from voxflow.edit_diff import same_text
from voxflow.memory_store import normalize
from voxflow.rewrite_prompts import (
    MEMORY_EXTRACT_SYSTEM_PROMPT, memory_extract_message,
)
from voxflow.rewriter import EXTRACT_ANSWER_TOKENS, MEMORY_TIMEOUT, RewriteClient, parse_memory_items

HERE = Path(__file__).resolve().parent
_NUMBER = re.compile(r"\d+")


def read(name: str) -> list[dict]:
    return [json.loads(line) for line in (HERE / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def similar(first: str, second: str) -> bool:
    a, b = normalize(first), normalize(second)
    return bool(a and b) and (a in b or b in a or SequenceMatcher(None, a, b).ratio() >= 0.6)


def invented(content: str, source: str) -> bool:
    """An item mostly made of characters that are not in the text it came from."""
    key = normalize(content)
    return bool(key) and sum(ch in normalize(source) for ch in key) / len(key) < 0.5


def new_numbers(text: str, *sources: str) -> list[str]:
    known = set(_NUMBER.findall(" ".join(sources)))
    return [number for number in _NUMBER.findall(text) if number not in known]


FILLER = set("的在到和于了")


def added_details_present(text: str, expected: str, prediction: str, needed: float = 0.8) -> bool:
    """Whether the details the expected text adds (times, places, names) show up in the prediction,
    wherever and however the model worked them in."""
    added = "".join(expected[j1:j2] for tag, _i1, _i2, j1, j2
                    in SequenceMatcher(None, text, expected, autojunk=False).get_opcodes() if tag in ("insert", "replace"))
    chars = [ch for ch in normalize(added) if ch not in FILLER]
    if not chars:
        return True
    present = normalize(prediction)
    return sum(ch in present for ch in chars) / len(chars) >= needed


def timed(call):
    started = time.perf_counter()
    try:
        return call(), time.perf_counter() - started, ""
    except Exception as exc:  # noqa: BLE001 - a failed call is scored, not fatal
        return None, time.perf_counter() - started, str(exc)


def evaluate_extract(client: RewriteClient, out) -> dict:
    stats = {"cases": 0, "json_ok": 0, "predicted": 0, "expected": 0, "matched_pred": 0, "matched_exp": 0,
             "matched_exp_any_kind": 0, "empty_cases": 0, "empty_ok": 0, "events": 0, "event_time_ok": 0,
             "invented": 0}
    latencies = []
    for case in read("extract.jsonl"):
        message = memory_extract_message(case["text"], date.fromisoformat(case["today"]))
        raw, seconds, error = timed(lambda: client._chat(MEMORY_EXTRACT_SYSTEM_PROMPT, message, MEMORY_TIMEOUT,
                                                         EXTRACT_ANSWER_TOKENS))
        latencies.append(seconds)
        raw = raw or ""
        items = parse_memory_items(raw)
        expected = case["expected"]
        stats["cases"] += 1
        stats["json_ok"] += "[" in raw and "]" in raw and not error
        stats["predicted"] += len(items)
        stats["expected"] += len(expected)
        stats["invented"] += sum(invented(item["content"], case["text"]) for item in items)
        stats["matched_pred"] += sum(any(item["kind"] == want["kind"] and similar(item["content"], want["content"])
                                         for want in expected) for item in items)
        for want in expected:
            same_kind = [item for item in items
                         if item["kind"] == want["kind"] and similar(item["content"], want["content"])]
            stats["matched_exp"] += bool(same_kind)
            stats["matched_exp_any_kind"] += any(similar(item["content"], want["content"]) for item in items)
            if want["kind"] == "event":
                stats["events"] += 1
                stats["event_time_ok"] += any(any(normalize(spelling) in normalize(item.get("time", ""))
                                                  for spelling in want["time"]) for item in same_kind)
        if not expected:
            stats["empty_cases"] += 1
            stats["empty_ok"] += not items
        out.write(json.dumps({"task": "extract", "id": case["id"], "text": case["text"], "raw": raw,
                              "items": items, "expected": expected, "error": error}, ensure_ascii=False) + "\n")
    s = stats
    return {
        "cases": s["cases"],
        "json_ok": s["json_ok"] / s["cases"],
        "precision": s["matched_pred"] / s["predicted"] if s["predicted"] else None,
        "recall": s["matched_exp"] / s["expected"],
        "recall_any_kind": s["matched_exp_any_kind"] / s["expected"],
        "empty_ok": s["empty_ok"] / s["empty_cases"],
        "event_time_ok": s["event_time_ok"] / s["events"],
        "invented_items": s["invented"],
        "mean_items": s["predicted"] / s["cases"],
        "latency_median_s": statistics.median(latencies),
    }


def evaluate_fill(client: RewriteClient, out) -> dict:
    fill_cases = keep_cases = exact = covered = kept = 0
    invented_numbers = 0
    latencies = []
    for case in read("fill.jsonl"):
        filled, seconds, error = timed(lambda: client.fill(case["text"], case["memories"]))
        latencies.append(seconds)
        filled = filled or ""
        should_fill = not same_text(case["expected"], case["text"])
        invented_numbers += len(new_numbers(filled, case["text"], *case["memories"]))
        if should_fill:
            fill_cases += 1
            exact += same_text(filled, case["expected"])
            covered += added_details_present(case["text"], case["expected"], filled)
        else:
            keep_cases += 1
            kept += same_text(filled, case["text"])
        out.write(json.dumps({"task": "fill", "id": case["id"], "text": case["text"], "memories": case["memories"],
                              "prediction": filled, "expected": case["expected"], "error": error},
                             ensure_ascii=False) + "\n")
    return {"fill_cases": fill_cases, "fill_exact": exact / fill_cases, "fill_covered": covered / fill_cases,
            "keep_cases": keep_cases, "kept_unchanged": kept / keep_cases, "invented_numbers": invented_numbers,
            "latency_median_s": statistics.median(latencies)}


def evaluate_summary(client: RewriteClient, out) -> dict:
    coverage, invented_numbers, too_long, empty = [], 0, 0, 0
    latencies = []
    for case in read("summary.jsonl"):
        summary, seconds, error = timed(lambda: client.summarize(date.fromisoformat(case["day"]), case["texts"],
                                                                 case["memories"]))
        latencies.append(seconds)
        summary = summary or ""
        empty += not summary.strip()
        coverage.append(sum(mention.casefold() in summary.casefold() for mention in case["mentions"])
                        / len(case["mentions"]))
        invented_numbers += len(new_numbers(summary, *case["texts"], *case["memories"], case["day"]))
        too_long += len(summary) > 300
        out.write(json.dumps({"task": "summary", "id": case["id"], "prediction": summary, "error": error},
                             ensure_ascii=False) + "\n")
    return {"cases": len(coverage), "mention_coverage": statistics.mean(coverage),
            "invented_numbers": invented_numbers, "too_long": too_long, "empty": empty,
            "latency_median_s": statistics.median(latencies)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a model on the VoxFlow memory tasks")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8765/v1")
    parser.add_argument("--model", default="voxflow-rewrite")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    client = RewriteClient(args.endpoint, args.model)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "predictions-memory.jsonl").open("w", encoding="utf-8") as out:
        report = {"endpoint": args.endpoint, "extract": evaluate_extract(client, out),
                  "fill": evaluate_fill(client, out), "summary": evaluate_summary(client, out)}
    (args.output / "report-memory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
