import hashlib
import io
import tarfile

from scripts import download_model


def test_download_verifies_archive_and_extracts_expected_files(tmp_path, monkeypatch):
    name = "example-model"
    archive = tmp_path / "source.tar.bz2"
    with tarfile.open(archive, "w:bz2") as package:
        for filename, content in (("model.int8.onnx", b"model"), ("tokens.txt", b"tokens")):
            data = io.BytesIO(content)
            info = tarfile.TarInfo(f"{name}/{filename}")
            info.size = len(content)
            package.addfile(info, data)

    monkeypatch.setattr(download_model, "ROOT", tmp_path / "work")
    monkeypatch.setattr(download_model, "NAME", name)
    monkeypatch.setattr(download_model, "URL", archive.as_uri())
    monkeypatch.setattr(download_model, "SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    download_model.main()
    assert (tmp_path / "work" / "models" / name / "model.int8.onnx").read_bytes() == b"model"
    assert (tmp_path / "work" / "models" / name / "tokens.txt").read_bytes() == b"tokens"
