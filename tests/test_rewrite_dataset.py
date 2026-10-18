import json

from training.rewrite import schema
from training.rewrite.prompts import CLEAN_SYSTEM_PROMPT, SUGGEST_SYSTEM_PROMPT


def clean_case(**overrides):
    record = {
        "id": "edit-del-0001",
        "categories": ["edit_delete", "implicit_reason"],
        "scene": "shopping",
        "raw": "我今天要买苹果，梨子，哦昨天买过苹果了，去掉苹果",
        "output": "我今天要买梨子。",
    }
    record.update(overrides)
    return record


def suggestion(**overrides):
    record = {
        "id": "sug-0001",
        "scene": "work_chat",
        "input": "明天的会我去不了了，你们先开吧。",
        "suggestions": [
            {"label": "更礼貌", "text": "不好意思，明天的会我去不了，大家先开吧。"},
            {"label": "译成英文", "text": "I can't make it to tomorrow's meeting, please go ahead."},
        ],
    }
    record.update(overrides)
    return record


def test_prompts_describe_both_tasks():
    assert "改口" in CLEAN_SYSTEM_PROMPT and "翻译" in CLEAN_SYSTEM_PROMPT
    assert "JSON" in SUGGEST_SYSTEM_PROMPT and "3" in SUGGEST_SYSTEM_PROMPT


def test_load_jsonl_accepts_bom_and_crlf(tmp_path):
    path = tmp_path / "seeds.jsonl"
    path.write_bytes(b"\xef\xbb\xbf" + '{"id": "a"}\r\n\r\n{"id": "b"}\r\n'.encode("utf-8"))
    assert schema.load_jsonl(path) == [{"id": "a"}, {"id": "b"}]
    assert schema.load_jsonl(tmp_path / "missing.jsonl") == []


def test_load_jsonl_reports_the_bad_line(tmp_path):
    path = tmp_path / "seeds.jsonl"
    path.write_text('{"id": "a"}\n{broken\n', encoding="utf-8")
    try:
        schema.load_jsonl(path)
    except ValueError as exc:
        assert "seeds.jsonl:2" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_normalize_ignores_punctuation_space_and_case():
    assert schema.normalize("这个 PR，帮我 Review 一下。") == schema.normalize("这个pr帮我review一下")


def test_detect_lang():
    assert schema.detect_lang("明天开会。") == "zh"
    assert schema.detect_lang("See you tomorrow.") == "en"
    assert schema.detect_lang("这个 PR 帮我 review 一下") == "mixed"


def test_label_limits():
    assert schema.label_ok("更礼貌")
    assert not schema.label_ok("改成更加正式的说法")
    assert schema.label_ok("More formal")
    assert not schema.label_ok("Make it much more formal")
    assert not schema.label_ok("  ")


def test_valid_records_pass():
    assert schema.validate_clean_case(clean_case()) == []
    assert schema.validate_suggestion(suggestion()) == []
    assert schema.validate_suggestion(suggestion(input="好的。", suggestions=[])) == []


def test_clean_case_field_and_category_errors():
    errors = schema.validate_clean_case(clean_case(categories=["edit_delete", "typo_fix"], scene="moon", raw=""))
    assert any("typo_fix" in error for error in errors)
    assert any("scene" in error for error in errors)
    assert any("raw" in error for error in errors)


def test_instruction_cases_need_a_position():
    record = clean_case(categories=["instr_translate"], raw="明天下午开会，翻译成英文",
                        output="There's a meeting tomorrow afternoon.")
    assert any("instr_position" in error for error in schema.validate_clean_case(record))
    assert schema.validate_clean_case({**record, "instr_position": "suffix"}) == []
    assert any("instr_position" in error
               for error in schema.validate_clean_case(clean_case(instr_position="prefix")))


def test_negative_cases_must_stay_unchanged():
    record = clean_case(categories=["neg_instruction_like"], raw="他让我把这段翻译成英文",
                        output="他让我把这段翻译成英文。")
    assert schema.validate_clean_case(record) == []
    changed = {**record, "output": "他让我翻译。"}
    assert any("unchanged" in error for error in schema.validate_clean_case(changed))


def test_instruction_words_must_not_remain_in_output():
    record = clean_case(output="我今天要买梨子，去掉苹果。")
    assert any("去掉" in error for error in schema.validate_clean_case(record))
    assert schema.validate_clean_case({**record, "keeps_instruction_words": True}) == []


def test_suggestion_errors():
    too_many = suggestion(suggestions=[{"label": f"方向{i}", "text": f"第{i}种说法。"} for i in range(4)])
    assert any("at most 3" in error for error in schema.validate_suggestion(too_many))
    echo = suggestion(suggestions=[{"label": "原样", "text": "明天的会我去不了了，你们先开吧"}])
    assert any("repeats" in error for error in schema.validate_suggestion(echo))
    twins = suggestion(suggestions=[{"label": "甲", "text": "同一句。"}, {"label": "乙", "text": "同一句"}])
    assert any("repeats" in error for error in schema.validate_suggestion(twins))
    extra_key = suggestion(suggestions=[{"label": "甲", "text": "一句话。", "why": "x"}])
    assert any("label and text" in error for error in schema.validate_suggestion(extra_key))
    long_label = suggestion(suggestions=[{"label": "改成更加正式的说法", "text": "一句话。"}])
    assert any("label" in error for error in schema.validate_suggestion(long_label))


