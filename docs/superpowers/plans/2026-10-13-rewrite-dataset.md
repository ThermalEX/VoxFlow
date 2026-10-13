# 口语改写数据集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `training/rewrite/` 下建立口语改写模型的数据集：共用系统提示、手写种子、校验与噪声扩增脚本，导出可直接用于微调的 train/valid/test chat JSONL。

**Architecture:** 种子 JSONL 是唯一数据源；`schema.py` 定义规则并逐条校验，`augment.py` 在干净文本上注入口语噪声，`build_dataset.py` 校验、扩增、按种子哈希稳定划分并导出，同时打印覆盖报告。种子数据由 Claude 在会话中分批手写，第一批经用户抽查 10 条校准风格后再写其余部分。

**Tech Stack:** Python 3.12 标准库（json、hashlib、random、re、unicodedata）、pytest 8.4.2。不新增依赖。

**Spec:** `docs/superpowers/specs/2026-10-13-rewrite-dataset-design.md`

## Global Constraints

- 仅 Python 3.12、仅标准库；使用仓库 `.venv`：`.\.venv\Scripts\python.exe`。
- 导出格式：每行 `{"messages": [system, user, assistant], "meta": {...}}`，`ensure_ascii=False`，UTF-8，`\n` 换行。
- 任务 2 的 assistant 内容是紧凑 JSON 数组字符串，每项恰为 `{"label", "text"}`，0–3 项。
- 标签：含汉字时不超过 6 个字符，否则不超过 3 个英文单词。
- 划分：按种子分组，训练 85% / 验证 5% / 测试 10%；测试集只含手写样本；扩增数 ≤ 手写数 × 1.4（占比 < 60%）。
- 类别标识固定为 spec 第 3 节的 14 个；场景固定为 `work_chat, email, family_friends, customer_service, shopping, schedule, tech, school, social_media, daily`。
- 不做同音错字纠正样本。
- 提交信息不得包含任何 Claude 署名（无 `Co-Authored-By`、无 “Generated with Claude Code”）。
- 工作区里有与本计划无关的未提交改动（`voxflow/window.py`、`README.md`、`tests/test_window.py`、`.gitignore`、`.vscode/`）；每次提交只 `git add` 本任务列出的文件，`.gitignore` 只暂存本任务新增的那一行（用 `git add -p`）。

## Review Focus

- 在 Windows 上编辑的种子文件可能带 BOM 或 CRLF：加载器必须照常读取（Task 1 测试 `test_load_jsonl_accepts_bom_and_crlf`）。
- 某个噪声操作在文本上无处可用（如没有星期或钟点可做即时纠正）：扩增必须跳过，不能产出与干净文本相同的“噪声”样本（Task 2 测试 `test_augment_never_returns_the_clean_text`）。
- 英文文本被注入中文口气词、或英文单词被从中间切开：扩增必须按语言选择噪声并只在词边界插入（Task 2 测试 `test_english_text_gets_english_fillers_on_word_boundaries`）。
- 新增种子后已有样本跑到别的划分，导致测试集泄漏进训练集：划分必须只由种子 id 决定（Task 3 测试 `test_split_is_stable_when_seeds_are_added`）。
- 任务 2 的 assistant JSON 被转义成 `\uXXXX` 或格式不一，训练时模型学到错误格式：导出必须可原样解析且保留中文（Task 3 测试 `test_suggest_examples_round_trip_as_compact_json`）。

---

### Task 1: 包骨架、系统提示与种子校验

