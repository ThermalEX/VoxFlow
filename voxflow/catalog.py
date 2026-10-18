"""What VoxFlow can download: speech model, llama.cpp builds and rewrite models, listed in catalog.json.

The list lives in the ThermalEX/voxflow-rewrite repository on Hugging Face so new models show up without a new
release; a copy ships with the app and is used whenever the online list cannot be read.
"""

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SOURCES = ("auto", "huggingface", "mirror")
HOSTS = {"huggingface": "huggingface.co", "mirror": "hf-mirror.com"}
CATALOG_REPO = "ThermalEX/voxflow-rewrite"
KINDS = ("asr", "runtime", "rewrite")
BUILTIN_PATH = Path(__file__).resolve().parent / "assets" / "catalog.json"
INSTALLED_FILE = "installed.json"


@dataclass(frozen=True)
class CatalogFile:
    repo: str
    revision: str
    path: str
    size: int
    sha256: str
    dest: str  # relative to the data folder: the file itself, or the folder a zip unpacks into
    extract: bool = False


@dataclass(frozen=True)
class CatalogItem:
    id: str
    kind: str
    group: str  # items sharing a group replace each other, e.g. the two llama.cpp builds
    required: bool
    recommended: bool
    needs_nvidia: bool
    title: dict
    desc: dict
    files: tuple
    check: str  # relative path whose presence means the item is installed

    @property
    def size(self) -> int:
        return sum(file.size for file in self.files)


def _text(data: dict, key: str) -> dict:
    value = data[key]
    if not isinstance(value, dict) or not all(isinstance(value.get(lang), str) for lang in ("en", "zh")):
        raise ValueError(f"{key} needs en and zh text")
    return {"en": value["en"], "zh": value["zh"]}


def _file(data: dict) -> CatalogFile:
    return CatalogFile(repo=str(data["repo"]), revision=str(data["revision"]), path=str(data["path"]),
                       size=int(data["size"]), sha256=str(data["sha256"]).lower(), dest=str(data["dest"]),
                       extract=bool(data.get("extract", False)))


def parse_catalog(data: dict) -> list[CatalogItem]:
    try:
        items = []
        for entry in data["items"]:
            kind = str(entry["kind"])
            if kind not in KINDS:
                raise ValueError(f"unknown kind {kind}")
            files = tuple(_file(file) for file in entry["files"])
            if not files:
                raise ValueError("an item needs files")
            items.append(CatalogItem(
                id=str(entry["id"]), kind=kind, group=str(entry.get("group", "")),
                required=bool(entry.get("required", False)), recommended=bool(entry.get("recommended", False)),
                needs_nvidia=bool(entry.get("needs_nvidia", False)), title=_text(entry, "title"),
                desc=_text(entry, "desc"), files=files, check=str(entry["check"])))
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"malformed catalog: {exc}") from exc
    if not items:
        raise ValueError("empty catalog")
    return items


def builtin_catalog() -> list[CatalogItem]:
    return parse_catalog(json.loads(BUILTIN_PATH.read_text(encoding="utf-8")))


def hf_url(repo: str, revision: str, path: str, source: str) -> str:
    host = HOSTS["mirror" if source == "mirror" else "huggingface"]
    return f"https://{host}/{repo}/resolve/{revision}/{path}"


def file_url(file: CatalogFile, source: str) -> str:
    return hf_url(file.repo, file.revision, file.path, source)


def fetch_catalog(source: str, opener=urllib.request.urlopen, timeout: float = 10) -> tuple[list[CatalogItem], bool]:
    """The online list, or the built-in one (and False) when it cannot be read."""
    url = hf_url(CATALOG_REPO, "main", "catalog.json", source)
    try:
        with opener(urllib.request.Request(url, headers={"User-Agent": "VoxFlow"}), timeout=timeout) as response:
            return parse_catalog(json.loads(response.read().decode("utf-8"))), True
    except Exception:  # offline, HTTP errors, bad JSON or a malformed list: fall back, never show an empty list
        return builtin_catalog(), False


def read_installed(root: Path) -> dict:
    try:
        data = json.loads((Path(root) / INSTALLED_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def installed_ids(items: list[CatalogItem], root: Path) -> set[str]:
    """Items recorded by the downloader, plus items whose files are already there (e.g. a source checkout)."""
    recorded = read_installed(root)
    recorded_groups = {item.group for item in items if item.id in recorded and item.group}
    found = set()
    for item in items:
        if item.id in recorded:
            found.add(item.id)
        elif item.group not in recorded_groups and (Path(root) / item.check).exists():
            found.add(item.id)
    return found
