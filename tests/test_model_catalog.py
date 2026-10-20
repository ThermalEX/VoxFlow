from pathlib import Path

from voxflow import i18n
from voxflow.model_catalog import LocalModel, describe, discover_models, format_size


def make_gguf(path: Path, size: int = 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


def label(model: LocalModel, recommended: bool = False) -> str:
    return describe(model, recommended)


def test_discovers_runs_and_runtime_models_recommended_first(tmp_path):
    gguf = tmp_path / "training/rewrite/runs/qwen3.5-2b/gguf"
    make_gguf(gguf / "voxflow-rewrite-bf16.gguf")
    make_gguf(gguf / "voxflow-rewrite-q4_k_m.gguf")
    make_gguf(gguf / "voxflow-rewrite-q8_0.gguf")
    make_gguf(tmp_path / "runtime/models/other.gguf")
    make_gguf(gguf / "merged" / "ignored.txt")
    models = discover_models(tmp_path)
    assert [model.quant for model in models] == ["q8_0", "q4_k_m", "other", "bf16"]
    assert models[0].path == gguf / "voxflow-rewrite-q8_0.gguf"
    assert discover_models(tmp_path / "empty") == []


def test_sizes_read_like_a_file_manager():
    assert format_size(2_076_674_496) == "1.9 GB"
    assert format_size(512_000_000) == "488 MB"


def test_labels_start_with_the_model_name_and_version():
    downloaded = LocalModel(Path("runtime/models/voxflow-rewrite-v6-q8_0.gguf"), "q8_0", 2_076_674_496)
    run = LocalModel(Path("runs/qwen3.5-2b-v6/gguf/voxflow-rewrite-q4_k_m.gguf"), "q4_k_m", 1_312_164_288,
                     run="qwen3.5-2b-v6")
    experiment = LocalModel(Path("runs/gemma-4-e2b-r2/gguf/voxflow-rewrite-q4_k_m.gguf"), "q4_k_m", 3_427_880_192,
                            run="gemma-4-e2b-r2")
    old = LocalModel(Path("archive/qwen3.5-2b-v1/gguf/voxflow-rewrite-bf16.gguf"), "bf16", 3_897_387_456,
                     run="qwen3.5-2b-v1", archived=True)
    other = LocalModel(Path("my-model.gguf"), "other", 512_000_000)
    assert label(downloaded, recommended=True) == "VoxFlow v6 · Q8 · 1.9 GB · Recommended"
    assert label(run) == "VoxFlow v6 · Q4 · 1.2 GB · training run"
    assert label(experiment) == "gemma-4-e2b-r2 · Q4 · 3.2 GB · training run"
    assert label(old) == "VoxFlow v1 · BF16 · 3.6 GB · archived"
    assert label(other) == "my-model · 488 MB"
    i18n.set_language("zh")
    try:
        assert label(downloaded, recommended=True) == "VoxFlow v6 · Q8 · 1.9 GB · 推荐"
        assert label(old) == "VoxFlow v1 · BF16 · 3.6 GB · 旧版"
    finally:
        i18n.set_language("en")


def test_the_newest_version_comes_first_and_a_download_before_its_training_run(tmp_path):
    runs = tmp_path / "training/rewrite/runs"
    v6_run = make_gguf(runs / "qwen3.5-2b-v6/gguf/voxflow-rewrite-q8_0.gguf")
    v6_q4 = make_gguf(runs / "qwen3.5-2b-v6/gguf/voxflow-rewrite-q4_k_m.gguf")
    gemma = make_gguf(runs / "gemma-4-e2b/gguf/voxflow-rewrite-q8_0.gguf")
    v4 = make_gguf(tmp_path / "runtime/models/voxflow-rewrite-v4-q8_0.gguf")
    v6 = make_gguf(tmp_path / "runtime/models/voxflow-rewrite-v6-q8_0.gguf")
    v3 = make_gguf(runs / "archive/qwen3.5-2b-v3/gguf/voxflow-rewrite-q8_0.gguf")
    models = discover_models(tmp_path)
    assert [model.path for model in models] == [v6, v6_run, v6_q4, v4, gemma, v3]
    assert [model.version for model in models] == [6, 6, 6, 4, 0, 3]


def test_archived_runs_are_listed_after_current_ones_with_their_name(tmp_path):
    make_gguf(tmp_path / "training/rewrite/runs/archive/qwen3.5-2b-v1/gguf/voxflow-rewrite-q8_0.gguf")
    current = make_gguf(tmp_path / "training/rewrite/runs/qwen3.5-2b/gguf/voxflow-rewrite-q4_k_m.gguf")
    models = discover_models(tmp_path)
    assert models[0].path == current and models[0].run == "qwen3.5-2b" and not models[0].archived
    assert models[1].run == "qwen3.5-2b-v1" and models[1].archived
    assert label(models[1]) == f"VoxFlow v1 · Q8 · {format_size(64)} · archived"


def test_a_missing_saved_model_is_replaced_by_the_best_one_found(tmp_path):
    from PySide6.QtCore import QSettings
    from voxflow.model_catalog import replace_missing_model
    from voxflow.rewriter import RewriteConfig

    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    RewriteConfig(model_path="training/rewrite/runs/qwen3.5-2b/gguf/voxflow-rewrite-q8_0.gguf").save(settings)
    assert replace_missing_model(settings, tmp_path) is None  # nothing to switch to
    archived = make_gguf(tmp_path / "training/rewrite/runs/archive/v1/gguf/voxflow-rewrite-q8_0.gguf")
    assert replace_missing_model(settings, tmp_path) == archived
    assert RewriteConfig.from_settings(settings).model_path == "training/rewrite/runs/archive/v1/gguf/voxflow-rewrite-q8_0.gguf"
    assert replace_missing_model(settings, tmp_path) is None  # already usable


def test_the_newest_archived_run_comes_first(tmp_path):
    import os
    old = make_gguf(tmp_path / "training/rewrite/runs/archive/run-b/gguf/voxflow-rewrite-q8_0.gguf")
    new = make_gguf(tmp_path / "training/rewrite/runs/archive/run-a/gguf/voxflow-rewrite-q8_0.gguf")
    os.utime(old, (1_000_000, 1_000_000))
    assert [model.path for model in discover_models(tmp_path)] == [new, old]
