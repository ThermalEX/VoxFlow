"""Find local GGUF rewrite models and describe them for the settings dropdown."""

from dataclasses import dataclass
from pathlib import Path

SEARCH_PATTERNS = ("training/rewrite/runs/*/gguf/*.gguf", "runtime/models/*.gguf")
KNOWN_QUANTS = ("q8_0", "q4_k_m", "bf16")
ORDER = {"q8_0": 0, "q4_k_m": 1, "other": 2, "bf16": 3}


@dataclass(frozen=True)
class LocalModel:
    path: Path
    quant: str
    size: int


def quant_of(path: Path) -> str:
    suffix = path.stem.rsplit("-", 1)[-1].lower()
    return suffix if suffix in KNOWN_QUANTS else "other"


def discover_models(root: Path) -> list[LocalModel]:
    found = {path.resolve(): path for pattern in SEARCH_PATTERNS for path in Path(root).glob(pattern)
             if path.is_file()}
    models = [LocalModel(path, quant_of(path), path.stat().st_size) for path in found.values()]
    return sorted(models, key=lambda model: (ORDER[model.quant], str(model.path)))


def format_size(size: int) -> str:
    gigabytes = size / 2**30
    return f"{gigabytes:.1f} GB" if gigabytes >= 1 else f"{size / 2**20:.0f} MB"


def describe(model: LocalModel) -> tuple[str, dict]:
    """The dropdown label as an i18n key and its values."""
    size = format_size(model.size)
    if model.quant == "q8_0":
        return "model.choice.q8", {"size": size}
    if model.quant == "q4_k_m":
        return "model.choice.q4", {"size": size}
    if model.quant == "bf16":
        return "model.choice.bf16", {"size": size}
    return "model.choice.other", {"name": model.path.stem, "size": size}
