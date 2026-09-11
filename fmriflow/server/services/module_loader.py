"""Module code validation, dynamic registration, and persistence."""

from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path
from typing import Any

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
    _qa_reporters,
    _group_analyzers,
    _group_reporters,
    _study_analyzers,
    _study_reporters,
)

logger = logging.getLogger(__name__)

# Map categories to decorator registry dicts
CATEGORY_REGISTRY: dict[str, dict[str, type]] = {
    'stimulus_loaders': _stimulus_loaders,
    'response_loaders': _response_loaders,
    'response_readers': _response_readers,
    'feature_extractors': _feature_extractors,
    'feature_sources': _feature_sources,
    'preparers': _preparers,
    'preparation_steps': _preparation_steps,
    'analyzers': _analyzers,
    'models': _models,
    'reporters': _reporters,
    'group_analyzers': _group_analyzers,
    'group_reporters': _group_reporters,
    'study_analyzers': _study_analyzers,
    'study_reporters': _study_reporters,
}

# Required methods per category
REQUIRED_METHODS: dict[str, list[str]] = {
    'stimulus_loaders': ['load'],
    'response_loaders': ['load'],
    'response_readers': ['read'],
    'feature_extractors': ['extract'],
    'feature_sources': ['load'],
    'preparers': ['prepare'],
    'preparation_steps': ['apply'],
    'analyzers': ['analyze'],
    'models': ['fit'],
    'reporters': ['report'],
    'qa_reporters': ['report'],
    'group_analyzers': ['analyze'],
    'group_reporters': ['report'],
    'study_analyzers': ['analyze'],
    'study_reporters': ['report'],
}


# qa_reporters uses a nested ``dict[stage, dict[name, cls]]`` storage,
# so CATEGORY_REGISTRY (flat name → cls dicts) can't hold it directly.
# The helpers below give validate_code / register_code / _rollback a
# matching snapshot + diff + undo view, keyed by ``(stage, name)``.

def _qa_keys() -> set[tuple[str, str]]:
    """Flatten ``_qa_reporters`` to ``(stage, name)`` pairs."""
    return {
        (stage, name)
        for stage, plugins in _qa_reporters.items()
        for name in plugins
    }


def _qa_cls_ids() -> dict[tuple[str, str], int]:
    return {
        (stage, name): id(cls)
        for stage, plugins in _qa_reporters.items()
        for name, cls in plugins.items()
    }


# Snapshot the full pre-exec contents of every registry. Rollback uses
# the captured class objects to restore re-registrations (same name,
# different class) — diffing keys alone leaves those in place, which
# violates validate_code()'s "doesn't persist" contract.

def _take_snapshot() -> dict[str, dict[str, type]]:
    """Deep-copy ``CATEGORY_REGISTRY`` contents (cat → ``{name: cls}``)."""
    return {cat: dict(reg) for cat, reg in CATEGORY_REGISTRY.items()}


def _rollback(originals: dict[str, dict[str, type]]) -> None:
    """Restore each flat registry to its pre-exec contents.

    Drops any keys added during exec **and** restores any class object
    that was replaced (same name, new class) so the live registry is
    indistinguishable from its pre-call state.
    """
    for cat, original_reg in originals.items():
        reg = CATEGORY_REGISTRY[cat]
        # Drop new keys
        for k in list(reg.keys()):
            if k not in original_reg:
                del reg[k]
        # Restore replaced classes
        for k, original_cls in original_reg.items():
            if reg.get(k) is not original_cls:
                reg[k] = original_cls


def _qa_take_snapshot() -> dict[str, dict[str, type]]:
    """Deep-copy ``_qa_reporters`` (stage → ``{name: cls}``)."""
    return {stage: dict(plugins) for stage, plugins in _qa_reporters.items()}


def _qa_rollback(originals: dict[str, dict[str, type]]) -> None:
    """Restore ``_qa_reporters`` to its pre-exec contents — drops new
    ``(stage, name)`` entries AND restores any replaced class."""
    # Drop entries added during exec
    for stage in list(_qa_reporters.keys()):
        plugins = _qa_reporters[stage]
        original_plugins = originals.get(stage, {})
        for name in list(plugins.keys()):
            if name not in original_plugins:
                del plugins[name]
        if not plugins:
            del _qa_reporters[stage]
    # Restore replaced + reinstate entries that exec removed
    for stage, original_plugins in originals.items():
        bucket = _qa_reporters.setdefault(stage, {})
        for name, original_cls in original_plugins.items():
            if bucket.get(name) is not original_cls:
                bucket[name] = original_cls


