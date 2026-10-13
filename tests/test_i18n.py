import pytest

from voxflow import i18n


def test_every_string_has_english_and_chinese():
    for key, (english, chinese) in i18n.STRINGS.items():
        assert english.strip() and chinese.strip(), key


def test_tr_follows_the_current_language_and_formats():
    i18n.set_language("zh")
    try:
        assert i18n.tr("status.mic_unavailable", error="busy") == "麦克风不可用：busy"
    finally:
        i18n.set_language("en")
    assert i18n.tr("status.mic_unavailable", error="busy") == "Microphone unavailable: busy"


def test_resolve_uses_explicit_choice_or_system(monkeypatch):
    assert i18n.resolve("zh") == "zh" and i18n.resolve("en") == "en"
    monkeypatch.setenv("VOXFLOW_LANG", "zh")
    assert i18n.resolve("system") == "zh"
    monkeypatch.setenv("VOXFLOW_LANG", "en")
    assert i18n.resolve("anything else") == "en"


def test_unknown_key_fails_loudly():
    with pytest.raises(KeyError):
        i18n.tr("no.such.key")