**Files:**
- Create: `training/__init__.py`（空文件）
- Create: `training/rewrite/__init__.py`（空文件）
- Create: `training/rewrite/prompts.py`
- Create: `training/rewrite/schema.py`
- Modify: `pyproject.toml`（新增 `[tool.pytest.ini_options]`）
- Test: `tests/test_rewrite_dataset.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `prompts.CLEAN_SYSTEM_PROMPT: str`、`prompts.SUGGEST_SYSTEM_PROMPT: str`
  - `schema.CATEGORIES`、`NEGATIVE_CATEGORIES`、`INSTRUCTION_CATEGORIES`、`INSTRUCTION_POSITIONS`、`SCENES: frozenset[str]`
  - `schema.load_jsonl(path: str | Path) -> list[dict]`（文件不存在时返回 `[]`）
  - `schema.normalize(text: str) -> str`
  - `schema.detect_lang(text: str) -> str`（`"zh" | "en" | "mixed"`）
  - `schema.label_ok(label: str) -> bool`
  - `schema.validate_clean_case(record: dict) -> list[str]`
  - `schema.validate_suggestion(record: dict) -> list[str]`
  - `schema.duplicate_ids(*record_lists: list[dict]) -> list[str]`

- [ ] **Step 1: 让 pytest 能导入 `training` 包**

在 `pyproject.toml` 末尾追加：

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

创建空文件 `training/__init__.py` 和 `training/rewrite/__init__.py`。

- [ ] **Step 2: 写失败的测试**

创建 `tests/test_rewrite_dataset.py`：

```python
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
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_rewrite_dataset.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'training.rewrite.schema'`（或 `prompts`）

- [ ] **Step 4: 写系统提示**

创建 `training/rewrite/prompts.py`：

```python
"""System prompts shared by dataset export and, later, the runtime rewriter."""

CLEAN_SYSTEM_PROMPT = """你是语音输入的文字整理器。用户消息是语音识别的原始文本，请直接输出最终要输入的文字，不要解释。
规则：
1. 删除口气词和无意义的填充（如“额、嗯、那个、就是”，英文 um、uh、like），删除口吃式重复。
2. 说话人改口或要求修改前文（如“不对，是……”“去掉……”“把……换成……”“还有……”）时，按最终意图改好前文，并删除这些改口的话。
3. 把口述的格式命令（如“换行”“逗号”“第一……第二……”）转成对应的格式。
4. 说话人对全文提出要求（如翻译成英文、正式一点、委婉一点、简洁一点）时，执行要求并删除要求本身；要求可能在开头、结尾或句中。
5. 只是转述别人的话、或正文本身提到这些词时，不算要求，照常保留。
6. 中英混说保持原样，不擅自翻译；不添加原文没有的信息；已经通顺的句子原样输出，只补全必要的标点。"""

SUGGEST_SYSTEM_PROMPT = """你为语音输入的文字提供改写建议。用户消息是准备发送的文字。只输出一个 JSON 数组，最多 3 项，每项为 {"label": 简短标签, "text": 改写后的完整文字}。
规则：
1. 按内容和场景选择最有用的改写方向，如更正式、更委婉、更简洁、译成另一种语言、改成邮件等，不限于这些。
2. 每条建议都要与原文和其他建议有实质区别。
3. 不编造原文没有的人名、时间、数字等事实。
4. 原文很短或没有改写价值时，只给 1 项或输出 []。
5. 标签语言跟随原文，中文不超过 6 个字，英文不超过 3 个词。"""
```

- [ ] **Step 5: 写校验模块**

创建 `training/rewrite/schema.py`：

```python
"""Seed record rules for the spoken-text rewrite dataset."""

import json
import re
import unicodedata
from pathlib import Path


CATEGORIES = frozenset({
    "filler", "repetition", "immediate_correction",
    "edit_delete", "edit_replace", "edit_insert", "implicit_reason",
    "spoken_format", "instr_translate", "instr_style", "instr_combo",
    "neg_instruction_like", "neg_code_switch", "neg_clean",
})
NEGATIVE_CATEGORIES = frozenset({"neg_instruction_like", "neg_code_switch", "neg_clean"})
INSTRUCTION_CATEGORIES = frozenset({"instr_translate", "instr_style", "instr_combo"})
INSTRUCTION_POSITIONS = frozenset({"prefix", "suffix", "infix"})
SCENES = frozenset({
    "work_chat", "email", "family_friends", "customer_service", "shopping",
    "schedule", "tech", "school", "social_media", "daily",
})
# Phrases that should disappear once an instruction or edit has been applied.
INSTRUCTION_WORDS = (
    "翻译成", "翻成", "译成", "正式一点", "委婉一点", "简洁一点", "礼貌一点", "口语一点",
    "去掉", "删掉", "换成", "改成", "translate", "more formal", "more polite",
)
MAX_SUGGESTIONS = 3
MAX_LABEL_CHARS = 6
MAX_LABEL_WORDS = 3

_CJK = re.compile(r"[㐀-鿿]")
_LATIN_WORD = re.compile(r"[A-Za-z]+")


