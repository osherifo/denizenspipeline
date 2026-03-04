"""Central plugin registration decorators.

Each decorator registers the class into a module-level dict keyed by plugin
name.  ``register_builtins()`` in ``plugins/__init__.py`` copies these dicts
into the live :class:`PluginRegistry` at startup.

Usage in any plugin file::

    from denizenspipeline.plugins._decorators import feature_extractor

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
_preprocessors: dict[str, type] = {}
_preprocessing_steps: dict[str, type] = {}
_analyzers: dict[str, type] = {}
_models: dict[str, type] = {}
_reporters: dict[str, type] = {}


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
preprocessor = _make_decorator(_preprocessors)
preprocessing_step = _make_decorator(_preprocessing_steps)
analyzer = _make_decorator(_analyzers)
model = _make_decorator(_models)
reporter = _make_decorator(_reporters)
