import pytest

from voxflow.memory_command import strip_command
from voxflow.memory_names import correct_names


@pytest.mark.parametrize("spoken, kept", [
    ("记住周三下午三点开评审会", "周三下午三点开评审会"),
    ("请记住，我叫王书涵。", "我叫王书涵。"),
    ("帮我记一下：项目代号是北极星", "项目代号是北极星"),
    ("记下来 明天交房租", "明天交房租"),
    ("你记住一下，客户姓欧阳", "客户姓欧阳"),
    ("Remember that the demo is on Friday.", "The demo is on Friday."),
    ("please remember: my manager is Lisa", "My manager is Lisa"),
])
def test_remember_requests_lose_the_request_words(spoken, kept):
    assert strip_command(spoken) == kept


@pytest.mark.parametrize("text", [
    "记住了，明天见。",
    "记住没？",
    "我记住你说的了。",
    "Remember to buy milk.",
    "I remember that day.",
    "记住",
    "remember:",
    "今天开会。",
])
def test_ordinary_text_is_not_a_remember_request(text):
    assert strip_command(text) is None


def test_names_that_sound_the_same_are_written_the_remembered_way():
    assert correct_names("把文件发给王淑涵。", ["王书涵"]) == "把文件发给王书涵。"
    assert correct_names("欧阳晓雨和王淑涵来了", ["王书涵", "欧阳小雨"]) == "欧阳小雨和王书涵来了"


def test_polyphonic_characters_still_match():
    assert correct_names("增国强明天到", ["曾国强"]) == "曾国强明天到"


def test_two_character_names_keep_their_first_character():
    assert correct_names("李铭，我们黎明出发。", ["李明"]) == "李明，我们黎明出发。"


def test_names_that_are_already_right_or_cross_punctuation_are_left_alone():
    assert correct_names("王书涵到了。", ["王书涵"]) == "王书涵到了。"
    assert correct_names("王，书涵", ["王书涵"]) == "王，书涵"
    assert correct_names("Ship VoxFlow today", ["VoxFlow", "王书涵"]) == "Ship VoxFlow today"


def test_names_that_cannot_be_corrected_are_ignored():
    assert correct_names("王淑涵", ["王", "VoxFlow", "一二三四五六七八九"]) == "王淑涵"
    assert correct_names("王淑涵", []) == "王淑涵"