def load_jsonl(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{number}: {exc}") from exc
    return records


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P"))


def detect_lang(text: str) -> str:
    has_cjk = bool(_CJK.search(text))
    has_latin = bool(_LATIN_WORD.search(text))
    if has_cjk and has_latin:
        return "mixed"
    return "zh" if has_cjk else "en"


def label_ok(label: str) -> bool:
    label = label.strip()
    if not label:
        return False
    if _CJK.search(label):
        return len(label) <= MAX_LABEL_CHARS
    return len(label.split()) <= MAX_LABEL_WORDS


def _text_field(record: dict, key: str, errors: list[str]) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key} must be a non-empty string")
        return ""
    return value


def _common_fields(record: dict, errors: list[str]) -> None:
    if not isinstance(record.get("id"), str) or not record["id"]:
        errors.append("id must be a non-empty string")
    if record.get("scene") not in SCENES:
        errors.append(f"unknown scene: {record.get('scene')!r}")


def validate_clean_case(record: dict) -> list[str]:
    errors: list[str] = []
    _common_fields(record, errors)
    raw = _text_field(record, "raw", errors)
    output = _text_field(record, "output", errors)
    categories = record.get("categories")
    if not isinstance(categories, list) or not categories or not all(isinstance(c, str) for c in categories):
        errors.append("categories must be a non-empty list of strings")
        categories = []
    category_set = set(categories)
    unknown = sorted(category_set - CATEGORIES)
    if unknown:
        errors.append(f"unknown categories: {', '.join(unknown)}")

    position = record.get("instr_position")
    if category_set & INSTRUCTION_CATEGORIES:
        if position not in INSTRUCTION_POSITIONS:
            errors.append("instruction cases need instr_position prefix, suffix or infix")
    elif position is not None:
        errors.append("instr_position is only for instruction cases")

    if category_set and category_set <= NEGATIVE_CATEGORIES and raw and output:
        if normalize(raw) != normalize(output):
            errors.append("negative cases must keep the text unchanged apart from punctuation")
    if output and not category_set & NEGATIVE_CATEGORIES and not record.get("keeps_instruction_words"):
        residue = [word for word in INSTRUCTION_WORDS if word in output.casefold()]
        if residue:
            errors.append(f"output still contains instruction words: {', '.join(residue)}")
    return errors


def validate_suggestion(record: dict) -> list[str]:
    errors: list[str] = []
    _common_fields(record, errors)
    source = _text_field(record, "input", errors)
    suggestions = record.get("suggestions")
    if not isinstance(suggestions, list):
        errors.append("suggestions must be a list")
        return errors
    if len(suggestions) > MAX_SUGGESTIONS:
        errors.append(f"suggestions must have at most {MAX_SUGGESTIONS} items")
    seen = {normalize(source)} if source else set()
    for index, item in enumerate(suggestions, 1):
        if not isinstance(item, dict) or set(item) != {"label", "text"}:
            errors.append(f"suggestion {index} must have exactly label and text")
            continue
        label, text = item["label"], item["text"]
        if not isinstance(label, str) or not label_ok(label):
            errors.append(f"suggestion {index} label is empty or too long: {label!r}")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"suggestion {index} text must be a non-empty string")
            continue
        key = normalize(text)
        if key in seen:
            errors.append(f"suggestion {index} repeats the input or another suggestion")
        seen.add(key)
    return errors


