"""Where VoxFlow finds its models and runtime: the repository when run from source, the install folder when packaged."""

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


APP_ROOT = app_root()
