"""Tests for PipelineContext."""

import pytest

from fmriflow.context import PipelineContext
from fmriflow.exceptions import PipelineError


class TestPipelineContextPutGet:
    def test_put_get_roundtrip(self):
        ctx = PipelineContext(config={})
        ctx.put("key", "value")
        assert ctx.get("key") == "value"

    def test_get_with_correct_type(self):
        ctx = PipelineContext(config={})
        ctx.put("num", 42)
        assert ctx.get("num", expected_type=int) == 42

    def test_get_with_wrong_type_raises(self):
        ctx = PipelineContext(config={})
        ctx.put("num", 42)
        with pytest.raises(PipelineError):
            ctx.get("num", expected_type=str)

    def test_get_missing_key_raises(self):
        ctx = PipelineContext(config={})
        with pytest.raises(PipelineError):
            ctx.get("nonexistent")

    def test_put_overwrites(self):
        ctx = PipelineContext(config={})
        ctx.put("key", "first")
        ctx.put("key", "second")
        assert ctx.get("key") == "second"


class TestPipelineContextHas:
    def test_has_returns_true(self):
        ctx = PipelineContext(config={})
        ctx.put("key", "value")
        assert ctx.has("key") is True

    def test_has_returns_false(self):
        ctx = PipelineContext(config={})
        assert ctx.has("missing") is False


class TestPipelineContextArtifacts:
    def test_add_and_retrieve_artifacts(self):
        ctx = PipelineContext(config={})
        ctx.add_artifacts("metrics", {"file": "/path/to/metrics.json"})
        arts = ctx.artifacts
        assert "metrics" in arts
        assert arts["metrics"]["file"] == "/path/to/metrics.json"

    def test_multiple_reporters(self):
        ctx = PipelineContext(config={})
        ctx.add_artifacts("metrics", {"a": "1"})
        ctx.add_artifacts("weights", {"b": "2"})
        arts = ctx.artifacts
        assert len(arts) == 2


class TestPipelineContextCheckpoint:
    def test_save_and_restore_checkpoint(self, tmp_path):
        config = {"reporting": {"output_dir": str(tmp_path)}}
        ctx = PipelineContext(config=config)
        ctx.put("key1", "value1")
        ctx.put("key2", [1, 2, 3])

        path = ctx.save_checkpoint("test_stage")
        assert path.exists()

        ctx2 = PipelineContext.from_checkpoint(config, "test_stage")
        assert ctx2.get("key1") == "value1"
        assert ctx2.get("key2") == [1, 2, 3]
