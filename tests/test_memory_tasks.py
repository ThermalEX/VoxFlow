import json

import pytest

from training.rewrite import build_dataset
from training.rewrite.memory_tasks import memory_example, validate_memory
from voxflow.rewrite_prompts import MEMORY_EXTRACT_SYSTEM_PROMPT, MEMORY_FILL_SYSTEM_PROMPT, MEMORY_SUMMARY_SYSTEM_PROMPT

EXTRACT = {"id": "mem-ext-1", "task": "extract", "today": "2026-11-04", "text": "周四下午四点给客户做产品演示。",
           "items": [{"kind": "event", "content": "给客户做产品演示", "time": "周四下午四点"}]}
FILL = {"id": "mem-fill-1", "task": "fill", "memories": ["产品演示（周四下午四点）"], "text": "确认一下产品演示。",
        "output": "确认一下周四下午四点的产品演示。"}
SUMMARY = {"id": "mem-sum-1", "task": "summary", "day": "2026-11-04", "texts": ["周四下午四点给客户做产品演示。"],
           "memories": [], "output": "日程与会议：\n- 周四下午四点给客户做产品演示"}


def test_well_formed_memory_seeds_pass():
    assert validate_memory(EXTRACT) == validate_memory(FILL) == validate_memory(SUMMARY) == []
    assert validate_memory(EXTRACT | {"items": []}) == []


@pytest.mark.parametrize("record, problem", [
    (EXTRACT | {"task": "chat"}, "task must be one of"),
    (EXTRACT | {"today": "Tuesday"}, "today must be an ISO date"),
    (EXTRACT | {"items": [{"kind": "mood", "content": "开心"}]}, "needs a kind"),
    (EXTRACT | {"items": [{"kind": "event", "content": "演示", "time": "10月22日"}]}, "time must be copied"),
    (EXTRACT | {"items": [{"kind": "person", "content": "李思涵", "time": "周四"}]}, "not allowed for person"),
    (FILL | {"memories": []}, "memories must not be empty"),
    (FILL | {"output": "确认一下周四16点的产品演示。"}, "adds numbers"),
    (SUMMARY | {"output": "x" * 301}, "longer than"),
    (SUMMARY | {"texts": ["周四开会。"], "output": "- 周四3点开会"}, "adds numbers"),
])
def test_memory_seed_errors(record, problem):
    assert any(problem in error for error in validate_memory(record))


def test_memory_seeds_become_chat_examples_with_the_app_prompts():
    system, user, assistant, lang = memory_example(EXTRACT)
    assert system == MEMORY_EXTRACT_SYSTEM_PROMPT and lang == "zh"
    assert user.startswith("今天是11月4日（星期三，2026-11-04）。")
    assert json.loads(assistant) == EXTRACT["items"]
    system, user, assistant, _lang = memory_example(FILL)
    assert system == MEMORY_FILL_SYSTEM_PROMPT and assistant == FILL["output"] and "- 产品演示" in user
    system, _user, assistant, _lang = memory_example(SUMMARY)
    assert system == MEMORY_SUMMARY_SYSTEM_PROMPT and assistant == SUMMARY["output"]


def _write(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _seeds(tmp_path, memory_rows):
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    clean = {"id": "corr-1", "categories": ["immediate_correction"], "scene": "work_chat",
             "raw": "周五，不对，周六开会。", "output": "周六开会。"}
    tip = {"id": "sug-1", "scene": "work_chat", "input": "明天开会。", "suggestions": []}
    _write(seeds / "clean_cases.jsonl", [clean])
    _write(seeds / "suggestions.jsonl", [tip])
    _write(seeds / "memory.jsonl", memory_rows)
    return seeds


def test_memory_rows_never_land_in_the_test_split(tmp_path, monkeypatch):
    monkeypatch.setattr(build_dataset, "MEMORY_EVAL_DIR", tmp_path / "no-eval")
    rows = [FILL | {"id": f"mem-fill-{index}"} for index in range(60)]
    report = build_dataset.build(_seeds(tmp_path, rows), tmp_path / "out")
    test_rows = [json.loads(line) for line in (tmp_path / "out" / "test.jsonl").read_text(encoding="utf-8").splitlines()]
    assert not any(row["meta"]["task"].startswith("memory_") for row in test_rows)
    tasks = [json.loads(line)["meta"]["task"]
             for split in ("train", "valid") for line in (tmp_path / "out" / f"{split}.jsonl").read_text(
                 encoding="utf-8").splitlines()]
    assert tasks.count("memory_fill") == 60
    assert report.hand_total == 62


def test_memory_seeds_that_copy_an_evaluation_case_are_refused(tmp_path, monkeypatch):
    evaluation = tmp_path / "eval"
    evaluation.mkdir()
    _write(evaluation / "extract.jsonl", [{"id": "ext-001", "text": "周四下午四点给客户做产品演示。"}])
    monkeypatch.setattr(build_dataset, "MEMORY_EVAL_DIR", evaluation)
    with pytest.raises(build_dataset.DatasetError) as error:
        build_dataset.build(_seeds(tmp_path, [EXTRACT]), tmp_path / "out")
    assert any("too close to evaluation case ext-001" in message for message in error.value.errors)