def test_duplicate_ids_across_files():
    assert schema.duplicate_ids([clean_case()], [suggestion()]) == []
    assert schema.duplicate_ids([clean_case()], [suggestion(id="edit-del-0001")]) == ["edit-del-0001"]


import random

from training.rewrite import augment


def test_chinese_fillers_are_inserted_at_clause_starts():
    rng = random.Random(1)
    noisy = augment.inject_fillers("我明天请个假，下午的会帮我请个假。", rng)
    assert noisy is not None and noisy != "我明天请个假，下午的会帮我请个假。"
    assert any(filler + "，" in noisy for filler in augment.ZH_FILLERS)
    assert noisy.replace("，", "").replace("。", "").endswith("下午的会帮我请个假")


def test_english_text_gets_english_fillers_on_word_boundaries():
    for seed in range(20):
        noisy = augment.inject_fillers("I will send it today, after the meeting.", random.Random(seed))
        assert noisy is not None
        assert not any(filler in noisy for filler in augment.ZH_FILLERS)
        words = noisy.replace(",", " ").replace(".", " ").lower().split()
        original = {"i", "will", "send", "it", "today", "after", "the", "meeting"}
        fillers = {word for filler in augment.EN_FILLERS for word in filler.split()}
        assert set(words) <= original | fillers


def test_repetition_doubles_a_clause_start():
    noisy = augment.inject_repetition("我觉得这个方案可以。", random.Random(3))
    assert noisy is not None
    assert noisy.startswith("我我") or noisy.startswith("我觉我觉") or noisy.startswith("我我我")
    assert augment.inject_repetition("Sounds good.", random.Random(3)).lower().startswith("sounds sounds")


def test_correction_needs_a_weekday_or_time():
    rng = random.Random(5)
    noisy = augment.inject_correction("周六下午三点开会。", rng)
    assert noisy is not None
    assert any(marker in noisy for marker in augment.ZH_CORRECTION_MARKERS)
    assert noisy.endswith("开会。")
    assert augment.inject_correction("我们改天再聊吧。", rng) is None
    english = augment.inject_correction("Let's meet on Friday.", random.Random(2))
    assert english is not None and english.endswith("Friday.")
    assert any(marker in english for marker in augment.EN_CORRECTION_MARKERS)


def test_augment_never_returns_the_clean_text():
    for text in ("好的。", "我们改天再聊吧。", "周六下午三点开会，记得带电脑。", "OK.", "第一，买菜\n第二，做饭"):
        for seed in range(30):
            for noisy, applied in augment.augment_text(text, random.Random(seed)):
                assert noisy != text
                assert applied and set(applied) <= {"filler", "repetition", "immediate_correction"}


def test_augment_is_deterministic():
    text = "周六下午三点开会，记得带电脑。"
    assert augment.augment_text(text, random.Random(9)) == augment.augment_text(text, random.Random(9))


from pathlib import Path

import pytest

from training.rewrite import build_dataset


def write_seeds(seeds_dir: Path, clean_cases, suggestions):
    seeds_dir.mkdir(parents=True, exist_ok=True)
    for name, records in (("clean_cases.jsonl", clean_cases), ("suggestions.jsonl", suggestions)):
        (seeds_dir / name).write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def sample_seeds(count=40):
    cases = [clean_case(id=f"case-{i:03d}", raw=f"额，周六下午{i % 9 + 1}点去买第{i}样东西",
                        output=f"周六下午{i % 9 + 1}点去买第{i}样东西。", categories=["filler"])
             for i in range(count)]
    tips = [suggestion(id=f"sug-{i:03d}", input=f"第{i}件事我明天处理。",
                       suggestions=[{"label": "更正式", "text": f"第{i}件事我将于明天处理完毕。"}])
            for i in range(count)]
    return cases, tips


