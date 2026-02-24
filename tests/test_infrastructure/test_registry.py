"""Tests for PluginRegistry."""

import pytest

from denizenspipeline.exceptions import PluginNotFoundError
from denizenspipeline.registry import PluginRegistry


class TestPluginRegistryDiscover:
    @pytest.fixture
    def registry(self):
        reg = PluginRegistry()
        reg.discover()
        return reg

    def test_discover_populates_all_categories(self, registry):
        plugins = registry.list_plugins()
        assert len(plugins) == 7
        for category, names in plugins.items():
            assert len(names) > 0, f"{category} should have plugins"

    def test_list_plugins_counts(self, registry):
        plugins = registry.list_plugins()
        assert len(plugins['stimulus_loaders']) == 1
        assert len(plugins['response_loaders']) == 2
        assert len(plugins['feature_extractors']) == 10
        assert len(plugins['feature_sources']) == 3
        assert len(plugins['preprocessors']) == 2
        assert len(plugins['models']) == 1
        assert len(plugins['reporters']) == 3

    def test_get_feature_extractor(self, registry):
        ext = registry.get_feature_extractor("numwords")
        assert ext.name == "numwords"
        assert ext.n_dims == 1

    def test_unknown_name_raises(self, registry):
        with pytest.raises(PluginNotFoundError):
            registry.get_feature_extractor("nonexistent_extractor")

    def test_unknown_model_raises(self, registry):
        with pytest.raises(PluginNotFoundError):
            registry.get_model("nonexistent_model")


class TestPluginRegistryDecorators:
    def test_decorator_registration(self):
        reg = PluginRegistry()

        @reg.feature_extractor("custom_extractor")
        class CustomExtractor:
            name = "custom_extractor"
            n_dims = 1
            def extract(self, stimuli, run_names, config): ...
            def validate_config(self, config): return []

        plugins = reg.list_plugins()
        assert "custom_extractor" in plugins["feature_extractors"]

    def test_decorator_returns_class(self):
        reg = PluginRegistry()

        @reg.model("test_model")
        class TestModel:
            name = "test_model"

        assert TestModel.name == "test_model"

    def test_multiple_decorators(self):
        reg = PluginRegistry()

        @reg.reporter("r1")
        class R1:
            name = "r1"

        @reg.reporter("r2")
        class R2:
            name = "r2"

        plugins = reg.list_plugins()
        assert "r1" in plugins["reporters"]
        assert "r2" in plugins["reporters"]


class TestPluginRegistryGetters:
    def test_get_returns_instance(self):
        reg = PluginRegistry()

        @reg.stimulus_loader("test_loader")
        class TestLoader:
            name = "test_loader"
            def load(self, config): ...
            def validate_config(self, config): return []

        instance = reg.get_stimulus_loader("test_loader")
        assert isinstance(instance, TestLoader)

    def test_each_call_returns_new_instance(self):
        reg = PluginRegistry()

        @reg.preprocessor("test_prep")
        class TestPrep:
            name = "test_prep"

        inst1 = reg.get_preprocessor("test_prep")
        inst2 = reg.get_preprocessor("test_prep")
        assert inst1 is not inst2
