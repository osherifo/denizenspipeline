"""Module registry: discovers, registers, and resolves pipeline modules.

A "module" here is an internal implementation of a pipeline stage —
a stimulus loader, response loader, feature extractor, preparer,
preparation step, analyzer, model, or reporter. The term is reserved
distinct from "plugin", which is intended for downloadable third-party
extensions in the future.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from fmriflow.exceptions import ModuleLookupError
from fmriflow.modules._decorators import (
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
    _group_analyzers,
    _group_reporters,
    _study_analyzers,
    _study_reporters,
    _qa_reporters,
)

logger = logging.getLogger(__name__)


_USER_ADDONS_LOADED = False


class ModuleRegistry:
    """Discovers and manages modules by type.

    Modules are registered as classes (not instances).  The backing dicts
    live in :mod:`fmriflow.modules._decorators` so that the
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
        self._group_analyzers = _group_analyzers
        self._group_reporters = _group_reporters
        self._study_analyzers = _study_analyzers
        self._study_reporters = _study_reporters
        self._qa_reporters = _qa_reporters

    def discover(self) -> None:
        """Discover modules from builtins, entry_points and user addons."""
        self._register_builtins()
        self._discover_entry_points()
        self._discover_user_addons()

    def _discover_user_addons(self) -> None:
        """Load ``$FMRIFLOW_HOME/addons/modules/*.py`` once per process, so CLI runs see addons too."""
        global _USER_ADDONS_LOADED
        if _USER_ADDONS_LOADED:
            return
        _USER_ADDONS_LOADED = True
        try:
            from fmriflow.server.services.module_loader import discover_user_modules
            discover_user_modules()
        except Exception as exc:
            logger.warning("Could not load user addon modules: %s", exc)

    def _register_builtins(self) -> None:
        """Register the built-in modules that ship with fmriflow."""
        from fmriflow.modules import register_builtins
        register_builtins(self)

    def _discover_entry_points(self) -> None:
        """Load modules from installed packages via entry_points."""
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
            'fmriflow.group_analyzers': self._group_analyzers,
            'fmriflow.group_reporters': self._group_reporters,
            'fmriflow.study_analyzers': self._study_analyzers,
            'fmriflow.study_reporters': self._study_reporters,
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
                        logger.debug(f"Discovered module: {group}/{ep.name}")
                    except Exception as e:
                        logger.warning(
                            f"Failed to load module {group}/{ep.name}: {e}")

        # QA reporters use a nested ``dict[stage, dict[name, cls]]``
        # storage shape so the flat-dict loader above can't handle them
        # directly. The class itself carries ``stage`` as a class
        # attribute (set by the built-in @qa_reporter decorator); a
        # third-party class is expected to do the same.
        qa_group = 'fmriflow.qa_reporters'
        try:
            qa_eps = entry_points(group=qa_group)
        except TypeError:
            qa_eps = entry_points().get(qa_group, [])
        for ep in qa_eps:
            try:
                cls = ep.load()
                stage = getattr(cls, 'stage', None)
                if not isinstance(stage, str) or not stage:
                    logger.warning(
                        f"Skipping {qa_group}/{ep.name}: class is missing a "
                        f"'stage' class attribute")
                    continue
                bucket = self._qa_reporters.setdefault(stage, {})
                if ep.name in bucket:
                    continue
                bucket[ep.name] = cls
                logger.debug(f"Discovered module: {qa_group}/{ep.name} (stage={stage})")
            except Exception as e:
                logger.warning(
                    f"Failed to load module {qa_group}/{ep.name}: {e}")

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

    def group_analyzer(self, name: str):
        """Decorator to register a group-scope analyzer."""
        def wrapper(cls):
            self._group_analyzers[name] = cls
            return cls
        return wrapper

    def group_reporter(self, name: str):
        """Decorator to register a group-scope reporter."""
        def wrapper(cls):
            self._group_reporters[name] = cls
            return cls
        return wrapper

    def qa_reporter(self, name: str, *, stage: str):
        """Decorator to register a QA reporter for ``stage``.

        Example::

            @registry.qa_reporter("score_histogram", stage="model")
            class ModelScoreHistogram:
                ...
        """
        def wrapper(cls):
            cls.stage = stage
            self._qa_reporters.setdefault(stage, {})[name] = cls
            return cls
        return wrapper

    # ─── Getters (return instances) ─────────────────────────────

    def get_stimulus_loader(self, name: str):
        if name not in self._stimulus_loaders:
            raise ModuleLookupError(
                f"Stimulus loader '{name}' not found. "
                f"Available: {list(self._stimulus_loaders.keys())}")
        return self._stimulus_loaders[name]()

    def get_response_loader(self, name: str):
        if name not in self._response_loaders:
            raise ModuleLookupError(
                f"Response loader '{name}' not found. "
                f"Available: {list(self._response_loaders.keys())}")
        return self._response_loaders[name]()

    def get_response_reader(self, name: str):
        if name not in self._response_readers:
            raise ModuleLookupError(
                f"Response reader '{name}' not found. "
                f"Available: {list(self._response_readers.keys())}")
        return self._response_readers[name]()

    def get_feature_extractor(self, name: str):
        if name not in self._feature_extractors:
            raise ModuleLookupError(
                f"Feature extractor '{name}' not found. "
                f"Available: {list(self._feature_extractors.keys())}")
        return self._feature_extractors[name]()

    def get_feature_source(self, name: str):
        if name not in self._feature_sources:
            raise ModuleLookupError(
                f"Feature source '{name}' not found. "
                f"Available: {list(self._feature_sources.keys())}")
        return self._feature_sources[name]()

    def get_preparer(self, name: str):
        if name not in self._preparers:
            raise ModuleLookupError(
                f"Preparer '{name}' not found. "
                f"Available: {list(self._preparers.keys())}")
        return self._preparers[name]()

    def get_preparation_step(self, name: str):
        if name not in self._preparation_steps:
            raise ModuleLookupError(
                f"Preparation step '{name}' not found. "
                f"Available: {list(self._preparation_steps.keys())}")
        return self._preparation_steps[name]()

    def get_analyzer(self, name: str):
        if name not in self._analyzers:
            raise ModuleLookupError(
                f"Analyzer '{name}' not found. "
                f"Available: {list(self._analyzers.keys())}")
        return self._analyzers[name]()

    def get_model(self, name: str):
        if name not in self._models:
            raise ModuleLookupError(
                f"Model '{name}' not found. "
                f"Available: {list(self._models.keys())}")
        return self._models[name]()

    def get_reporter(self, name: str):
        if name not in self._reporters:
            raise ModuleLookupError(
                f"Reporter '{name}' not found. "
                f"Available: {list(self._reporters.keys())}")
        return self._reporters[name]()

    def get_group_analyzer(self, name: str):
        if name not in self._group_analyzers:
            raise ModuleLookupError(
                f"Group analyzer '{name}' not found. "
                f"Available: {list(self._group_analyzers.keys())}")
        return self._group_analyzers[name]()

    def get_group_reporter(self, name: str):
        if name not in self._group_reporters:
            raise ModuleLookupError(
                f"Group reporter '{name}' not found. "
                f"Available: {list(self._group_reporters.keys())}")
        return self._group_reporters[name]()

    def get_study_analyzer(self, name: str):
        if name not in self._study_analyzers:
            raise ModuleLookupError(
                f"Study analyzer '{name}' not found. "
                f"Available: {list(self._study_analyzers.keys())}")
        return self._study_analyzers[name]()

    def get_study_reporter(self, name: str):
        if name not in self._study_reporters:
            raise ModuleLookupError(
                f"Study reporter '{name}' not found. "
                f"Available: {list(self._study_reporters.keys())}")
        return self._study_reporters[name]()

    def get_qa_reporter(self, stage: str, name: str):
        """Look up one QA reporter by ``(stage, name)``."""
        plugins = self._qa_reporters.get(stage, {})
        if name not in plugins:
            raise ModuleLookupError(
                f"QA reporter '{name}' not found for stage '{stage}'. "
                f"Available for this stage: {sorted(plugins.keys())}")
        return plugins[name]()

    def list_qa_reporters(self, stage: str | None = None) -> dict:
        """List registered QA reporters.

        With ``stage=None``, returns ``{stage: [names]}`` across every
        stage. With ``stage`` set, returns ``[names]`` for that stage.
        """
        if stage is None:
            return {
                s: sorted(plugins.keys())
                for s, plugins in self._qa_reporters.items()
            }
        return sorted(self._qa_reporters.get(stage, {}).keys())

    # ─── Introspection ──────────────────────────────────────────

    def list_modules(self) -> dict[str, list[str]]:
        """List all registered modules by type."""
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
            'group_analyzers': sorted(self._group_analyzers.keys()),
            'study_analyzers': sorted(self._study_analyzers.keys()),
            'study_reporters': sorted(self._study_reporters.keys()),
            'group_reporters': sorted(self._group_reporters.keys()),
        }

    def get_module_class(self, category: str, name: str) -> type:
        """Return the raw class (not an instance) for a module."""
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
            'group_analyzers': self._group_analyzers,
            'group_reporters': self._group_reporters,
            'study_analyzers': self._study_analyzers,
            'study_reporters': self._study_reporters,
        }
        if category not in registry_map:
            raise ModuleLookupError(f"Unknown category '{category}'")
        modules = registry_map[category]
        if name not in modules:
            raise ModuleLookupError(
                f"Module '{name}' not found in '{category}'. "
                f"Available: {sorted(modules.keys())}")
        return modules[name]

    def module_metadata(self) -> dict[str, list[dict]]:
        """Return full module metadata for all categories.

        Each entry includes name, docstring, category, stage, n_dims
        (for extractors), and PARAM_SCHEMA.
        """
        from fmriflow.modules._schema import extract_schema

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
            'group_analyzers': 'group_analyze',
            'group_reporters': 'group_report',
            'study_analyzers': 'study_analyze',
            'study_reporters': 'study_report',
        }

        result = {}
        for category, names in self.list_modules().items():
            result[category] = []
            for name in names:
                cls = self.get_module_class(category, name)
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

        # QA reporters use a nested ``dict[stage, dict[name, cls]]``
        # storage shape (a single plugin name may register against
        # multiple stages). Flatten to a single ``qa_reporters`` list so
        # the browser's per-category grouping treats them like any
        # other plugin type — each entry keeps its own ``stage`` so
        # downstream UI groups them under the right subject stage.
        result['qa_reporters'] = []
        for stage, plugins in self._qa_reporters.items():
            for name, cls in sorted(plugins.items()):
                doc = (cls.__doc__ or '').strip()
                entry = {
                    'name': name,
                    'docstring': doc.split('\n')[0] if doc else '',
                    'full_docstring': doc,
                    'category': 'qa_reporters',
                    'stage': stage,
                    'params': extract_schema(cls),
                }
                result['qa_reporters'].append(entry)
        return result