def get_modules_dir() -> Path:
    """Return the user modules directory, creating it if needed.

    Resolution order:
    1. ``$FMRIFLOW_MODULES_DIR`` (legacy env var, still honoured).
    2. ``$FMRIFLOW_HOME/addons/modules/`` (new home).
    3. Legacy ``~/.fmriflow/modules/`` if it exists with content
       and the new dir is still empty (migration grace).
    """
    custom = os.environ.get('FMRIFLOW_MODULES_DIR')
    if custom:
        d = Path(custom)
        d.mkdir(parents=True, exist_ok=True)
        return d
    from fmriflow.core import paths
    new = paths.addons_dir("modules")
    legacy = paths.legacy_modules_root()
    if legacy.is_dir() and any(legacy.iterdir()) and not any(new.iterdir()):
        return legacy
    return new


def validate_code(code: str, category: str | None = None) -> dict[str, Any]:
    """Validate module code without persisting or registering it.

    Returns a dict with:
      valid: bool
      errors: list[str]
      warnings: list[str]
      module_name: str | None
      class_name: str | None
      category: str | None   (detected or confirmed)
      params: dict | None
    """
    result: dict[str, Any] = {
        'valid': False,
        'errors': [],
        'warnings': [],
        'module_name': None,
        'class_name': None,
        'category': category,
        'params': None,
    }

    # Step 1: syntax check
    try:
        compiled = compile(code, '<user_module>', 'exec')
    except SyntaxError as e:
        result['errors'].append(f"Syntax error on line {e.lineno}: {e.msg}")
        return result

    # Step 2: snapshot every registry's full contents so we can detect
    # changes (new keys OR re-registered classes) AND undo them in
    # step 7.
    originals = _take_snapshot()
    qa_originals = _qa_take_snapshot()

    # Step 3: exec in controlled namespace
    try:
        exec(compiled)
    except Exception as e:
        result['errors'].append(f"Execution error: {e}")
        # Roll back any partial registrations
        _rollback(originals)
        _qa_rollback(qa_originals)
        return result

    # Step 4: find what was registered (new key OR replaced class)
    detected_category = None
    detected_name = None
    detected_cls = None
    detected_stage: str | None = None

    for cat, reg in CATEGORY_REGISTRY.items():
        original_reg = originals[cat]
        new_names = set(reg.keys()) - set(original_reg.keys())
        # Also detect re-registered modules (same key, different class object)
        if not new_names:
            for k, v in reg.items():
                if k in original_reg and v is not original_reg[k]:
                    new_names = {k}
                    break
        if new_names:
            if detected_category is not None:
                result['warnings'].append(
                    f"Module registered in multiple categories: {detected_category}, {cat}")
            detected_category = cat
            detected_name = next(iter(new_names))
            detected_cls = reg[detected_name]

    # qa_reporters: nested ``dict[stage, dict[name, cls]]`` storage.
    # Check separately for new (stage, name) entries.
    new_qa: set[tuple[str, str]] = set()
    for stage, plugins in _qa_reporters.items():
        original_plugins = qa_originals.get(stage, {})
        for name, cls in plugins.items():
            if name not in original_plugins or cls is not original_plugins[name]:
                new_qa.add((stage, name))
    if new_qa:
        if detected_category is not None:
            result['warnings'].append(
                f"Module registered in multiple categories: "
                f"{detected_category}, qa_reporters")
        stage, name = next(iter(new_qa))
        detected_category = 'qa_reporters'
        detected_name = name
        detected_stage = stage
        detected_cls = _qa_reporters[stage][name]

    if detected_cls is None:
        result['errors'].append(
            "No decorated module class found. "
            "Make sure you use the correct decorator (e.g. @feature_extractor(\"name\")).")
        _rollback(originals)
        _qa_rollback(qa_originals)
        return result

    # Category mismatch check
    if category and detected_category != category:
        result['warnings'].append(
            f"Expected category '{category}' but module registered as '{detected_category}'")

    result['module_name'] = detected_name
    result['class_name'] = detected_cls.__name__
    result['category'] = detected_category
    if detected_stage is not None:
        result['stage'] = detected_stage

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
    from fmriflow.modules._schema import extract_schema
    result['params'] = extract_schema(detected_cls)

    # Step 7: check for name collision with built-in modules
    # (Only warn if the name was already present before exec)
    if detected_category == 'qa_reporters':
        if detected_name in qa_originals.get(detected_stage or '', {}):
            result['warnings'].append(
                f"Module '{detected_name}' already exists in qa_reporters "
                f"(stage={detected_stage}). Saving will override the "
                f"existing module.")
    elif detected_name in originals.get(detected_category, {}):
        result['warnings'].append(
            f"Module '{detected_name}' already exists in '{detected_category}'. "
            f"Saving will override the existing module.")

    # Roll back the registration — we only validate here, don't persist
    _rollback(originals)
    _qa_rollback(qa_originals)

    if not result['errors']:
        result['valid'] = True

    return result


