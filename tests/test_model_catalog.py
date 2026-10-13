from pathlib import Path

from voxflow import i18n
from voxflow.model_catalog import LocalModel, describe, discover_models, format_size


def make_gguf(path: Path, size: int = 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


def label(model: LocalModel) -> str:
    key, values = describe(model)
    return i18n.tr(key, **values)


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


def test_labels_explain_size_and_purpose():
    q8 = LocalModel(Path("voxflow-rewrite-q8_0.gguf"), "q8_0", 2_076_674_496)
    q4 = LocalModel(Path("voxflow-rewrite-q4_k_m.gguf"), "q4_k_m", 1_312_164_288)
    other = LocalModel(Path("my-model.gguf"), "other", 512_000_000)
    assert label(q8) == "Q8 · 1.9 GB · Recommended"
    assert label(other) == "my-model · 488 MB"
    i18n.set_language("zh")
    try:
        assert label(q4) == "Q4 · 1.2 GB · 更省显存"
    finally:
        i18n.set_language("en")
