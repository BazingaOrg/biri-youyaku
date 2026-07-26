import pytest

from biri_youyaku.modules.storage import distill


def _patch_storage_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(distill.settings, "distill_storage_dir", tmp_path)


def test_save_corpus_replaces_complete_file_atomically(monkeypatch, tmp_path):
    _patch_storage_dir(monkeypatch, tmp_path)
    distill.save_corpus(1, "old corpus")

    distill.save_corpus(1, "new corpus")

    assert distill.read_corpus(1) == "new corpus"


def test_save_corpus_keeps_old_file_and_cleans_temp_after_partial_write_failure(
    monkeypatch, tmp_path
):
    _patch_storage_dir(monkeypatch, tmp_path)
    distill.save_corpus(1, "old corpus")
    path = distill.corpus_path(1)
    original_named_temporary_file = distill.tempfile.NamedTemporaryFile

    class PartialWriteFile:
        def __init__(self, file):
            self.file = file

        def write(self, content):
            self.file.write(content[:3])
            raise OSError("simulated partial write")

        def __getattr__(self, name):
            return getattr(self.file, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

    def partial_named_temporary_file(*args, **kwargs):
        return PartialWriteFile(original_named_temporary_file(*args, **kwargs))

    monkeypatch.setattr(distill.tempfile, "NamedTemporaryFile", partial_named_temporary_file)

    with pytest.raises(OSError, match="simulated partial write"):
        distill._atomic_write_text(path, "new corpus")

    assert path.read_text(encoding="utf-8") == "old corpus"
    assert not list(path.parent.glob(f".{path.name}.*"))
