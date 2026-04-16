"""Module code validation, dynamic registration, and persistence."""

from __future__ import annotations

import logging
import os
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
}


def get_modules_dir() -> Path:
    """Return the user modules directory, creating it if needed."""
    custom = os.environ.get('FMRIFLOW_MODULES_DIR')
    if custom:
        d = Path(custom)
    else:
        d = Path.home() / '.fmriflow' / 'modules'
    d.mkdir(parents=True, exist_ok=True)
    return d


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

    # Step 2: snapshot registries (keys AND identity of classes) to detect changes
    snapshots = {cat: set(reg.keys()) for cat, reg in CATEGORY_REGISTRY.items()}
    cls_snapshots = {cat: {k: id(v) for k, v in reg.items()} for cat, reg in CATEGORY_REGISTRY.items()}

    # Step 3: exec in controlled namespace
    try:
        exec(compiled)
    except Exception as e:
        result['errors'].append(f"Execution error: {e}")
        # Roll back any partial registrations
        _rollback(snapshots)
        return result

    # Step 4: find what was registered (new key OR replaced class)
    detected_category = None
    detected_name = None
    detected_cls = None

    for cat, reg in CATEGORY_REGISTRY.items():
        new_names = set(reg.keys()) - snapshots[cat]
        # Also detect re-registered modules (same key, different class object)
        if not new_names:
            for k, v in reg.items():
                if k in cls_snapshots[cat] and id(v) != cls_snapshots[cat][k]:
                    new_names = {k}
                    break
        if new_names:
            if detected_category is not None:
                result['warnings'].append(
                    f"Module registered in multiple categories: {detected_category}, {cat}")
            detected_category = cat
            detected_name = next(iter(new_names))
            detected_cls = reg[detected_name]

    if detected_cls is None:
        result['errors'].append(
            "No decorated module class found. "
            "Make sure you use the correct decorator (e.g. @feature_extractor(\"name\")).")
        _rollback(snapshots)
        return result

    # Category mismatch check
    if category and detected_category != category:
        result['warnings'].append(
            f"Expected category '{category}' but module registered as '{detected_category}'")

    result['module_name'] = detected_name
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
    from fmriflow.modules._schema import extract_schema
    result['params'] = extract_schema(detected_cls)

    # Step 7: check for name collision with built-in modules
    # (Only warn if the name was already present before exec)
    if detected_name in snapshots.get(detected_category, set()):
        result['warnings'].append(
            f"Module '{detected_name}' already exists in '{detected_category}'. "
            f"Saving will override the existing module.")

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
    """Execute module code and register it in the live registry.

    Returns (module_name, class_name, category).
    Raises ValueError if registration fails.
    """
    snapshots = {cat: set(reg.keys()) for cat, reg in CATEGORY_REGISTRY.items()}
    cls_snapshots = {cat: {k: id(v) for k, v in reg.items()} for cat, reg in CATEGORY_REGISTRY.items()}

    try:
        exec(compile(code, '<user_module>', 'exec'))
    except Exception as e:
        _rollback(snapshots)
        raise ValueError(f"Failed to execute module code: {e}") from e

    for cat, reg in CATEGORY_REGISTRY.items():
        new_names = set(reg.keys()) - snapshots[cat]
        # Also detect re-registered modules (same key, different class object)
        if not new_names:
            for k, v in reg.items():
                if k in cls_snapshots[cat] and id(v) != cls_snapshots[cat][k]:
                    new_names = {k}
                    break
        if new_names:
            name = next(iter(new_names))
            cls = reg[name]
            return name, cls.__name__, cat

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
            exec(compile(code, str(py_file), 'exec'))
            logger.info("Loaded user module: %s", py_file.stem)
            loaded += 1
        except Exception as e:
            logger.warning("Failed to load user module %s: %s", py_file.stem, e)

    return loaded