def duplicate_ids(*record_lists: list[dict]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for records in record_lists:
        for record in records:
            record_id = record.get("id")
            if record_id in seen and record_id not in duplicates:
                duplicates.append(record_id)
            seen.add(record_id)
    return duplicates
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_rewrite_dataset.py`
Expected: 全部 PASS

- [ ] **Step 7: 运行全部测试，确认没有影响现有用例**

Run: `$env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`
Expected: 全部 PASS

- [ ] **Step 8: Commit**

```powershell
git add pyproject.toml training/__init__.py training/rewrite/__init__.py training/rewrite/prompts.py training/rewrite/schema.py tests/test_rewrite_dataset.py
git commit -m "Add rewrite dataset prompts and seed validation"
```

---

### Task 2: 口语噪声扩增

**Files:**
- Create: `training/rewrite/augment.py`
- Test: `tests/test_rewrite_dataset.py`（追加）

**Interfaces:**
- Consumes: `schema.detect_lang(text) -> str`
- Produces:
  - `augment.inject_fillers(text: str, rng: random.Random) -> str | None`
  - `augment.inject_repetition(text: str, rng: random.Random) -> str | None`
  - `augment.inject_correction(text: str, rng: random.Random) -> str | None`
  - `augment.augment_text(text: str, rng: random.Random, max_variants: int = 2) -> list[tuple[str, list[str]]]`：返回 `(噪声文本, 已应用的类别名列表)`，类别名取自 `filler` / `repetition` / `immediate_correction`；不会包含与原文相同的文本。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_rewrite_dataset.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_rewrite_dataset.py`
Expected: FAIL，`ImportError: cannot import name 'augment'`

- [ ] **Step 3: 实现扩增模块**

创建 `training/rewrite/augment.py`：

```python
"""Inject spoken noise into clean text; the clean text stays the training target."""

import random
import re

from .schema import detect_lang


ZH_FILLERS = ("额", "嗯", "呃", "啊", "那个", "就是", "然后")
EN_FILLERS = ("um", "uh", "like", "you know")
ZH_CORRECTION_MARKERS = ("不对", "不是", "哦不", "说错了")
EN_CORRECTION_MARKERS = ("no wait", "sorry", "I mean")
_ZH_DIGITS = "一二三四五六日"
_EN_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_ZH_TARGET = re.compile(r"(周|星期)([一二三四五六日天])|(\d{1,2})点")
_EN_TARGET = re.compile(r"\b(" + "|".join(_EN_WEEKDAYS) + r")\b|\b(\d{1,2})(?=\s?(?:am|pm)\b)")
_CJK_CHAR = re.compile(r"[㐀-鿿]")


def _clause_starts(text: str, separator: str) -> list[int]:
    starts = [0]
    index = text.find(separator)
    while index != -1:
        start = index + len(separator)
        if start < len(text):
            starts.append(start)
        index = text.find(separator, start)
    return starts


def inject_fillers(text: str, rng: random.Random) -> str | None:
    if "\n" in text:
        return None
    if detect_lang(text) == "en":
        starts = _clause_starts(text, ", ")
        position = rng.choice(starts)
        filler = rng.choice(EN_FILLERS)
        insert = f"{filler.capitalize()}, " if position == 0 else f"{filler}, "
    else:
        starts = _clause_starts(text, "，")
        position = rng.choice(starts)
        insert = f"{rng.choice(ZH_FILLERS)}，"
    return text[:position] + insert + text[position:]


def inject_repetition(text: str, rng: random.Random) -> str | None:
    if "\n" in text:
        return None
    if detect_lang(text) == "en":
        position = rng.choice(_clause_starts(text, ", "))
        match = re.match(r"[A-Za-z']+", text[position:])
        if not match:
            return None
        word = match.group(0)
        return text[:position] + word + " " + word.lower() + text[position + len(word):]
    candidates = [start for start in _clause_starts(text, "，") if _CJK_CHAR.match(text, start)]
    if not candidates:
        return None
    position = rng.choice(candidates)
    size = 2 if _CJK_CHAR.match(text, position + 1) and rng.random() < 0.3 else 1
    piece = text[position:position + size]
    return text[:position] + piece * rng.choice((1, 2)) + text[position:]


def inject_correction(text: str, rng: random.Random) -> str | None:
    if "\n" in text:
        return None
    if detect_lang(text) == "en":
        matches = list(_EN_TARGET.finditer(text))
        if not matches:
            return None
        match = rng.choice(matches)
        right = match.group(0)
        if match.group(1):
            wrong = rng.choice([day for day in _EN_WEEKDAYS if day != right])
        else:
            wrong = str(int(right) % 12 + 1)
        marker = rng.choice(EN_CORRECTION_MARKERS)
        return text[:match.start()] + f"{wrong}, {marker}, {right}" + text[match.end():]
    matches = list(_ZH_TARGET.finditer(text))
    if not matches:
        return None
    match = rng.choice(matches)
    right = match.group(0)
    if match.group(1):
        day = match.group(2)
        wrong = match.group(1) + rng.choice([d for d in _ZH_DIGITS if d != day and not (day == "天" and d == "日")])
    else:
        wrong = f"{int(match.group(3)) % 12 + 1}点"
    marker = rng.choice(ZH_CORRECTION_MARKERS)
    return text[:match.start()] + f"{wrong}，{marker}，{right}" + text[match.end():]


OPERATIONS = (
    ("filler", inject_fillers),
    ("repetition", inject_repetition),
    ("immediate_correction", inject_correction),
)


def augment_text(text: str, rng: random.Random, max_variants: int = 2) -> list[tuple[str, list[str]]]:
    variants: list[tuple[str, list[str]]] = []
    seen = {text}
    for size in range(1, max_variants + 1):
        noisy, applied = text, []
        for name, operation in rng.sample(OPERATIONS, k=len(OPERATIONS)):
            if len(applied) == size:
                break
            result = operation(noisy, rng)
            if result is not None and result != noisy:
                noisy, applied = result, applied + [name]
        if applied and noisy not in seen:
            seen.add(noisy)
            variants.append((noisy, sorted(applied)))
    return variants
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_rewrite_dataset.py`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```powershell
git add training/rewrite/augment.py tests/test_rewrite_dataset.py
git commit -m "Add spoken noise augmentation for rewrite dataset"
```

---

### Task 3: 构建脚本：划分、导出、覆盖报告

**Files:**
- Create: `training/rewrite/build_dataset.py`
- Create: `training/rewrite/seeds/clean_cases.jsonl`（空文件）
- Create: `training/rewrite/seeds/suggestions.jsonl`（空文件）
- Modify: `.gitignore`（追加 `training/rewrite/build/`）
- Test: `tests/test_rewrite_dataset.py`（追加）

**Interfaces:**
- Consumes: `schema.*`（Task 1）、`augment.augment_text`（Task 2）、`prompts.*`（Task 1）
- Produces:
  - `build_dataset.split_for(group_id: str) -> str`（`"train" | "valid" | "test"`）
  - `build_dataset.DatasetError(Exception)`，属性 `errors: list[str]`
  - `build_dataset.build(seeds_dir: Path, out_dir: Path) -> BuildReport`
  - `BuildReport`：`counts: dict[str, int]`（各划分条数）、`hand_total: int`、`augmented_total: int`、`warnings: list[str]`、`coverage: list[str]`
  - CLI：`.\.venv\Scripts\python.exe -m training.rewrite.build_dataset`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_rewrite_dataset.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_rewrite_dataset.py`
Expected: FAIL，`ImportError: cannot import name 'build_dataset'`

- [ ] **Step 3: 实现构建脚本**

创建 `training/rewrite/build_dataset.py`：

```python
"""Validate rewrite seeds, add spoken-noise variants and export train/valid/test chat files."""

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .augment import augment_text
from .prompts import CLEAN_SYSTEM_PROMPT, SUGGEST_SYSTEM_PROMPT
from .schema import (
    CATEGORIES,
    NEGATIVE_CATEGORIES,
    detect_lang,
    duplicate_ids,
    load_jsonl,
    validate_clean_case,
    validate_suggestion,
)


ROOT = Path(__file__).resolve().parent
SEEDS_DIR = ROOT / "seeds"
BUILD_DIR = ROOT / "build"
SPLIT_LIMITS = (("train", 85), ("valid", 90), ("test", 100))
AUGMENT_RATIO = 1.4
RANDOM_SEED = 20261013
NEAR_DUPLICATE_THRESHOLD = 0.8
EDIT_CATEGORIES = {"immediate_correction", "edit_delete", "edit_replace", "edit_insert", "implicit_reason"}
PLAN_MINIMUMS = (
    ("edits", EDIT_CATEGORIES, 250),
    ("instr_translate", {"instr_translate"}, 120),
    ("instr_style", {"instr_style"}, 140),
    ("instr_combo", {"instr_combo"}, 40),
    ("spoken_format", {"spoken_format"}, 60),
    ("negatives", set(NEGATIVE_CATEGORIES), 150),
    ("filler/repetition", {"filler", "repetition"}, 100),
)
SUGGESTION_MINIMUM = 400
FEW_SUGGESTIONS_MINIMUM = 40


class DatasetError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"{len(errors)} seed error(s)")
        self.errors = errors