def register_code(code: str) -> tuple[str, str, str]:
    """Execute module code and register it in the live registry.

    Returns ``(module_name, class_name, category)``. Raises
    ``ValueError`` if registration fails. For qa_reporters the
    category is the literal string ``"qa_reporters"``; the stage the
    reporter attached to lives on ``cls.stage`` (set by the
    decorator).
    """
    originals = _take_snapshot()
    qa_originals = _qa_take_snapshot()

    try:
        exec(compile(code, '<user_module>', 'exec'), {"__name__": "fmriflow_user_module"})
    except Exception as e:
        _rollback(originals)
        _qa_rollback(qa_originals)
        raise ValueError(f"Failed to execute module code: {e}") from e

    for cat, reg in CATEGORY_REGISTRY.items():
        original_reg = originals[cat]
        new_names = set(reg.keys()) - set(original_reg.keys())
        # Also detect re-registered modules (same key, different class object)
        if not new_names:
            for k, v in reg.items():
                if k in original_reg and v is not original_reg[k]:
                    new_names = {k}
                    break
        if new_names:
            name = next(iter(new_names))
            cls = reg[name]
            return name, cls.__name__, cat

    # qa_reporters — nested storage, same diff shape as above.
    for stage, plugins in _qa_reporters.items():
        original_plugins = qa_originals.get(stage, {})
        for name, cls in plugins.items():
            if name not in original_plugins or cls is not original_plugins[name]:
                return name, cls.__name__, 'qa_reporters'

    raise ValueError("No decorated module class found in the code.")


def save_module(code: str, name: str, category: str) -> Path:
    """Save module code to disk and register it.

    Returns the file path where the module was saved.
    """
    modules_dir = get_modules_dir()
    filepath = modules_dir / f"{name}.py"
    filepath.write_text(code)
    logger.info("Saved user module: %s -> %s", name, filepath)
    return filepath


def delete_module(name: str) -> bool:
    """Delete a user module file and unregister it.

    Returns True if the file existed and was deleted.
    """
    modules_dir = get_modules_dir()
    filepath = modules_dir / f"{name}.py"

    # Find and unregister from decorator registries
    for cat, reg in CATEGORY_REGISTRY.items():
        if name in reg:
            del reg[name]
            logger.info("Unregistered module: %s from %s", name, cat)
    # qa_reporters live under nested stage keys.
    for stage in list(_qa_reporters.keys()):
        plugins = _qa_reporters[stage]
        if name in plugins:
            del plugins[name]
            logger.info(
                "Unregistered qa_reporter: %s (stage=%s)", name, stage)
            if not plugins:
                del _qa_reporters[stage]

    if filepath.is_file():
        filepath.unlink()
        logger.info("Deleted user module file: %s", filepath)
        return True
    return False


def list_user_modules() -> list[dict[str, Any]]:
    """List all user modules from the modules directory."""
    modules_dir = get_modules_dir()
    result = []

    for py_file in sorted(modules_dir.glob('*.py')):
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


def get_user_module_code(name: str) -> str | None:
    """Return the source code for a user module, or None if not found."""
    modules_dir = get_modules_dir()
    filepath = modules_dir / f"{name}.py"
    if filepath.is_file():
        return filepath.read_text()
    return None


def discover_user_modules(modules_dir: Path | None = None) -> int:
    """Load all user modules from the modules directory.

    Returns the number of modules successfully loaded.
    """
    if modules_dir is None:
        modules_dir = get_modules_dir()

    if not modules_dir.is_dir():
        return 0

    loaded = 0
    for py_file in sorted(modules_dir.glob('*.py')):
        try:
            code = py_file.read_text()
            # Run each addon as its own registered module: its imports and helpers
            # stay visible to its classes, and inspect.getfile() finds the file
            # (the web UI shows node sources through it).
            module = types.ModuleType(f"fmriflow_user_module_{py_file.stem}")
            module.__file__ = str(py_file)
            sys.modules[module.__name__] = module
            exec(compile(code, str(py_file), 'exec'), module.__dict__)
            logger.info("Loaded user module: %s", py_file.stem)
            loaded += 1
        except Exception as e:
            logger.warning("Failed to load user module %s: %s", py_file.stem, e)

    return loaded
