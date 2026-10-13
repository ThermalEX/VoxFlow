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
