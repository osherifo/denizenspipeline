"""Tests for configuration loading, merging, and env var resolution."""

import os

import pytest
import yaml

from fmriflow.config.loader import (
    load_config,
    load_config_with_inheritance,
    merge_configs,
    resolve_env_vars,
)
from fmriflow.exceptions import ConfigError


class TestMergeConfigs:
    def test_deep_merge(self):
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10}}
        result = merge_configs(base, override)
        assert result["a"]["b"] == 10
        assert result["a"]["c"] == 2
        assert result["d"] == 3

    def test_override_scalars(self):
        base = {"x": 1}
        override = {"x": 2}
        result = merge_configs(base, override)
        assert result["x"] == 2

    def test_nested_dict_merge(self):
        base = {"a": {"b": {"c": 1}}}
        override = {"a": {"b": {"d": 2}}}
        result = merge_configs(base, override)
        assert result["a"]["b"]["c"] == 1
        assert result["a"]["b"]["d"] == 2

    def test_lists_replaced_not_merged(self):
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = merge_configs(base, override)
        assert result["items"] == [4, 5]

    def test_new_keys_added(self):
        base = {"a": 1}
        override = {"b": 2}
        result = merge_configs(base, override)
        assert result["a"] == 1
        assert result["b"] == 2

    def test_does_not_mutate_inputs(self):
        base = {"a": {"b": 1}}
        override = {"a": {"b": 2}}
        merge_configs(base, override)
        assert base["a"]["b"] == 1


class TestResolveEnvVars:
    def test_env_var_substitution(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "hello")
        result = resolve_env_vars({"key": "${MY_VAR}"})
        assert result["key"] == "hello"

    def test_default_fallback(self):
        result = resolve_env_vars({"key": "${UNSET_VAR_XYZ:fallback}"})
        assert result["key"] == "fallback"

    def test_nested_dicts(self, monkeypatch):
        monkeypatch.setenv("INNER", "value")
        result = resolve_env_vars({"outer": {"inner": "${INNER}"}})
        assert result["outer"]["inner"] == "value"

    def test_nested_lists(self, monkeypatch):
        monkeypatch.setenv("ITEM", "resolved")
        result = resolve_env_vars({"items": ["${ITEM}", "static"]})
        assert result["items"] == ["resolved", "static"]

    def test_unset_var_left_as_is(self):
        result = resolve_env_vars({"key": "${DEFINITELY_NOT_SET_ABC123}"})
        assert result["key"] == "${DEFINITELY_NOT_SET_ABC123}"

    def test_non_string_passthrough(self):
        result = resolve_env_vars({"num": 42, "flag": True})
        assert result["num"] == 42
        assert result["flag"] is True


class TestLoadConfig:
    def test_load_valid_yaml(self, tmp_path):
        config = {
            "experiment": "test",
            "subject": "subj",
            "features": [{"name": "numwords"}],
            "split": {"test_runs": ["story1"]},
        }
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(config, f)

        loaded = load_config(path)
        assert loaded["experiment"] == "test"
        assert loaded["subject"] == "subj"
        # Should have default values merged in
        assert "preparation" in loaded
        assert "model" in loaded

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(ConfigError):
            load_config(tmp_path / "nonexistent.yaml")


class TestLoadConfigWithInheritance:
    def test_parent_child_chain(self, tmp_path):
        parent_config = {
            "experiment": "parent_exp",
            "preparation": {"trim_start": 10},
        }
        parent_path = tmp_path / "parent.yaml"
        with open(parent_path, "w") as f:
            yaml.dump(parent_config, f)

        child_config = {
            "inherit": "parent.yaml",
            "subject": "child_subj",
            "preparation": {"trim_end": 3},
        }

        result = load_config_with_inheritance(child_config, tmp_path)
        assert result["experiment"] == "parent_exp"
        assert result["subject"] == "child_subj"
        assert result["preparation"]["trim_start"] == 10
        assert result["preparation"]["trim_end"] == 3

    def test_no_inherit_passthrough(self):
        config = {"experiment": "test"}
        result = load_config_with_inheritance(config, "/tmp")
        assert result == {"experiment": "test"}

    def test_missing_parent_raises(self, tmp_path):
        config = {"inherit": "nonexistent.yaml"}
        with pytest.raises(ConfigError):
            load_config_with_inheritance(config, tmp_path)