@dataclass
class BuildReport:
    counts: dict[str, int] = field(default_factory=dict)
    hand_total: int = 0
    augmented_total: int = 0
    warnings: list[str] = field(default_factory=list)
    coverage: list[str] = field(default_factory=list)


def split_for(group_id: str) -> str:
    bucket = int(hashlib.sha256(group_id.encode("utf-8")).hexdigest(), 16) % 100
    for name, limit in SPLIT_LIMITS:
        if bucket < limit:
            return name
    raise AssertionError("unreachable")


def _example(system: str, user: str, assistant: str, meta: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "meta": meta,
    }


def _validate(cases: list[dict], tips: list[dict]) -> list[str]:
    errors = []
    for record in cases:
        errors += [f"clean_cases {record.get('id')!r}: {error}" for error in validate_clean_case(record)]
    for record in tips:
        errors += [f"suggestions {record.get('id')!r}: {error}" for error in validate_suggestion(record)]
    errors += [f"duplicate id: {record_id}" for record_id in duplicate_ids(cases, tips)]
    return errors


def _trigrams(text: str) -> set[str]:
    return {text[index:index + 3] for index in range(max(1, len(text) - 2))}


def _near_duplicates(items: list[tuple[str, str]]) -> list[str]:
    grams = [(record_id, _trigrams(text)) for record_id, text in items]
    warnings = []
    for index, (first_id, first) in enumerate(grams):
        for second_id, second in grams[index + 1:]:
            if len(first | second) and len(first & second) / len(first | second) >= NEAR_DUPLICATE_THRESHOLD:
                warnings.append(f"near-duplicate seeds: {first_id} ~ {second_id}")
    return warnings


