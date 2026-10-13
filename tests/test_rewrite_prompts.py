from training.rewrite import prompts as training_prompts
from voxflow import rewrite_prompts


def test_app_and_training_share_the_same_prompts():
    assert training_prompts.CLEAN_SYSTEM_PROMPT is rewrite_prompts.CLEAN_SYSTEM_PROMPT
    assert training_prompts.SUGGEST_SYSTEM_PROMPT is rewrite_prompts.SUGGEST_SYSTEM_PROMPT
