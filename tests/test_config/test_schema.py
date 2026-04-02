"""Tests for configuration schema validation."""

import pytest

from fmriflow.config.schema import validate_config


class TestValidateConfig:
    def test_valid_minimal_config(self, minimal_config):
        errors = validate_config(minimal_config)
        assert errors == []

    def test_missing_experiment(self, minimal_config):
        del minimal_config["experiment"]
        errors = validate_config(minimal_config)
        assert any("experiment" in e for e in errors)

    def test_missing_subject(self, minimal_config):
        del minimal_config["subject"]
        errors = validate_config(minimal_config)
        assert any("subject" in e for e in errors)

    def test_missing_test_runs(self, minimal_config):
        del minimal_config["split"]["test_runs"]
        errors = validate_config(minimal_config)
        assert any("test_runs" in e for e in errors)

    def test_invalid_feature_source(self, minimal_config):
        minimal_config["features"] = [
            {"name": "bad", "source": "invalid_source"},
        ]
        errors = validate_config(minimal_config)
        assert any("invalid source" in e.lower() or "invalid_source" in e for e in errors)

    def test_filesystem_source_missing_path(self, minimal_config):
        minimal_config["features"] = [
            {"name": "feat", "source": "filesystem"},
        ]
        errors = validate_config(minimal_config)
        assert any("path" in e for e in errors)

    def test_features_not_a_list(self, minimal_config):
        minimal_config["features"] = "not_a_list"
        errors = validate_config(minimal_config)
        assert any("list" in e for e in errors)

    def test_invalid_trim_start(self, minimal_config):
        minimal_config["preprocessing"]["trim_start"] = -1
        errors = validate_config(minimal_config)
        assert any("trim_start" in e for e in errors)

    def test_invalid_language(self, minimal_config):
        minimal_config["stimulus"] = {"language": "xx"}
        errors = validate_config(minimal_config)
        assert any("language" in e for e in errors)

    def test_empty_config_multiple_errors(self):
        errors = validate_config({})
        assert len(errors) >= 2  # At least experiment and subject
