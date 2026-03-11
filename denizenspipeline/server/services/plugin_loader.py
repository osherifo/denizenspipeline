"""Plugin code validation, dynamic registration, and persistence."""

from __future__ import annotations

import inspect
import logging
import os
import re
from pathlib import Path
from typing import Any

from denizenspipeline.plugins._decorators import (
    _stimulus_loaders,
    _response_loaders,
    _response_readers,
    _feature_extractors,
    _feature_sources,
    _preprocessors,
    _preprocessing_steps,
    _analyzers,
    _models,
    _reporters,
)

logger = logging.getLogger(__name__)

# Map categories to decorator registry dicts
CATEGORY_REGISTRY: dict[str, dict[str, type]] = {
    'stimulus_loaders': _stimulus_loaders,
    'response_loaders': _response_loaders,
    'response_readers': _response_readers,
    'feature_extractors': _feature_extractors,
    'feature_sources': _feature_sources,
    'preprocessors': _preprocessors,
    'preprocessing_steps': _preprocessing_steps,
    'analyzers': _analyzers,
    'models': _models,
    'reporters': _reporters,
}

# Required methods per category
REQUIRED_METHODS: dict[str, list[str]] = {
    'stimulus_loaders': ['load'],
    'response_loaders': ['load'],
    'response_readers': ['read'],
    'feature_extractors': ['extract'],
    'feature_sources': ['load'],
    'preprocessors': ['preprocess'],
    'preprocessing_steps': ['apply'],
    'analyzers': ['analyze'],
    'models': ['fit_predict'],
    'reporters': ['report'],
}


def get_plugins_dir() -> Path:
    """Return the user plugins directory, creating it if needed."""
    custom = os.environ.get('DENIZENS_PLUGINS_DIR')
    if custom:
        d = Path(custom)
    else:
        d = Path.home() / '.denizens' / 'plugins'
    d.mkdir(parents=True, exist_ok=True)
    return d


def validate_code(code: str, category: str | None = None) -> dict[str, Any]:
    """Validate plugin code without persisting or registering it.

    Returns a dict with:
      valid: bool
      errors: list[str]
      warnings: list[str]
      plugin_name: str | None
      class_name: str | None
      category: str | None   (detected or confirmed)
      params: dict | None
    """
    result: dict[str, Any] = {
        'valid': False,
        'errors': [],
        'warnings': [],
        'plugin_name': None,
        'class_name': None,
        'category': category,
        'params': None,
    }

    # Step 1: syntax check
    try:
        compiled = compile(code, '<user_plugin>', 'exec')
    except SyntaxError as e:
        result['errors'].append(f"Syntax error on line {e.lineno}: {e.msg}")
        return result

    # Step 2: snapshot registries to detect new entries
    snapshots = {cat: set(reg.keys()) for cat, reg in CATEGORY_REGISTRY.items()}

    # Step 3: exec in controlled namespace
    try:
        exec(compiled)
    except Exception as e:
        result['errors'].append(f"Execution error: {e}")
        # Roll back any partial registrations
        _rollback(snapshots)
        return result

    # Step 4: find what was registered
    detected_category = None
    detected_name = None
    detected_cls = None

    for cat, reg in CATEGORY_REGISTRY.items():
        new_names = set(reg.keys()) - snapshots[cat]
        if new_names:
            if detected_category is not None:
                result['warnings'].append(
                    f"Plugin registered in multiple categories: {detected_category}, {cat}")
            detected_category = cat
            detected_name = next(iter(new_names))
            detected_cls = reg[detected_name]

    if detected_cls is None:
        result['errors'].append(
            "No decorated plugin class found. "
            "Make sure you use the correct decorator (e.g. @feature_extractor(\"name\")).")
        _rollback(snapshots)
        return result

    # Category mismatch check
    if category and detected_category != category:
        result['warnings'].append(
            f"Expected category '{category}' but plugin registered as '{detected_category}'")

    result['plugin_name'] = detected_name
    result['class_name'] = detected_cls.__name__
    result['category'] = detected_category

    # Step 5: check required methods
    required = REQUIRED_METHODS.get(detected_category, [])
    for method_name in required:
        if not hasattr(detected_cls, method_name):
            result['errors'].append(
                f"Missing required method: {method_name}()")
        elif not callable(getattr(detected_cls, method_name)):
            result['errors'].append(
                f"'{method_name}' must be a method, not an attribute")

    # Step 6: extract PARAM_SCHEMA
    from denizenspipeline.plugins._schema import extract_schema
    result['params'] = extract_schema(detected_cls)

    # Step 7: check for name collision with built-in plugins
    # (Only warn if the name was already present before exec)
    if detected_name in snapshots.get(detected_category, set()):
        result['warnings'].append(
            f"Plugin '{detected_name}' already exists in '{detected_category}'. "
            f"Saving will override the existing plugin.")

    # Roll back the registration — we only validate here, don't persist
    _rollback(snapshots)

    if not result['errors']:
        result['valid'] = True

    return result


