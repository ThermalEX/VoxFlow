import json

import pytest

from training.rewrite import metrics
from training.rewrite.train import tokenize_example


def row(task, user, gold, prediction, categories=(), system="sys"):
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": gold},
        ],
        "meta": {"id": user, "task": task, "categories": list(categories)},
        "prediction": prediction,
    }


def test_char_error_rate():
    assert metrics.char_error_rate("周六开会。", "周六开会。") == 0
    assert metrics.char_error_rate("周五开会。", "周六开会。") == pytest.approx(1 / 5)
    assert metrics.char_error_rate("", "") == 0


def test_new_numbers_lists_numbers_missing_from_the_source():
    assert metrics.new_numbers("下午3点开会，5个人参加", "下午3点开会") == ["5"]
    assert metrics.new_numbers("Meet at 10:30.", "十点半，Meet at 10:30") == []


def test_clean_metrics_scores_negatives_residue_and_categories():
    records = [
        row("clean", "他让我翻译成英文", "他让我翻译成英文。", "他让我翻译成英文。", ["neg_instruction_like"]),
        row("clean", "老师说要正式一点", "老师说要正式一点。", "老师说要正式。", ["neg_instruction_like"]),
        row("clean", "明天开会，翻译成英文", "There's a meeting tomorrow.", "明天开会，翻译成英文", ["instr_translate"]),
        row("clean", "额，周六开会", "周六开会。", "周六开会。", ["filler"]),
    ]
    scores = metrics.clean_metrics(records)
    assert scores["count"] == 4
    assert scores["exact"] == pytest.approx(2 / 4)
    assert scores["negative_kept"] == pytest.approx(1 / 2)
    assert scores["instruction_residue"] == pytest.approx(1 / 2)
    assert scores["by_category"]["filler"] == {"count": 1, "exact": 1.0}
    assert scores["by_category"]["instr_translate"]["exact"] == 0.0


def test_suggest_metrics_checks_json_and_rules():
    good = json.dumps([{"label": "更正式", "text": "本周五开会。"}], ensure_ascii=False)
    long_label = json.dumps([{"label": "改成更加正式的说法", "text": "周五开会。"}], ensure_ascii=False)
    invented = json.dumps([{"label": "更具体", "text": "周五下午3点开会。"}], ensure_ascii=False)
    records = [
        row("suggest", "周五开会。", good, good),
        row("suggest", "周五开会。", good, "not json"),
        row("suggest", "周五开会。", good, long_label),
        row("suggest", "周五开会。", good, invented),
    ]
    scores = metrics.suggest_metrics(records)
    assert scores["count"] == 4
    assert scores["json_valid"] == pytest.approx(3 / 4)
    assert scores["rules_ok"] == pytest.approx(2 / 4)
    assert scores["new_numbers"] == pytest.approx(1 / 4)
    assert scores["count_match"] == pytest.approx(3 / 4)


class CharTokenizer:
    eos_token = "<E>"

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking):
        assert not tokenize and add_generation_prompt and enable_thinking is False
        return "".join(f"[{m['role']}]{m['content']}" for m in messages) + "[assistant]"

    def __call__(self, text, add_special_tokens):
        assert add_special_tokens is False
        return {"input_ids": [ord(ch) for ch in text]}


def test_tokenize_example_trains_only_on_the_answer():
    example = tokenize_example(CharTokenizer(), {"messages": [
        {"role": "system", "content": "S"}, {"role": "user", "content": "U"}, {"role": "assistant", "content": "AB"},
    ]}, max_length=100)
    prompt = "[system]S[user]U[assistant]"
    assert example["input_ids"] == [ord(ch) for ch in prompt + "AB<E>"]
    assert example["labels"] == [-100] * len(prompt) + [ord(ch) for ch in "AB<E>"]
    assert example["attention_mask"] == [1] * len(example["input_ids"])
    assert tokenize_example(CharTokenizer(), {"messages": [
        {"role": "system", "content": "S"}, {"role": "user", "content": "U"}, {"role": "assistant", "content": "AB"},
    ]}, max_length=10) is None


def test_instruction_residue_covers_style_and_translation_phrasings():
    records = [
        row("clean", "周六来我家，热情一点", "周六来我家呀！", "周六来我家，热情一点。", ["instr_style"]),
        row("clean", "用英文说，我到了", "I'm here.", "用英文说，I'm here.", ["instr_translate"]),
        row("clean", "see you, in Chinese please", "回头见。", "回头见，in Chinese please", ["instr_translate"]),
        row("clean", "make it shorter, see you soon", "See you soon.", "See you soon.", ["instr_style"]),
    ]
    assert metrics.clean_metrics(records)["instruction_residue"] == pytest.approx(3 / 4)
