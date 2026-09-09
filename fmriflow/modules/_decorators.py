"""Central module registration decorators.

Each decorator registers the class into a module-level dict keyed by module
name.  ``register_builtins()`` in ``modules/__init__.py`` copies these dicts
into the live :class:`ModuleRegistry` at startup.

Usage in any module file::

    from fmriflow.modules._decorators import feature_extractor

    @feature_extractor("numwords")
    class NumWordsExtractor:
        ...
"""
from __future__ import annotations

# ── Module-level registries ──────────────────────────────────────────────

_stimulus_loaders: dict[str, type] = {}
_response_loaders: dict[str, type] = {}
_response_readers: dict[str, type] = {}
_feature_extractors: dict[str, type] = {}
_feature_sources: dict[str, type] = {}
_preparers: dict[str, type] = {}
_preparation_steps: dict[str, type] = {}
_analyzers: dict[str, type] = {}
_models: dict[str, type] = {}
_reporters: dict[str, type] = {}
_nipype_nodes: dict[str, type] = {}
_group_analyzers: dict[str, type] = {}
_group_reporters: dict[str, type] = {}
_study_analyzers: dict[str, type] = {}
_study_reporters: dict[str, type] = {}

# QA reporters are keyed by stage first, then plugin name —
# ``_qa_reporters[stage][name] = cls``. Multiple plugins per stage is
# the common case, so the two-level dict keeps lookup cheap without
# scanning all plugins.
_qa_reporters: dict[str, dict[str, type]] = {}


# ── Decorator factories ──────────────────────────────────────────────────

def _make_decorator(registry: dict[str, type]):
    """Return a decorator that registers a class into *registry*."""
    def decorator(name: str):
        def wrapper(cls):
            registry[name] = cls
            return cls
        return wrapper
    return decorator


stimulus_loader = _make_decorator(_stimulus_loaders)
response_loader = _make_decorator(_response_loaders)
response_reader = _make_decorator(_response_readers)
feature_extractor = _make_decorator(_feature_extractors)
feature_source = _make_decorator(_feature_sources)
preparer = _make_decorator(_preparers)
preparation_step = _make_decorator(_preparation_steps)
analyzer = _make_decorator(_analyzers)
model = _make_decorator(_models)
reporter = _make_decorator(_reporters)
_nipype_node_legacy = _make_decorator(_nipype_nodes)


def nipype_node(name: str):
    """Register a post-preproc DAG node.

    Also registers the class in the unified preprocessing node library
    (``fmriflow.preproc.node_registry``), where it is an ``interface``
    node — the same class object serves both.
    """
    def wrapper(cls):
        _nipype_node_legacy(name)(cls)
        from fmriflow.preproc.node_registry import preproc_node
        preproc_node(name, kind="interface")(cls)
        return cls
    return wrapper
group_analyzer = _make_decorator(_group_analyzers)
group_reporter = _make_decorator(_group_reporters)
study_analyzer = _make_decorator(_study_analyzers)
study_reporter = _make_decorator(_study_reporters)


def qa_reporter(name: str, *, stage: str):
    """Register a QA reporter under ``stage``.

    Example::

        @qa_reporter("score_histogram", stage="model")
        class ModelScoreHistogram:
            ...
    """
    def wrapper(cls):
        # Stash the stage on the class so callers can introspect.
        cls.stage = stage
        _qa_reporters.setdefault(stage, {})[name] = cls
        return cls
    return wrapper
