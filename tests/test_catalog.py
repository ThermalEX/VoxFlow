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
    assert {item.id for item in items} >= {"asr-sensevoice", "llama-vulkan", "llama-cuda", "rewrite-v4-q8", "rewrite-v4-q4"}
    assert item_by_id(items, "llama-cuda").needs_nvidia
    assert item_by_id(items, "llama-vulkan").group == item_by_id(items, "llama-cuda").group == "llama"
    assert item_by_id(items, "rewrite-v4-q8").recommended
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
    assert online and [item.id for item in items] == ["rewrite-v5-q8"]
    assert seen == ["https://hf-mirror.com/ThermalEX/voxflow-rewrite/resolve/main/catalog.json"]


def test_parse_rejects_unknown_kind():
    data = json.loads(catalog.BUILTIN_PATH.read_text(encoding="utf-8"))
    data["items"][0]["kind"] = "plugin"
    with pytest.raises(ValueError):
        parse_catalog(data)


def test_installed_ids_reads_record_and_existing_files(tmp_path):
    (tmp_path / "installed.json").write_text(json.dumps({"rewrite-v4-q4": ["abc"]}), encoding="utf-8")
    server = tmp_path / "runtime" / "llama.cpp" / "ggml-vulkan.dll"  # each llama.cpp build has its own backend DLL
    server.parent.mkdir(parents=True)
    server.write_bytes(b"")
    ids = installed_ids(builtin_catalog(), tmp_path)
    assert {"rewrite-v4-q4", "llama-vulkan"} <= ids
    assert "rewrite-v4-q8" not in ids


def test_a_recorded_variant_hides_its_sibling(tmp_path):
    (tmp_path / "installed.json").write_text(json.dumps({"llama-cuda": ["abc"]}), encoding="utf-8")
    server = tmp_path / "runtime" / "llama.cpp" / "llama-server.exe"
    server.parent.mkdir(parents=True)
    server.write_bytes(b"")
    ids = installed_ids(builtin_catalog(), tmp_path)
    assert "llama-cuda" in ids and "llama-vulkan" not in ids
