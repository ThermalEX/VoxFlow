"""Publish the llama.cpp builds and the download catalog to the ThermalEX/voxflow-rewrite Hugging Face repository.

llama.cpp releases only on GitHub, where the China mirror does not help, so its Windows archives are re-hosted
(MIT license, copied alongside) under runtime/ and pinned by a tag. The catalog's sizes and SHA-256 values are
filled from the downloaded files, written to voxflow/assets/catalog.json and uploaded as catalog.json.

Usage (needs `gh` and `hf auth login`):
    .\\.venv\\Scripts\\python.exe packaging\\publish_runtime.py
"""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
REPO = "ThermalEX/voxflow-rewrite"
LLAMA_TAG = "b11596"
RUNTIME_TAG = f"llama-{LLAMA_TAG}"
ARCHIVES = (f"llama-{LLAMA_TAG}-bin-win-vulkan-x64.zip", f"llama-{LLAMA_TAG}-bin-win-cuda-12.4-x64.zip",
            "cudart-llama-bin-win-cuda-12.4-x64.zip")
CATALOG = ROOT / "voxflow" / "assets" / "catalog.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    api = HfApi()
    with tempfile.TemporaryDirectory(prefix="voxflow-runtime-") as folder:
        folder = Path(folder)
        for name in ARCHIVES:
            print(f"Downloading {name}", flush=True)
            subprocess.run(["gh", "release", "download", LLAMA_TAG, "-R", "ggml-org/llama.cpp", "-p", name,
                            "-D", str(folder)], check=True)
        facts = {name: ((folder / name).stat().st_size, sha256(folder / name)) for name in ARCHIVES}
        for name in ARCHIVES:
            print(f"Uploading {name} ({facts[name][0]} bytes)", flush=True)
            api.upload_file(path_or_fileobj=str(folder / name), path_in_repo=f"runtime/{name}", repo_id=REPO,
                            commit_message=f"Add llama.cpp {LLAMA_TAG} {name}")
    api.upload_file(path_or_fileobj=str(ROOT / "packaging" / "LICENSE-llama.cpp"),
                    path_in_repo="runtime/LICENSE-llama.cpp", repo_id=REPO,
                    commit_message="Add the llama.cpp license for the re-hosted builds")
    refs = {tag.name for tag in api.list_repo_refs(REPO).tags}
    if RUNTIME_TAG not in refs:
        api.create_tag(REPO, tag=RUNTIME_TAG, tag_message=f"llama.cpp {LLAMA_TAG} Windows builds")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    for item in catalog["items"]:
        for file in item["files"]:
            name = file["path"].rsplit("/", 1)[-1]
            if file["repo"] == REPO and name in facts:
                file["revision"] = RUNTIME_TAG
                file["size"], file["sha256"] = facts[name]
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    CATALOG.write_text(text, encoding="utf-8", newline="\n")
    api.upload_file(path_or_fileobj=text.encode("utf-8"), path_in_repo="catalog.json", repo_id=REPO,
                    commit_message="Update the download catalog")
    print("Catalog updated:", CATALOG, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
