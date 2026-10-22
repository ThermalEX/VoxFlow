import json
from pathlib import Path

from voxflow.suggestion_labels import EN_TO_ZH, ZH_TO_EN, localize_label, translates_into_chinese

SEEDS = Path(__file__).resolve().parents[1] / "training" / "rewrite" / "seeds" / "suggestions.jsonl"


def test_labels_are_shown_in_the_interface_language():
    assert localize_label("更礼貌", "en") == "More polite"
    assert localize_label("More polite", "zh") == "更礼貌"
    assert localize_label("more formal", "zh") == "更正式"
    assert localize_label("更礼貌", "zh") == "更礼貌"
    assert localize_label("More polite", "en") == "More polite"


def test_unknown_labels_become_a_plain_rewrite():
    assert localize_label("更像诗", "en") == "Rewrite"
    assert localize_label("More poetic", "zh") == "改写"


def test_every_label_the_model_was_taught_has_a_translation():
    labels = {suggestion["label"] for line in SEEDS.read_text(encoding="utf-8").splitlines()
              for suggestion in json.loads(line)["suggestions"]}
    assert sorted(label for label in labels if label not in ZH_TO_EN and label not in EN_TO_ZH) == []


def test_a_chinese_version_of_an_english_text_is_recognized():
    assert translates_into_chinese("Send me the slides.", "把幻灯片发给我。")
    assert translates_into_chinese("Send me the slides.", "把 slides 发给我。")
    assert not translates_into_chinese("Send me the slides.", "Could you send me the slides?")
    assert not translates_into_chinese("Send me the slides.", "Send 张三 the slides, please.")
    assert not translates_into_chinese("把幻灯片发给我。", "请把幻灯片发给我。")
