"""Phase 4c — on-disk StackCache tests.

Cache contract:
- ``store`` + ``lookup`` round-trip preserves the full manifest.
- ``lookup`` returns None when the cached manifest's ``output_dir``
  is gone (cache is invalidated, but the entry isn't deleted —
  reviving the dir revives the cache).
- ``lookup`` returns None on missing fingerprint or corrupt JSON.
- ``invalidate`` removes the entry.
- ``clear`` removes all entries.
- A second ``StackCache`` instance pointing at the same root sees
  entries the first instance stored.
"""

from __future__ import annotations

from pathlib import Path

from fmriflow.preproc.manifest import PreprocManifest, now_iso
from fmriflow.preproc.stack import StepRecord
from fmriflow.preproc.stack_cache import StackCache


def _make_manifest(output_dir: Path) -> PreprocManifest:
    return PreprocManifest(
        subject="sub01",
        dataset="study1",
        sessions=["ses01"],
        runs=[],
        backend="identity",
        backend_version="0.1.0",
        parameters={},
        space="native",
        additional_steps=[StepRecord(name="smooth", params={"fwhm": 6})],
        output_dir=str(output_dir),
        created=now_iso(),
    )


class TestRoundTrip:
    def test_store_then_lookup(self, tmp_path):
        cache = StackCache(root_dir=tmp_path / "cache")
        out_dir = tmp_path / "stage_outputs"
        out_dir.mkdir()
        manifest = _make_manifest(out_dir)

        cache.store("abc12345", manifest)
        loaded = cache.lookup("abc12345")

        assert loaded is not None
        assert loaded.subject == "sub01"
        assert loaded.output_dir == str(out_dir)
        assert len(loaded.additional_steps) == 1
        assert loaded.additional_steps[0].name == "smooth"
        assert loaded.additional_steps[0].params == {"fwhm": 6}

    def test_creates_root_dir_on_store(self, tmp_path):
        # ``root_dir`` doesn't exist yet.
        cache = StackCache(root_dir=tmp_path / "deeply" / "nested")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        cache.store("abc", _make_manifest(out_dir))
        assert (tmp_path / "deeply" / "nested" / "abc.json").is_file()


class TestInvalidation:
    def test_missing_output_dir_returns_none(self, tmp_path):
        cache = StackCache(root_dir=tmp_path / "cache")
        out_dir = tmp_path / "removed_outputs"
        out_dir.mkdir()
        cache.store("abc", _make_manifest(out_dir))

        # Delete the output dir; cache should now miss.
        out_dir.rmdir()
        assert cache.lookup("abc") is None

    def test_missing_entry_returns_none(self, tmp_path):
        cache = StackCache(root_dir=tmp_path / "cache")
        assert cache.lookup("never_stored") is None

    def test_corrupt_json_treated_as_miss(self, tmp_path):
        cache = StackCache(root_dir=tmp_path / "cache")
        cache.root_dir.mkdir(parents=True, exist_ok=True)
        (cache.root_dir / "corrupt.json").write_text("{ not valid json")
        assert cache.lookup("corrupt") is None

    def test_invalidate_removes_entry(self, tmp_path):
        cache = StackCache(root_dir=tmp_path / "cache")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        cache.store("abc", _make_manifest(out_dir))

        assert cache.invalidate("abc") is True
        assert cache.invalidate("abc") is False  # already gone
        assert cache.lookup("abc") is None

    def test_invalidated_entry_revives_on_outdir_recreation(self, tmp_path):
        # Per docstring: a missing-output_dir miss does NOT delete the
        # cache file. If the user recreates outputs, the cache revives.
        cache = StackCache(root_dir=tmp_path / "cache")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        cache.store("abc", _make_manifest(out_dir))

        out_dir.rmdir()
        assert cache.lookup("abc") is None

        out_dir.mkdir()  # user "ran" the stage again, outputs are back
        loaded = cache.lookup("abc")
        assert loaded is not None
        assert loaded.subject == "sub01"


class TestClear:
    def test_clear_removes_all(self, tmp_path):
        cache = StackCache(root_dir=tmp_path / "cache")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        cache.store("abc", _make_manifest(out_dir))
        cache.store("def", _make_manifest(out_dir))
        cache.store("ghi", _make_manifest(out_dir))

        assert cache.clear() == 3
        assert cache.clear() == 0  # already empty

    def test_clear_missing_root_returns_zero(self, tmp_path):
        cache = StackCache(root_dir=tmp_path / "never_created")
        assert cache.clear() == 0


class TestPersistenceAcrossInstances:
    def test_second_instance_sees_first_stored(self, tmp_path):
        root = tmp_path / "shared_cache"
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        first = StackCache(root_dir=root)
        first.store("abc", _make_manifest(out_dir))

        second = StackCache(root_dir=root)
        loaded = second.lookup("abc")
        assert loaded is not None
        assert loaded.subject == "sub01"
