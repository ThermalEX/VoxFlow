"""Build the Windows installer: PyInstaller app + speech model + llama-server + rewrite model -> Inno Setup.

Usage (from the repository root):
    .\\.venv\\Scripts\\python.exe packaging\\build.py [--model path\\to\\model.gguf] [--skip-installer]

Output: dist\\VoxFlow\\ (portable folder) and dist\\VoxFlow-Setup-<version>.exe.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voxflow.__main__ import MODEL_NAME  # noqa: E402
from voxflow.model_catalog import discover_models  # noqa: E402

PACKAGING = ROOT / "packaging"
BUILD = ROOT / "build" / "packaging"
DIST = ROOT / "dist"
APP = DIST / "VoxFlow"
ISCC = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"
ASR_FILES = ("model.int8.onnx", "tokens.txt", "LICENSE", "README.md")
# llama-server needs its own -impl DLL, the ggml backends, CUDA runtime and OpenMP; the other tools are left out.
SERVER_EXES = {"llama-server.exe"}


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def default_model() -> Path:
    models = [model for model in discover_models(ROOT) if model.quant == "q8_0" and "runtime" not in model.path.parts]
    if not models:
        raise SystemExit("No Q8 rewrite model found; pass --model path\\to\\model.gguf")
    return models[0].path


def write_icon() -> None:
    from PySide6.QtWidgets import QApplication

    from voxflow.ui_icons import app_icon

    app = QApplication.instance() or QApplication([])
    pixmap = app_icon().pixmap(256, 256)
    if not pixmap.save(str(BUILD / "voxflow.ico"), "ICO"):
        raise SystemExit("Could not write the application icon")
    del app


def write_version_resource(text: str) -> None:
    numbers = tuple(int(part) for part in (text.split(".") + ["0", "0", "0"])[:4])
    (BUILD / "version.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}),
  kids=[StringFileInfo([StringTable('080404b0', [
    StringStruct('CompanyName', 'ThermalEX'),
    StringStruct('FileDescription', 'VoxFlow 语音输入'),
    StringStruct('FileVersion', '{text}'),
    StringStruct('ProductName', 'VoxFlow'),
    StringStruct('ProductVersion', '{text}')])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])])
""", encoding="utf-8")


def copy_runtime(model: Path) -> None:
    asr_source = ROOT / "models" / MODEL_NAME
    asr_target = APP / "models" / MODEL_NAME
    asr_target.mkdir(parents=True, exist_ok=True)
    for name in ASR_FILES:
        shutil.copy2(asr_source / name, asr_target / name)

    server_source = ROOT / "runtime" / "llama.cpp"
    server_target = APP / "runtime" / "llama.cpp"
    server_target.mkdir(parents=True, exist_ok=True)
    for path in server_source.iterdir():
        name = path.name
        if path.suffix == ".exe" and name not in SERVER_EXES:
            continue
        if name.endswith("-impl.dll") and name != "llama-server-impl.dll":
            continue
        shutil.copy2(path, server_target / name)
    shutil.copy2(PACKAGING / "LICENSE-llama.cpp", server_target / "LICENSE-llama.cpp")

    models_target = APP / "runtime" / "models"
    models_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model, models_target / "voxflow-rewrite-q8_0.gguf")
    shutil.copy2(PACKAGING / "THIRD_PARTY.txt", APP / "THIRD_PARTY.txt")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the VoxFlow installer")
    parser.add_argument("--model", type=Path, help="rewrite model GGUF to bundle (default: newest Q8)")
    parser.add_argument("--skip-installer", action="store_true", help="only build dist\\VoxFlow")
    args = parser.parse_args()

    model = (args.model or default_model()).resolve()
    text = version()
    print(f"VoxFlow {text} · rewrite model {model}")
    BUILD.mkdir(parents=True, exist_ok=True)
    write_icon()
    write_version_resource(text)
    if APP.exists():
        shutil.rmtree(APP)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(DIST),
                    "--workpath", str(BUILD / "pyinstaller"), str(PACKAGING / "voxflow.spec")], check=True, cwd=ROOT)
    copy_runtime(model)
    if args.skip_installer:
        return 0
    if not ISCC.is_file():
        raise SystemExit(f"Inno Setup not found at {ISCC}; install it with: winget install JRSoftware.InnoSetup")
    subprocess.run([str(ISCC), f"/DAppVersion={text}", f"/DIconFile={BUILD / 'voxflow.ico'}",
                    str(PACKAGING / "voxflow.iss")], check=True, cwd=ROOT)
    print(f"Installer: {DIST / f'VoxFlow-Setup-{text}.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
