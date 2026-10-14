# PyInstaller spec for VoxFlow; run through packaging/build.py, which adds models and runtime afterwards.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent
build_dir = root / "build" / "packaging"

datas = [(str(root / "voxflow" / "assets"), "voxflow/assets")]
datas += collect_data_files("sherpa_onnx")
binaries = collect_dynamic_libs("sherpa_onnx")

# Qt modules VoxFlow never imports; leaving them out keeps the install smaller.
excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
            "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization"]

a = Analysis([str(root / "packaging" / "launcher.py")], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=["PySide6.QtSvg"], excludes=excludes)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VoxFlow", console=False,
          icon=str(build_dir / "voxflow.ico"), version=str(build_dir / "version.txt"))
coll = COLLECT(exe, a.binaries, a.datas, name="VoxFlow")
