"""Plugin registry: discovers, registers, and resolves plugins."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from fmriflow.exceptions import PluginNotFoundError
from fmriflow.plugins._decorators import (
    _stimulus_loaders,
    _response_loaders,
    _response_readers,
    _feature_extractors,
    _feature_sources,
    _preparers,
    _preparation_steps,
    _analyzers,
    _models,
    _reporters,
)

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Discovers and manages plugins by type.

    Plugins are registered as classes (not instances).  The backing dicts
    live in :mod:`fmriflow.plugins._decorators` so that the
    ``@decorator`` on each class and the registry share a single source
    of truth.  Instances are created on demand via the ``get_*`` methods.
    """

    def __init__(self):
        self._stimulus_loaders = _stimulus_loaders
        self._response_loaders = _response_loaders
        self._response_readers = _response_readers
        self._feature_extractors = _feature_extractors
        self._feature_sources = _feature_sources
        self._preparers = _preparers
        self._preparation_steps = _preparation_steps
        self._analyzers = _analyzers
        self._models = _models
        self._reporters = _reporters

    def discover(self) -> None:
        """Discover plugins from builtins and entry_points."""
        self._register_builtins()
        self._discover_entry_points()

    def _register_builtins(self) -> None:
        """Register the built-in plugins that ship with fmriflow."""
        from fmriflow.plugins import register_builtins
        register_builtins(self)

    def _discover_entry_points(self) -> None:
        """Load plugins from installed packages via entry_points."""
        groups = {
            'fmriflow.stimulus_loaders': self._stimulus_loaders,
            'fmriflow.response_loaders': self._response_loaders,
            'fmriflow.response_readers': self._response_readers,
            'fmriflow.feature_extractors': self._feature_extractors,
            'fmriflow.feature_sources': self._feature_sources,
            'fmriflow.preparers': self._preparers,
            'fmriflow.preparation_steps': self._preparation_steps,
            'fmriflow.analyzers': self._analyzers,
            'fmriflow.models': self._models,
            'fmriflow.reporters': self._reporters,
        }

        for group, registry_dict in groups.items():
            try:
                eps = entry_points(group=group)
            except TypeError:
                # Python < 3.12 compatibility
                eps = entry_points().get(group, [])

            for ep in eps:
                if ep.name not in registry_dict:
                    try:
                        cls = ep.load()
                        registry_dict[ep.name] = cls
                        logger.debug(f"Discovered plugin: {group}/{ep.name}")
                    except Exception as e:
                        logger.warning(
                            f"Failed to load plugin {group}/{ep.name}: {e}")

    # ─── Decorator API ──────────────────────────────────────────

    def stimulus_loader(self, name: str):
        """Decorator to register a stimulus loader."""
        def wrapper(cls):
            self._stimulus_loaders[name] = cls
            return cls
        return wrapper

    def response_loader(self, name: str):
        """Decorator to register a response loader."""
        def wrapper(cls):
            self._response_loaders[name] = cls
            return cls
        return wrapper

    def response_reader(self, name: str):
        """Decorator to register a response reader."""
        def wrapper(cls):
            self._response_readers[name] = cls
            return cls
        return wrapper

    def feature_extractor(self, name: str):
        """Decorator to register a feature extractor."""
        def wrapper(cls):
            self._feature_extractors[name] = cls
            return cls
        return wrapper

    def feature_source(self, name: str):
        """Decorator to register a feature source."""
        def wrapper(cls):
            self._feature_sources[name] = cls
            return cls
        return wrapper

    def preparer(self, name: str):
        """Decorator to register a preparer (analysis-stage data preparation)."""
        def wrapper(cls):
            self._preparers[name] = cls
            return cls
        return wrapper

    def preparation_step(self, name: str):
        """Decorator to register a preparation step."""
        def wrapper(cls):
            self._preparation_steps[name] = cls
            return cls
        return wrapper

    def analyzer(self, name: str):
        """Decorator to register an analyzer."""
        def wrapper(cls):
            self._analyzers[name] = cls
            return cls
        return wrapper

    def model(self, name: str):
        """Decorator to register a model."""
        def wrapper(cls):
            self._models[name] = cls
            return cls
        return wrapper

    def reporter(self, name: str):
        """Decorator to register a reporter."""
        def wrapper(cls):
            self._reporters[name] = cls
            return cls
        return wrapper

    # ─── Getters (return instances) ─────────────────────────────

    def get_stimulus_loader(self, name: str):
        if name not in self._stimulus_loaders:
            raise PluginNotFoundError(
                f"Stimulus loader '{name}' not found. "
                f"Available: {list(self._stimulus_loaders.keys())}")
        return self._stimulus_loaders[name]()

    def get_response_loader(self, name: str):
        if name not in self._response_loaders:
            raise PluginNotFoundError(
                f"Response loader '{name}' not found. "
                f"Available: {list(self._response_loaders.keys())}")
        return self._response_loaders[name]()

    def get_response_reader(self, name: str):
        if name not in self._response_readers:
            raise PluginNotFoundError(
                f"Response reader '{name}' not found. "
                f"Available: {list(self._response_readers.keys())}")
        return self._response_readers[name]()

    def get_feature_extractor(self, name: str):
        if name not in self._feature_extractors:
            raise PluginNotFoundError(
                f"Feature extractor '{name}' not found. "
                f"Available: {list(self._feature_extractors.keys())}")
        return self._feature_extractors[name]()

    def get_feature_source(self, name: str):
        if name not in self._feature_sources:
            raise PluginNotFoundError(
                f"Feature source '{name}' not found. "
                f"Available: {list(self._feature_sources.keys())}")
        return self._feature_sources[name]()

    def get_preparer(self, name: str):
        if name not in self._preparers:
            raise PluginNotFoundError(
                f"Preparer '{name}' not found. "
                f"Available: {list(self._preparers.keys())}")
        return self._preparers[name]()

    def get_preparation_step(self, name: str):
        if name not in self._preparation_steps:
            raise PluginNotFoundError(
                f"Preparation step '{name}' not found. "
                f"Available: {list(self._preparation_steps.keys())}")
        return self._preparation_steps[name]()

    def get_analyzer(self, name: str):
        if name not in self._analyzers:
            raise PluginNotFoundError(
                f"Analyzer '{name}' not found. "
                f"Available: {list(self._analyzers.keys())}")
        return self._analyzers[name]()

    def get_model(self, name: str):
        if name not in self._models:
            raise PluginNotFoundError(
                f"Model '{name}' not found. "
                f"Available: {list(self._models.keys())}")
        return self._models[name]()

    def get_reporter(self, name: str):
        if name not in self._reporters:
            raise PluginNotFoundError(
                f"Reporter '{name}' not found. "
                f"Available: {list(self._reporters.keys())}")
        return self._reporters[name]()

    # ─── Introspection ──────────────────────────────────────────

    def list_plugins(self) -> dict[str, list[str]]:
        """List all registered plugins by type."""
        return {
            'stimulus_loaders': sorted(self._stimulus_loaders.keys()),
            'response_loaders': sorted(self._response_loaders.keys()),
            'response_readers': sorted(self._response_readers.keys()),
            'feature_extractors': sorted(self._feature_extractors.keys()),
            'feature_sources': sorted(self._feature_sources.keys()),
            'preparers': sorted(self._preparers.keys()),
            'preparation_steps': sorted(self._preparation_steps.keys()),
            'analyzers': sorted(self._analyzers.keys()),
            'models': sorted(self._models.keys()),
            'reporters': sorted(self._reporters.keys()),
        }

    def get_plugin_class(self, category: str, name: str) -> type:
        """Return the raw class (not an instance) for a plugin."""
        registry_map = {
            'stimulus_loaders': self._stimulus_loaders,
            'response_loaders': self._response_loaders,
            'response_readers': self._response_readers,
            'feature_extractors': self._feature_extractors,
            'feature_sources': self._feature_sources,
            'preparers': self._preparers,
            'preparation_steps': self._preparation_steps,
            'analyzers': self._analyzers,
            'models': self._models,
            'reporters': self._reporters,
        }
        if category not in registry_map:
            raise PluginNotFoundError(f"Unknown category '{category}'")
        plugins = registry_map[category]
        if name not in plugins:
            raise PluginNotFoundError(
                f"Plugin '{name}' not found in '{category}'. "
                f"Available: {sorted(plugins.keys())}")
        return plugins[name]

    def plugin_metadata(self) -> dict[str, list[dict]]:
        """Return full plugin metadata for all categories.

        Each entry includes name, docstring, category, stage, n_dims
        (for extractors), and PARAM_SCHEMA.
        """
        from fmriflow.plugins._schema import extract_schema

        CATEGORY_TO_STAGE = {
            'stimulus_loaders': 'stimuli',
            'response_loaders': 'responses',
            'response_readers': 'responses',
            'feature_extractors': 'features',
            'feature_sources': 'features',
            'preparers': 'prepare',
            'preparation_steps': 'prepare',
            'analyzers': 'analyze',
            'models': 'model',
            'reporters': 'report',
        }

        result = {}
        for category, names in self.list_plugins().items():
            result[category] = []
            for name in names:
                cls = self.get_plugin_class(category, name)
                doc = (cls.__doc__ or '').strip()
                entry = {
                    'name': name,
                    'docstring': doc.split('\n')[0] if doc else '',
                    'full_docstring': doc,
                    'category': category,
                    'stage': CATEGORY_TO_STAGE[category],
                    'params': extract_schema(cls),
                }
                if hasattr(cls, 'n_dims'):
                    entry['n_dims'] = cls.n_dims
                result[category].append(entry)
        return result
