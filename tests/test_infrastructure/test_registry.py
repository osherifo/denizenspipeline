"""Tests for PluginRegistry."""

import pytest

from fmriflow.exceptions import PluginNotFoundError
from fmriflow.registry import PluginRegistry

# Categories that PluginRegistry.discover() must always populate.
# Update this set when adding a new top-level plugin category.
EXPECTED_CATEGORIES = {
    "stimulus_loaders",
    "response_loaders",
    "response_readers",
    "feature_extractors",
    "feature_sources",
    "preparers",
    "preparation_steps",
    "analyzers",
    "models",
    "reporters",
}


class TestPluginRegistryDiscover:
    @pytest.fixture
    def registry(self):
        reg = PluginRegistry()
        reg.discover()
        return reg

    def test_discover_populates_all_categories(self, registry):
        plugins = registry.list_plugins()
        assert set(plugins) == EXPECTED_CATEGORIES
        for category, names in plugins.items():
            assert len(names) > 0, f"{category} should have plugins"

    def test_known_builtins_registered(self, registry):
        """Spot-check that representative built-in plugins are discovered.

        Asserts plugin *names* rather than counts so the test doesn't break
        every time someone adds a new built-in.
        """
        plugins = registry.list_plugins()
        assert "textgrid" in plugins["stimulus_loaders"]
        assert "local" in plugins["response_loaders"]
        assert "auto" in plugins["response_readers"]
        assert "numwords" in plugins["feature_extractors"]
        assert "default" in plugins["preparers"]
        assert "flatmap" in plugins["reporters"]

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

        @reg.preparer("test_prep")
        class TestPrep:
            name = "test_prep"

        inst1 = reg.get_preparer("test_prep")
        inst2 = reg.get_preparer("test_prep")
        assert inst1 is not inst2