def _coverage(cases: list[dict], tips: list[dict]) -> tuple[list[str], list[str]]:
    category_counts = Counter(category for record in cases for category in record["categories"])
    lines = [f"{name}: {category_counts.get(name, 0)}" for name in sorted(CATEGORIES)]
    lines += [f"scene {name}: {count}" for name, count in sorted(Counter(
        record["scene"] for record in cases + tips).items())]
    lines += [f"lang {name}: {count}" for name, count in sorted(Counter(
        detect_lang(record.get("raw") or record["input"]) for record in cases + tips).items())]
    lines += [f"instr_position {name}: {count}" for name, count in sorted(Counter(
        record["instr_position"] for record in cases if "instr_position" in record).items())]
    few = sum(1 for record in tips if len(record["suggestions"]) <= 1)
    lines.append(f"suggestions: {len(tips)} (0-1 items: {few})")

    warnings = []
    for name, group, minimum in PLAN_MINIMUMS:
        count = sum(1 for record in cases if group & set(record["categories"]))
        if count < minimum:
            warnings.append(f"coverage {name}: {count} < planned {minimum}")
    if len(tips) < SUGGESTION_MINIMUM:
        warnings.append(f"coverage suggestions: {len(tips)} < planned {SUGGESTION_MINIMUM}")
    if few < FEW_SUGGESTIONS_MINIMUM:
        warnings.append(f"coverage short suggestions: {few} < planned {FEW_SUGGESTIONS_MINIMUM}")
    return lines, warnings


