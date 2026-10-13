from voxflow import edit_diff

WHITE, GRAY, BLUE = (243, 247, 255), (150, 160, 175), (140, 190, 255)


def test_chinese_diff_is_per_character():
    assert edit_diff.diff_segments("额，我明天请个假啊。", "我明天请个假。") == [
        ("removed", "额，"), ("same", "我明天请个假"), ("removed", "啊"), ("same", "。")]


def test_english_diff_is_per_word():
    segments = edit_diff.diff_segments("I need eggs, bread, and cheese", "I need eggs and bread.")
    assert ("same", "I need eggs") in segments
    assert any(kind == "removed" and "cheese" in text for kind, text in segments)


def test_similarity_separates_light_edits_from_rewrites():
    assert edit_diff.similarity("额，我明天请个假啊。", "我明天请个假。") > edit_diff.LARGE_CHANGE_SIMILARITY
    assert edit_diff.similarity("明天下午开会", "There's a meeting tomorrow afternoon.") < edit_diff.LARGE_CHANGE_SIMILARITY


def test_light_edit_frames_strike_then_fade_removed_text():
    start = edit_diff.frame_html("额，我请假。", "我请假。", 0.0, WHITE, GRAY, BLUE)
    end = edit_diff.frame_html("额，我请假。", "我请假。", 1.0, WHITE, GRAY, BLUE)
    assert "line-through" in start and "额，" in start and "rgba(150,160,175,1.00)" in start
    assert "rgba(150,160,175,0.00)" in end


def test_rewrite_frames_crossfade_and_escape_html():
    early = edit_diff.frame_html("明天<开会>", "Meeting <tomorrow>.", 0.1, WHITE, GRAY, BLUE)
    late = edit_diff.frame_html("明天<开会>", "Meeting <tomorrow>.", 0.9, WHITE, GRAY, BLUE)
    assert "明天&lt;开会&gt;" in early and "Meeting" not in early
    assert "Meeting &lt;tomorrow&gt;." in late and "明天" not in late


def test_frames_keep_line_breaks():
    html = edit_diff.frame_html("待办，第一，开会", "待办：\n1. 开会", 1.0, WHITE, GRAY, BLUE)
    assert "pre-wrap" in html and "\n" in html


def test_same_text_ignores_punctuation_space_and_case():
    assert edit_diff.same_text("我明天请个假", "我明天请个假。")
    assert edit_diff.same_text("See you", "see you!")
    assert not edit_diff.same_text("额，我请假", "我请假")


def test_continuation_joins_chinese_directly_and_english_with_a_space():
    assert edit_diff.join_continuation("你好，我叫李四。", "他叫王五") == "你好，我叫李四。他叫王五"
    assert edit_diff.join_continuation("我叫李四", "他叫王五") == "我叫李四他叫王五"
    assert edit_diff.join_continuation("Hello, I'm Si Li.", "his name is Wu Wang") == "Hello, I'm Si Li. his name is Wu Wang"
    assert edit_diff.join_continuation("我在开会", "PR 晚点看") == "我在开会PR 晚点看"
    assert edit_diff.join_continuation("", "新的一句") == "新的一句"
    assert edit_diff.join_continuation("已有文字", "  ") == "已有文字"
