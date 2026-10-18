"""Where VoxFlow lives: the program files (APP_ROOT) and the downloaded models and runtime (DATA_ROOT).

Run from source, both are the repository. Installed, the program sits in its install folder and downloads go to
%LOCALAPPDATA%\VoxFlow, so reinstalling or upgrading keeps them.
"""

import os
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def data_root() -> Path:
    if not getattr(sys, "frozen", False):
        return app_root()
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "VoxFlow"
    root.mkdir(parents=True, exist_ok=True)
    return root


APP_ROOT = app_root()
DATA_ROOT = data_root()
