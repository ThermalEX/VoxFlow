"""Find local GGUF rewrite models and describe them for the settings dropdown."""

import re
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QSettings

from .i18n import tr
from .rewriter import RewriteConfig

SEARCH_PATTERNS = ("training/rewrite/runs/*/gguf/*.gguf", "runtime/models/*.gguf",
                   "training/rewrite/runs/archive/*/gguf/*.gguf")
RUNS = Path("training/rewrite/runs")
ARCHIVE = RUNS / "archive"
KNOWN_QUANTS = ("q8_0", "q4_k_m", "bf16")
ORDER = {"q8_0": 0, "q4_k_m": 1, "other": 2, "bf16": 3}
QUANT_NAMES = {"q8_0": "Q8", "q4_k_m": "Q4", "bf16": "BF16"}
_FILE_VERSION = re.compile(r"-v(\d+)-")
_RUN_VERSION = re.compile(r"-v(\d+)$")


@dataclass(frozen=True)
class LocalModel:
    path: Path
    quant: str
    size: int
    run: str = ""  # training run folder, empty for downloaded or browsed files
    archived: bool = False  # the run was moved to runs/archive

    @property
    def version(self) -> int:
        """The VoxFlow model version from the run folder (qwen3.5-2b-v6) or the downloaded file
        (voxflow-rewrite-v6-q8_0.gguf); 0 for experiments and other files."""
        match = _RUN_VERSION.search(self.run) if self.run else _FILE_VERSION.search(self.path.name)
        return int(match.group(1)) if match else 0

    @property
    def name(self) -> str:
        if self.version:
            return f"VoxFlow v{self.version}"
        return self.run or self.path.stem


def quant_of(path: Path) -> str:
    suffix = path.stem.rsplit("-", 1)[-1].lower()
    return suffix if suffix in KNOWN_QUANTS else "other"


def _run_of(root: Path, path: Path) -> tuple[str, bool]:
    for folder, archived in ((ARCHIVE, True), (RUNS, False)):
        try:
            parts = path.relative_to(Path(root) / folder).parts
        except ValueError:
            continue
        if len(parts) == 3 and parts[1] == "gguf":
            return parts[0], archived
    return "", False


def local_model(root: Path, path: Path) -> LocalModel:
    run, archived = _run_of(root, path)
    return LocalModel(path, quant_of(path), path.stat().st_size, run, archived)


def discover_models(root: Path) -> list[LocalModel]:
    found = {path.resolve(): path for pattern in SEARCH_PATTERNS for path in Path(root).glob(pattern)
             if path.is_file()}
    models = [local_model(root, path) for path in found.values()]
    # Newest version first (current before archived, downloaded before the same version's training run),
    # then the recommended quantization; among unversioned archived runs the most recently written first.
    return sorted(models, key=lambda model: (model.archived, -model.version, ORDER[model.quant], bool(model.run),
                                             -model.path.stat().st_mtime if model.archived else 0, str(model.path)))


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


def describe(model: LocalModel, recommended: bool = False) -> str:
    """The dropdown label: name and version first, so every entry can be told apart."""
    quant = QUANT_NAMES.get(model.quant)
    parts = [model.name] + ([quant] if quant else []) + [format_size(model.size)]
    if recommended:
        parts.append(tr("model.note.recommended"))
    if model.archived:
        parts.append(tr("model.note.archived"))
    elif model.run:
        parts.append(tr("model.note.run"))
    return " · ".join(parts)
