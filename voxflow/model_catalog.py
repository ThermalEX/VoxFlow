"""Find local GGUF rewrite models and describe them for the settings dropdown."""

from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QSettings

from .rewriter import RewriteConfig

SEARCH_PATTERNS = ("training/rewrite/runs/*/gguf/*.gguf", "runtime/models/*.gguf",
                   "training/rewrite/runs/archive/*/gguf/*.gguf")
ARCHIVE = Path("training/rewrite/runs/archive")
KNOWN_QUANTS = ("q8_0", "q4_k_m", "bf16")
ORDER = {"q8_0": 0, "q4_k_m": 1, "other": 2, "bf16": 3}


@dataclass(frozen=True)
class LocalModel:
    path: Path
    quant: str
    size: int
    run: str = ""  # name of an archived training run, empty for current models


def quant_of(path: Path) -> str:
    suffix = path.stem.rsplit("-", 1)[-1].lower()
    return suffix if suffix in KNOWN_QUANTS else "other"


def _archived_run(root: Path, path: Path) -> str:
    try:
        return path.relative_to(Path(root) / ARCHIVE).parts[0]
    except ValueError:
        return ""


def discover_models(root: Path) -> list[LocalModel]:
    found = {path.resolve(): path for pattern in SEARCH_PATTERNS for path in Path(root).glob(pattern)
             if path.is_file()}
    models = [LocalModel(path, quant_of(path), path.stat().st_size, _archived_run(root, path))
              for path in found.values()]
    return sorted(models, key=lambda model: (bool(model.run), ORDER[model.quant], str(model.path)))


def replace_missing_model(settings: QSettings, root: Path) -> Path | None:
    """Switch to the best model found when the saved file is gone (say, while its run is being retrained)."""
    config = RewriteConfig.from_settings(settings)
    saved = Path(config.model_path).expanduser()
    if (saved if saved.is_absolute() else Path(root) / saved).is_file():
        return None
    models = discover_models(root)
    if not models:
        return None
    chosen = models[0].path
    try:
        model_path = chosen.relative_to(root).as_posix()
    except ValueError:
        model_path = str(chosen)
    replace(config, model_path=model_path).save(settings)
    return chosen


def format_size(size: int) -> str:
    gigabytes = size / 2**30
    return f"{gigabytes:.1f} GB" if gigabytes >= 1 else f"{size / 2**20:.0f} MB"


def describe(model: LocalModel) -> tuple[str, dict]:
    """The dropdown label as an i18n key and its values."""
    size = format_size(model.size)
    if model.run:
        quant = {"q8_0": "Q8", "q4_k_m": "Q4", "bf16": "BF16"}.get(model.quant, model.path.stem)
        return "model.choice.archived", {"quant": quant, "size": size, "run": model.run}
    if model.quant == "q8_0":
        return "model.choice.q8", {"size": size}
    if model.quant == "q4_k_m":
        return "model.choice.q4", {"size": size}
    if model.quant == "bf16":
        return "model.choice.bf16", {"size": size}
    return "model.choice.other", {"name": model.path.stem, "size": size}