def _rollback(snapshots: dict[str, set[str]]) -> None:
    """Remove any entries that were added during exec."""
    for cat, reg in CATEGORY_REGISTRY.items():
        new_names = set(reg.keys()) - snapshots[cat]
        for name in new_names:
            del reg[name]


def register_code(code: str) -> tuple[str, str, str]:
    """Execute plugin code and register it in the live registry.

    Returns (plugin_name, class_name, category).
    Raises ValueError if registration fails.
    """
    snapshots = {cat: set(reg.keys()) for cat, reg in CATEGORY_REGISTRY.items()}

    try:
        exec(compile(code, '<user_plugin>', 'exec'))
    except Exception as e:
        _rollback(snapshots)
        raise ValueError(f"Failed to execute plugin code: {e}") from e

    for cat, reg in CATEGORY_REGISTRY.items():
        new_names = set(reg.keys()) - snapshots[cat]
        if new_names:
            name = next(iter(new_names))
            cls = reg[name]
            return name, cls.__name__, cat

    raise ValueError("No decorated plugin class found in the code.")


def save_plugin(code: str, name: str, category: str) -> Path:
    """Save plugin code to disk and register it.

    Returns the file path where the plugin was saved.
    """
    plugins_dir = get_plugins_dir()
    filepath = plugins_dir / f"{name}.py"
    filepath.write_text(code)
    logger.info("Saved user plugin: %s -> %s", name, filepath)
    return filepath


def delete_plugin(name: str) -> bool:
    """Delete a user plugin file and unregister it.

    Returns True if the file existed and was deleted.
    """
    plugins_dir = get_plugins_dir()
    filepath = plugins_dir / f"{name}.py"

    # Find and unregister from decorator registries
    for cat, reg in CATEGORY_REGISTRY.items():
        if name in reg:
            del reg[name]
            logger.info("Unregistered plugin: %s from %s", name, cat)

    if filepath.is_file():
        filepath.unlink()
        logger.info("Deleted user plugin file: %s", filepath)
        return True
    return False


def list_user_plugins() -> list[dict[str, Any]]:
    """List all user plugins from the plugins directory."""
    plugins_dir = get_plugins_dir()
    result = []

    for py_file in sorted(plugins_dir.glob('*.py')):
        name = py_file.stem
        # Detect which category it's registered in
        category = None
        registered = False
        for cat, reg in CATEGORY_REGISTRY.items():
            if name in reg:
                category = cat
                registered = True
                break

        result.append({
            'name': name,
            'filename': py_file.name,
            'category': category,
            'registered': registered,
            'path': str(py_file),
        })

    return result


def get_user_plugin_code(name: str) -> str | None:
    """Return the source code for a user plugin, or None if not found."""
    plugins_dir = get_plugins_dir()
    filepath = plugins_dir / f"{name}.py"
    if filepath.is_file():
        return filepath.read_text()
    return None


def discover_user_plugins(plugins_dir: Path | None = None) -> int:
    """Load all user plugins from the plugins directory.

    Returns the number of plugins successfully loaded.
    """
    if plugins_dir is None:
        plugins_dir = get_plugins_dir()

    if not plugins_dir.is_dir():
        return 0

    loaded = 0
    for py_file in sorted(plugins_dir.glob('*.py')):
        try:
            code = py_file.read_text()
            exec(compile(code, str(py_file), 'exec'))
            logger.info("Loaded user plugin: %s", py_file.stem)
            loaded += 1
        except Exception as e:
            logger.warning("Failed to load user plugin %s: %s", py_file.stem, e)

    return loaded
