import io
import json
import urllib.error

import pytest

from voxflow import catalog
from voxflow.catalog import builtin_catalog, fetch_catalog, file_url, installed_ids, parse_catalog


class Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def item_by_id(items, item_id):
    return next(item for item in items if item.id == item_id)


def test_builtin_catalog_parses_and_has_required_speech_model():
    items = builtin_catalog()
    speech = item_by_id(items, "asr-sensevoice")
    assert speech.kind == "asr" and speech.required
    assert {item.id for item in items} >= {"asr-sensevoice", "llama-vulkan", "llama-cuda", "rewrite-v6-q8", "rewrite-v6-q4",
                                        "rewrite-v4-q8", "rewrite-v4-q4"}
    assert item_by_id(items, "llama-cuda").needs_nvidia
    assert item_by_id(items, "llama-vulkan").group == item_by_id(items, "llama-cuda").group == "llama"
    assert item_by_id(items, "rewrite-v6-q8").recommended and not item_by_id(items, "rewrite-v4-q8").recommended
    assert item_by_id(items, "rewrite-v6-q8").files[0].revision == "v6"
    assert set(speech.title) == {"en", "zh"}


def test_file_url_uses_mirror_host():
    q8 = item_by_id(builtin_catalog(), "rewrite-v4-q8").files[0]
    assert file_url(q8, "huggingface") == (
        "https://huggingface.co/ThermalEX/voxflow-rewrite/resolve/v4/voxflow-rewrite-q8_0.gguf")
    assert file_url(q8, "mirror").startswith("https://hf-mirror.com/ThermalEX/voxflow-rewrite/resolve/v4/")


@pytest.mark.parametrize("failure", ["network", "404", "garbage", "wrong shape"])
def test_bad_remote_catalog_falls_back_to_builtin(failure):
    def opener(request, timeout=None):
        if failure == "network":
            raise urllib.error.URLError("offline")
        if failure == "404":
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
        if failure == "garbage":
            return Response(b"<html>not json</html>")
        return Response(json.dumps({"items": [{"id": "broken"}]}).encode())

    items, online = fetch_catalog("huggingface", opener=opener)
    assert not online
    assert [item.id for item in items] == [item.id for item in builtin_catalog()]


def test_remote_catalog_replaces_builtin():
    data = json.loads(catalog.BUILTIN_PATH.read_text(encoding="utf-8"))
    new = dict(data["items"][-1], id="rewrite-v5-q8")
    seen = []

    def opener(request, timeout=None):
        seen.append(request.full_url)
        return Response(json.dumps({"version": 1, "items": [new]}).encode())

    items, online = fetch_catalog("mirror", opener=opener)
    assert online and [item.id for item in items][-1] == "rewrite-v5-q8"
    # the speech model and llama.cpp builds always stay available, with their built-in hashes
    assert {"asr-sensevoice", "llama-vulkan", "llama-cuda"} <= {item.id for item in items}
    assert "rewrite-v4-q8" not in {item.id for item in items}  # models follow the online list
    assert seen == ["https://hf-mirror.com/ThermalEX/voxflow-rewrite/resolve/main/catalog.json"]


def test_parse_rejects_unknown_kind():
    data = json.loads(catalog.BUILTIN_PATH.read_text(encoding="utf-8"))
    data["items"][0]["kind"] = "plugin"
    with pytest.raises(ValueError):
        parse_catalog(data)


def test_installed_ids_reads_record_and_existing_files(tmp_path):
    (tmp_path / "installed.json").write_text(json.dumps({"rewrite-v4-q4": ["abc"]}), encoding="utf-8")
    model = tmp_path / "runtime/models/voxflow-rewrite-v4-q4_k_m.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"")
    server = tmp_path / "runtime" / "llama.cpp" / "ggml-vulkan.dll"  # each llama.cpp build has its own backend DLL
    server.parent.mkdir(parents=True)
    server.write_bytes(b"")
    ids = installed_ids(builtin_catalog(), tmp_path)
    assert {"rewrite-v4-q4", "llama-vulkan"} <= ids
    assert "rewrite-v4-q8" not in ids


def test_a_recorded_variant_hides_its_sibling(tmp_path):
    (tmp_path / "installed.json").write_text(json.dumps({"llama-cuda": ["abc"]}), encoding="utf-8")
    server = tmp_path / "runtime" / "llama.cpp" / "ggml-cuda.dll"
    server.parent.mkdir(parents=True)
    server.write_bytes(b"")
    ids = installed_ids(builtin_catalog(), tmp_path)
    assert "llama-cuda" in ids and "llama-vulkan" not in ids


def test_builtin_catalog_is_complete():
    import re

    for item in builtin_catalog():
        for file in item.files:
            assert file.size > 0, (item.id, file.path)
            assert re.fullmatch(r"[0-9a-f]{64}", file.sha256), (item.id, file.path)
            assert "//" not in file_url(file, "huggingface").split("://", 1)[1]


@pytest.mark.parametrize("dest", ["/etc/passwd", "C:/Windows/x.dll", "../outside.gguf", "runtime/../../x", "",
                                  "runtime", "voxflow/evil.py"])
def test_parse_rejects_paths_outside_the_download_folders(dest):
    data = json.loads(catalog.BUILTIN_PATH.read_text(encoding="utf-8"))
    data["items"][-1]["files"][0]["dest"] = dest
    with pytest.raises(ValueError):
        parse_catalog(data)


def test_remote_catalog_cannot_change_runtime_or_speech_files():
    data = json.loads(catalog.BUILTIN_PATH.read_text(encoding="utf-8"))
    remote = {"items": []}
    for entry in data["items"]:
        entry = json.loads(json.dumps(entry))
        if entry["id"] == "llama-vulkan":
            entry["files"][0]["sha256"] = "f" * 64  # a mirror trying to swap the executable
        remote["items"].append(entry)
    new_runtime = json.loads(json.dumps(next(e for e in data["items"] if e["id"] == "llama-vulkan")))
    new_runtime["id"] = "llama-evil"
    remote["items"].append(new_runtime)
    new_model = json.loads(json.dumps(data["items"][-1]))
    new_model["id"] = "rewrite-v5-q8"
    remote["items"].append(new_model)

    def opener(request, timeout=None):
        return Response(json.dumps(remote).encode())

    items, online = fetch_catalog("mirror", opener=opener)
    by_id = {item.id: item for item in items}
    assert online
    assert by_id["llama-vulkan"] == item_by_id(builtin_catalog(), "llama-vulkan")
    assert "llama-evil" not in by_id
    assert "rewrite-v5-q8" in by_id


def test_recorded_item_whose_files_were_deleted_is_not_installed(tmp_path):
    (tmp_path / "installed.json").write_text(json.dumps({"rewrite-v4-q4": {"sha256": ["x"]}}), encoding="utf-8")
    assert "rewrite-v4-q4" not in installed_ids(builtin_catalog(), tmp_path)


def test_unrecorded_item_needs_every_file(tmp_path):
    speech = item_by_id(builtin_catalog(), "asr-sensevoice")
    check = tmp_path / speech.check
    check.parent.mkdir(parents=True)
    check.write_bytes(b"")
    assert "asr-sensevoice" not in installed_ids(builtin_catalog(), tmp_path)
    for file in speech.files:
        (tmp_path / file.dest).write_bytes(b"")
    assert "asr-sensevoice" in installed_ids(builtin_catalog(), tmp_path)
