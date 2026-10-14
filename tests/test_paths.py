import sys
from pathlib import Path

from voxflow import paths


def test_source_checkout_uses_the_repository_root():
    assert paths.app_root() == Path(paths.__file__).resolve().parents[1]
    assert (paths.app_root() / "pyproject.toml").is_file()


def test_installed_app_uses_the_folder_of_the_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "VoxFlow.exe"))
    assert paths.app_root() == tmp_path