def read_split(out_dir: Path, name: str):
    return [json.loads(line) for line in (out_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]


def test_split_is_stable_when_seeds_are_added():
    before = {f"case-{i}": build_dataset.split_for(f"case-{i}") for i in range(200)}
    assert set(before.values()) == {"train", "valid", "test"}
    assert {key: build_dataset.split_for(key) for key in before} == before
    counts = {name: list(before.values()).count(name) for name in ("train", "valid", "test")}
    assert counts["train"] > counts["test"] > counts["valid"]


def test_build_exports_chat_files_without_test_leakage(tmp_path):
    cases, tips = sample_seeds()
    write_seeds(tmp_path / "seeds", cases, tips)
    report = build_dataset.build(tmp_path / "seeds", tmp_path / "out")
    splits = {name: read_split(tmp_path / "out", name) for name in ("train", "valid", "test")}
    assert sum(report.counts.values()) == sum(len(rows) for rows in splits.values())
    assert report.hand_total == 80
    assert 0 < report.augmented_total <= int(report.hand_total * build_dataset.AUGMENT_RATIO)
    assert all(row["meta"]["source"] == "hand" for row in splits["test"])
    groups = {name: {row["meta"]["group"] for row in rows} for name, rows in splits.items()}
    assert not groups["test"] & (groups["train"] | groups["valid"])
    assert not groups["train"] & groups["valid"]
    row = splits["train"][0]
    assert [message["role"] for message in row["messages"]] == ["system", "user", "assistant"]


def test_augmented_rows_target_the_clean_text(tmp_path):
    cases, tips = sample_seeds()
    write_seeds(tmp_path / "seeds", cases, tips)
    build_dataset.build(tmp_path / "seeds", tmp_path / "out")
    rows = [row for name in ("train", "valid") for row in read_split(tmp_path / "out", name)
            if row["meta"]["source"] == "augmented"]
    assert rows
    for row in rows:
        user, assistant = row["messages"][1]["content"], row["messages"][2]["content"]
        assert row["meta"]["task"] == "clean"
        assert user != assistant
        assert row["messages"][0]["content"] == build_dataset.CLEAN_SYSTEM_PROMPT


def test_suggest_examples_round_trip_as_compact_json(tmp_path):
    cases, tips = sample_seeds()
    write_seeds(tmp_path / "seeds", cases, tips)
    build_dataset.build(tmp_path / "seeds", tmp_path / "out")
    rows = [row for name in ("train", "valid", "test") for row in read_split(tmp_path / "out", name)
            if row["meta"]["task"] == "suggest"]
    assert len(rows) == 40
    content = rows[0]["messages"][2]["content"]
    assert "\\u" not in content and ", " not in content and "更正式" in content
    assert json.loads(content)[0].keys() == {"label", "text"}
    assert rows[0]["messages"][0]["content"] == build_dataset.SUGGEST_SYSTEM_PROMPT


def test_build_fails_with_every_error_listed(tmp_path):
    cases, tips = sample_seeds(3)
    cases[1]["scene"] = "moon"
    tips[2]["id"] = cases[0]["id"]
    write_seeds(tmp_path / "seeds", cases, tips)
    with pytest.raises(build_dataset.DatasetError) as caught:
        build_dataset.build(tmp_path / "seeds", tmp_path / "out")
    text = "\n".join(caught.value.errors)
    assert "case-001" in text and "scene" in text
    assert "duplicate id" in text and "case-000" in text
    assert not (tmp_path / "out" / "train.jsonl").exists()


def test_coverage_warns_below_plan_and_flags_near_duplicates(tmp_path):
    cases, tips = sample_seeds(3)
    cases.append(clean_case(id="case-dup", raw=cases[0]["raw"] + "啊", output=cases[0]["output"],
                            categories=["filler"]))
    write_seeds(tmp_path / "seeds", cases, tips)
    report = build_dataset.build(tmp_path / "seeds", tmp_path / "out")
    assert any("instr_translate" in warning for warning in report.warnings)
    assert any("near-duplicate" in warning and "case-dup" in warning for warning in report.warnings)
    assert any(line.startswith("filler") for line in report.coverage)


def test_english_repetition_keeps_the_word_as_spoken():
    assert augment.inject_repetition("I need eggs.", random.Random(0)) == "I I need eggs."
    assert augment.inject_repetition("OK.", random.Random(0)) == "OK OK."


def test_english_filler_at_start_lowercases_the_next_word():
    for seed in range(10):
        noisy = augment.inject_fillers("The meeting is at 3.", random.Random(seed))
        assert noisy.endswith(", the meeting is at 3.")
        kept = augment.inject_fillers("I think so.", random.Random(seed))
        assert kept.endswith(", I think so.")


def test_english_dominant_mixed_text_gets_english_noise():
    for seed in range(20):
        noisy = augment.inject_fillers("Mom said we're having 饺子 for dinner.", random.Random(seed))
        assert not any(filler in noisy for filler in augment.ZH_FILLERS)
        assert "饺子" in noisy


def test_correction_ignores_numbers_that_are_not_clock_hours():
    for seed in range(10):
        rng = random.Random(seed)
        assert augment.inject_correction("Let's meet at 10:30 am.", rng) is None
        assert augment.inject_correction("积分有100点。", rng) is None
        assert augment.inject_correction("每周一次例会。", rng) is None


def test_build_rejects_missing_seed_files(tmp_path):
    with pytest.raises(build_dataset.DatasetError) as caught:
        build_dataset.build(tmp_path / "nowhere", tmp_path / "out")
    assert any("missing seed file" in error for error in caught.value.errors)
    assert not (tmp_path / "out").exists()


def test_build_reports_lines_that_are_not_objects(tmp_path):
    cases, tips = sample_seeds(2)
    write_seeds(tmp_path / "seeds", cases, tips)
    with (tmp_path / "seeds" / "clean_cases.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("[1, 2]\n")
    with pytest.raises(build_dataset.DatasetError) as caught:
        build_dataset.build(tmp_path / "seeds", tmp_path / "out")
    assert any("JSON object" in error for error in caught.value.errors)
