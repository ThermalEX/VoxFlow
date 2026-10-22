"""Show the rewrite model's suggestion labels in the interface language.

The model labels a suggestion in the language of the text ("更礼貌" for Chinese, "More polite" for English), because
that is how it was trained. The labels come from a small, fixed vocabulary, so a table can show them in the
interface language instead; a label the table does not know becomes a plain "Rewrite".
"""

import re

_HAN = re.compile(r"[一-鿿]")

ZH_TO_EN = {
    "更礼貌": "More polite", "译成英文": "In English", "更正式": "More formal", "更简洁": "More concise",
    "更体贴": "More caring", "更委婉": "More tactful", "更完整": "More complete", "更客气": "More courteous",
    "更直接": "More direct", "改成通知": "As a notice", "更随和": "More easygoing", "更诚恳": "More sincere",
    "更有感染力": "More engaging", "更关心": "More caring", "更冷静": "Calmer", "改成告警": "As an alert",
    "更热情": "Warmer", "更走心": "More heartfelt", "更贴心": "More thoughtful", "更简短": "Shorter",
    "更克制": "More restrained", "改成换货": "Ask to exchange", "更专业": "More professional",
    "改成提问": "As a question", "给出备选": "Give options", "更鼓励": "More encouraging",
    "更有画面感": "More vivid", "更有感触": "More moving", "更有祝福": "With good wishes", "更温和": "Gentler",
    "更温暖": "Warmer", "给出建议": "Give advice", "更轻松": "More relaxed", "更有激情": "More passionate",
    "改成通报": "As an update", "更有成就感": "More proud", "更幽默": "Funnier", "更积极": "More positive",
    "更真诚": "More sincere", "更柔和": "Softer", "列成要点": "Bullet points", "改成公告": "As an announcement",
    "改成邮件": "As an email", "更亲切": "Friendlier", "更清晰": "Clearer", "更有文采": "More eloquent",
    "更口语": "More casual", "全中文": "All in Chinese", "更有推荐感": "More persuasive", "更兴奋": "More excited",
    "改成求助": "Ask for help", "分段": "In paragraphs", "改成复盘": "As a review", "改成评价": "As a review",
    "更有惊喜感": "More delighted", "更有担当": "More accountable", "更惬意": "More laid-back",
    "更急切": "More urgent", "更具体": "More specific", "更建设性": "More constructive", "更温馨": "Warmer",
    "更浪漫": "More romantic", "改成提醒": "As a reminder", "更商量": "More open", "改成推荐": "As a recommendation",
    "更有决心": "More determined", "改成交接": "As a handover", "改成步骤": "As steps", "更活泼": "More lively",
    "规范用语": "Standard wording", "精简": "More concise", "改正错别字": "Fix typos", "列成清单": "As a checklist",
    "列成步骤": "As steps", "加上标题": "Add a title", "改成反馈": "As feedback",
}
EN_TO_ZH = {
    "More polite": "更礼貌", "In Chinese": "译成中文", "More formal": "更正式", "Ask for notes": "请对方提供笔记",
    "Warmer": "更温暖", "More detailed": "更详细", "Calmer": "更冷静", "More vivid": "更生动",
    "More complete": "更完整", "More diplomatic": "更委婉", "More neutral": "更中立", "More friendly": "更友好",
    "As a notice": "改成通知", "As a reminder": "改成提醒", "More specific": "更具体", "Softer": "更柔和",
    "Friendlier": "更友好", "More concise": "更简洁", "Shorter": "更简短", "As a checklist": "改成清单",
    "As a review": "改成评价", "Gentler": "更温和", "More inviting": "更有邀请感", "More excited": "更兴奋",
    "More explicit": "更明确", "More professional": "更专业", "More constructive": "更有建设性",
    "In English": "译成英文", "More casual": "更口语", "Bullet points": "列成要点", "As an email": "改成邮件",
    "Fix typos": "改正错别字", "Standard wording": "规范用语", "Clearer": "更清晰", "More direct": "更直接",
}
FALLBACK = {"en": "Rewrite", "zh": "改写"}


def _is_chinese(label: str) -> bool:
    return bool(_HAN.search(label))


def localize_label(label: str, language: str) -> str:
    """The label in the interface language ("en" or "zh")."""
    label = label.strip()
    if language == "en" and _is_chinese(label):
        return ZH_TO_EN.get(label, FALLBACK["en"])
    if language == "zh" and not _is_chinese(label):
        return EN_TO_ZH.get(label, EN_TO_ZH.get(label.capitalize(), FALLBACK["zh"]))
    return label


def translates_into_chinese(source: str, suggestion: str) -> bool:
    """An English text whose suggestion is mostly Chinese: the model offering a Chinese translation."""
    if _HAN.search(source):
        return False
    han = len(_HAN.findall(suggestion))
    return han > 0 and han >= len(re.findall(r"[A-Za-z]+", suggestion))