def build(seeds_dir: Path = SEEDS_DIR, out_dir: Path = BUILD_DIR) -> BuildReport:
    cases = load_jsonl(seeds_dir / "clean_cases.jsonl")
    tips = load_jsonl(seeds_dir / "suggestions.jsonl")
    errors = _validate(cases, tips)
    if errors:
        raise DatasetError(errors)

    rows: dict[str, list[dict]] = {name: [] for name, _limit in SPLIT_LIMITS}
    bases: list[tuple[str, str]] = []
    for record in sorted(cases, key=lambda item: item["id"]):
        split = split_for(record["id"])
        rows[split].append(_example(CLEAN_SYSTEM_PROMPT, record["raw"], record["output"], {
            "id": record["id"], "group": record["id"], "task": "clean", "source": "hand",
            "categories": record["categories"], "scene": record["scene"], "lang": detect_lang(record["raw"]),
        }))
        if split != "test" and "\n" not in record["output"]:
            bases.append((record["id"], record["output"]))
    for record in sorted(tips, key=lambda item: item["id"]):
        split = split_for(record["id"])
        assistant = json.dumps(record["suggestions"], ensure_ascii=False, separators=(",", ":"))
        rows[split].append(_example(SUGGEST_SYSTEM_PROMPT, record["input"], assistant, {
            "id": record["id"], "group": record["id"], "task": "suggest", "source": "hand",
            "categories": [], "scene": record["scene"], "lang": detect_lang(record["input"]),
        }))
        if split != "test":
            bases.append((record["id"], record["input"]))

    rng = random.Random(RANDOM_SEED)
    augmented = []
    for group, text in bases:
        for number, (noisy, applied) in enumerate(augment_text(text, rng), 1):
            augmented.append((group, number, noisy, text, applied))
    rng.shuffle(augmented)
    hand_total = len(cases) + len(tips)
    augmented = sorted(augmented[:int(hand_total * AUGMENT_RATIO)], key=lambda item: (item[0], item[1]))
    for group, number, noisy, text, applied in augmented:
        rows[split_for(group)].append(_example(CLEAN_SYSTEM_PROMPT, noisy, text, {
            "id": f"{group}#aug{number}", "group": group, "task": "clean", "source": "augmented",
            "categories": applied, "scene": None, "lang": detect_lang(text),
        }))

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, split_rows in rows.items():
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for row in split_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    coverage, warnings = _coverage(cases, tips)
    warnings += _near_duplicates([(record["id"], record["raw"]) for record in cases]
                                 + [(record["id"], record["input"]) for record in tips])
    return BuildReport(
        counts={name: len(split_rows) for name, split_rows in rows.items()},
        hand_total=hand_total,
        augmented_total=len(augmented),
        warnings=warnings,
        coverage=coverage,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the spoken-text rewrite dataset")
    parser.add_argument("--seeds", type=Path, default=SEEDS_DIR)
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    args = parser.parse_args()
    try:
        report = build(args.seeds, args.out)
    except (DatasetError, ValueError) as exc:
        for error in getattr(exc, "errors", [str(exc)]):
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    print(f"hand {report.hand_total} · augmented {report.augmented_total} · "
          + " · ".join(f"{name} {count}" for name, count in report.counts.items()))
    for line in report.coverage:
        print(f"  {line}")
    for warning in report.warnings:
        print(f"WARN {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 创建空种子文件并忽略构建产物**

创建空文件 `training/rewrite/seeds/clean_cases.jsonl`、`training/rewrite/seeds/suggestions.jsonl`。在 `.gitignore` 末尾追加一行：

```
training/rewrite/build/
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_rewrite_dataset.py`
Expected: 全部 PASS

- [ ] **Step 6: 用空种子跑一次 CLI**

Run: `.\.venv\Scripts\python.exe -m training.rewrite.build_dataset`
Expected: 退出码 0，输出 `hand 0 · augmented 0 · train 0 · valid 0 · test 0`，以及每个计划下限的 `WARN coverage ...`

- [ ] **Step 7: Commit**

```powershell
git add training/rewrite/build_dataset.py training/rewrite/seeds/clean_cases.jsonl training/rewrite/seeds/suggestions.jsonl tests/test_rewrite_dataset.py
git add -p .gitignore   # 只选 training/rewrite/build/ 这一行
git commit -m "Add rewrite dataset build, split and coverage report"
```

---

### Task 4: 第一批种子（风格校准）

**Files:**
- Modify: `training/rewrite/seeds/clean_cases.jsonl`
- Modify: `training/rewrite/seeds/suggestions.jsonl`

**Interfaces:**
- Consumes: 种子记录格式与校验规则（Task 1）；构建 CLI（Task 3）
- Produces: 约 160 条已通过校验的种子；交给用户抽查的 10 条

**写作规则**（本任务及 Task 5 共用）：

- id 前缀按主类别：`filler-`、`rep-`、`corr-`、`edit-del-`、`edit-rep-`、`edit-ins-`、`implicit-`、`fmt-`、`tr-`、`style-`、`combo-`、`neg-instr-`、`neg-cs-`、`neg-clean-`、`sug-`，后接四位序号。
- `raw` 模拟 SenseVoice 输出：有标点但不一定准确、数字已转阿拉伯数字、中英混说时英文词前后可能没有空格。
- `output` 只做必要修改：保留说话人的用词和语气词“吧、呢、哈”等句末语气（是否保留由校准决定），不润色。
- 场景在 10 个场景间轮换，每批每个场景至少 2 条。
- 指令样本的 `instr_position` 前置和后置约各半，句中约 10%。
- 翻译同时覆盖中译英、英译中；译文自然地道，不逐字翻。
- 任务 2 遵守 spec 第 4 节的 6 条规则，尤其不编造事实。

- [ ] **Step 1: 写任务 1 校准样本**

在 `clean_cases.jsonl` 写入 14 个类别各 10 条（共 140 条），一行一条 JSON。示例（第一行即 spec 中的例子）：

```json
{"id": "edit-del-0001", "categories": ["edit_delete", "implicit_reason"], "scene": "shopping", "raw": "我今天要买苹果，梨子，哦昨天买过苹果了，去掉苹果", "output": "我今天要买梨子。"}
{"id": "tr-0001", "categories": ["instr_translate"], "scene": "work_chat", "instr_position": "suffix", "raw": "明天下午开会，翻译成英文", "output": "There's a meeting tomorrow afternoon."}
{"id": "neg-instr-0001", "categories": ["neg_instruction_like"], "scene": "work_chat", "raw": "他让我把这段翻译成英文，我晚点弄", "output": "他让我把这段翻译成英文，我晚点弄。"}
```

- [ ] **Step 2: 写任务 2 校准样本**

在 `suggestions.jsonl` 写入 20 条，其中 2 条为短句（`[]` 或 1 项），覆盖至少 8 个场景、至少 3 条英文原文。

- [ ] **Step 3: 构建并修正**

Run: `.\.venv\Scripts\python.exe -m training.rewrite.build_dataset`
Expected: 退出码 0；若有 `ERROR`，逐条修正种子后重跑，直到无错误。`WARN coverage` 属预期（数量未达计划），`WARN near-duplicate` 需逐条改写到不再告警。

- [ ] **Step 4: 选 10 条交用户抽查（停在这里等反馈）**

从本批挑 10 条，覆盖这些取舍：口气词清理尺度（含句末“吧、呢”）、回头编辑（删除、替换、带理由各 1）、翻译（中译英、英译中各 1）、风格改写（正式、委婉各 1）、反例 1、自由建议 1。以表格形式在对话里展示“输入 → 输出”，询问需要调整的地方。**用户确认前不进入 Task 5**；用户的调整意见要回改到本批所有同类样本，并补进上方“写作规则”。

- [ ] **Step 5: Commit**

```powershell
git add training/rewrite/seeds/clean_cases.jsonl training/rewrite/seeds/suggestions.jsonl
git commit -m "Add calibration batch of rewrite seeds"
```

---

### Task 5: 其余种子分批写作

**Files:**
- Modify: `training/rewrite/seeds/clean_cases.jsonl`
- Modify: `training/rewrite/seeds/suggestions.jsonl`
- Modify: `HANDOFF.md`（最后一批完成后）

**Interfaces:**
- Consumes: Task 4 校准后的写作规则；构建 CLI
- Produces: 达到 spec 第 6 节计划规模、`WARN coverage` 全部消失的种子集

按下表顺序写，每批约 50 条（数字为写完后该类别的累计目标）：

| 批次 | 内容 | 累计目标 |
| --- | --- | --- |
| 1–4 | 即时纠正、回头删除/替换/补充、带理由修正 | edits ≥ 250 |
| 5–7 | 翻译（中译英、英译中，三种指令位置） | instr_translate ≥ 120 |
| 8–10 | 风格改写（正式、委婉、简洁、口语、礼貌等） | instr_style ≥ 140 |
| 11 | 指令与编辑组合 | instr_combo ≥ 40 |
| 12 | 口述格式 | spoken_format ≥ 60 |
| 13–14 | 反例三类 | negatives ≥ 150 |
| 15 | 口气词、重复的自然样本 | filler/repetition ≥ 100 |
| 16–23 | 自由建议 | suggestions ≥ 400，其中 0–1 项 ≥ 40 |

- [ ] **Step 1–N: 每一批执行同样四步**

1. 按写作规则追加约 50 条到对应种子文件。
2. Run: `.\.venv\Scripts\python.exe -m training.rewrite.build_dataset`，修正所有 `ERROR` 和 `near-duplicate` 告警。
3. 检查覆盖报告里的场景与语言分布，下一批补足偏少的场景。
4. 提交：

```powershell
git add training/rewrite/seeds/clean_cases.jsonl training/rewrite/seeds/suggestions.jsonl
git commit -m "Add rewrite seeds batch <n>: <内容>"
```

- [ ] **Final Step: 收尾**

1. Run: `.\.venv\Scripts\python.exe -m training.rewrite.build_dataset`
   Expected: 无 `ERROR`、无 `WARN`；手写 ≈ 1300，扩增 ≤ 手写 × 1.4。
2. Run: `$env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`
   Expected: 全部 PASS。
3. 在 `HANDOFF.md` 第 3 节表格后补一段：数据集位置 `training/rewrite/`、构建命令、spec 路径、尚未训练。
4. 提交：

```powershell
git add HANDOFF.md
git commit -m "Document rewrite dataset in handoff notes"
```
