"""Build the Windows installer with the app only: PyInstaller -> Inno Setup.

The speech model, llama.cpp and the rewrite models are downloaded inside the app (Settings › Smart editing or the
first-run tutorial), so they are not bundled.

Usage (from the repository root):
    .\\.venv\\Scripts\\python.exe packaging\\build.py [--skip-installer]

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


PACKAGING = ROOT / "packaging"
BUILD = ROOT / "build" / "packaging"
DIST = ROOT / "dist"
APP = DIST / "VoxFlow"
ISCC = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


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


def copy_notices() -> None:
    shutil.copy2(PACKAGING / "THIRD_PARTY.txt", APP / "THIRD_PARTY.txt")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the VoxFlow installer")
    parser.add_argument("--skip-installer", action="store_true", help="only build dist\\VoxFlow")
    args = parser.parse_args()

    text = version()
    print(f"VoxFlow {text}")
    BUILD.mkdir(parents=True, exist_ok=True)
    write_icon()
    write_version_resource(text)
    if APP.exists():
        shutil.rmtree(APP)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(DIST),
                    "--workpath", str(BUILD / "pyinstaller"), str(PACKAGING / "voxflow.spec")], check=True, cwd=ROOT)
    copy_notices()
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
