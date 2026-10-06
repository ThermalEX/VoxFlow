"""Download the pinned local SenseVoiceSmall ONNX model."""

import hashlib
import shutil
import tarfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{NAME}.tar.bz2"
SHA256 = "7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e"


def main() -> None:
    model_root = ROOT / "models"
    model_root.mkdir(parents=True, exist_ok=True)
    model_dir = model_root / NAME
    if (model_dir / "model.int8.onnx").is_file() and (model_dir / "tokens.txt").is_file():
        print(f"Model ready: {model_dir}")
        return

    archive = model_root / f"{NAME}.tar.bz2"
    if not archive.is_file():
        partial = archive.with_suffix(archive.suffix + ".part")
        print(f"Downloading {URL}")
        with urllib.request.urlopen(URL, timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        partial.replace(archive)

    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != SHA256:
        raise RuntimeError(f"Model archive SHA256 mismatch: {digest}")
    with tarfile.open(archive, "r:bz2") as package:
        package.extractall(model_root, filter="data")
    if not (model_dir / "model.int8.onnx").is_file() or not (model_dir / "tokens.txt").is_file():
        raise RuntimeError("Model archive did not contain the expected files")
    print(f"Model ready: {model_dir}")


if __name__ == "__main__":
    main()
