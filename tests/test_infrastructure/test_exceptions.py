"""Tests for exception hierarchy."""

import pytest

from denizenspipeline.exceptions import (
    ConfigError,
    DenizensError,
    PipelineError,
    PluginNotFoundError,
    StageError,
)


class TestConfigError:
    def test_with_string(self):
        err = ConfigError("single error")
        assert err.errors == ["single error"]
        assert "single error" in str(err)

    def test_with_list(self):
        errors = ["error 1", "error 2"]
        err = ConfigError(errors)
        assert err.errors == errors
        assert "error 1" in str(err)
        assert "error 2" in str(err)


class TestPipelineError:
    def test_without_stage(self):
        err = PipelineError("something broke")
        assert err.stage is None
        assert "something broke" in str(err)

    def test_with_stage(self):
        err = PipelineError("failed", stage="features")
        assert err.stage == "features"
        assert "features" in str(err)


class TestStageError:
    def test_wraps_original(self):
        original = ValueError("bad value")
        err = StageError("model", original)
        assert err.original is original
        assert err.stage == "model"
        assert "bad value" in str(err)


class TestInheritance:
    def test_config_error_is_denizens_error(self):
        assert issubclass(ConfigError, DenizensError)

    def test_plugin_not_found_is_denizens_error(self):
        assert issubclass(PluginNotFoundError, DenizensError)

    def test_pipeline_error_is_denizens_error(self):
        assert issubclass(PipelineError, DenizensError)

    def test_stage_error_is_pipeline_error(self):
        assert issubclass(StageError, PipelineError)

    def test_stage_error_is_denizens_error(self):
        assert issubclass(StageError, DenizensError)

    def test_catch_all_denizens_errors(self):
        with pytest.raises(DenizensError):
            raise ConfigError("test")
        with pytest.raises(DenizensError):
            raise PluginNotFoundError("test")
        with pytest.raises(DenizensError):
            raise PipelineError("test")
        with pytest.raises(DenizensError):
            raise StageError("stage", ValueError("x"))
