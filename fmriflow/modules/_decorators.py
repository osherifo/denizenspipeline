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
nipype_node = _make_decorator(_nipype_nodes)
