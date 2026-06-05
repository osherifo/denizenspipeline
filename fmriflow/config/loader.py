"""Configuration loading: YAML parsing, env var resolution, inheritance."""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path

import yaml

from fmriflow.config.defaults import DEFAULT_CONFIG
from fmriflow.config.schema import validate_config, validate_group_config
from fmriflow.core.subject_db import resolve_subject_config
from fmriflow.exceptions import ConfigError


def load_config(path: str | Path) -> dict:
    """Load and fully resolve a YAML config file.

    Steps:
    1. Load YAML
    2. Resolve inheritance chain
    3. Merge with defaults
    4. Resolve environment variables
    5. Validate

    Parameters
    ----------
    path : str or Path
        Path to the experiment YAML config.

    Returns
    -------
    dict
        Fully resolved configuration.

    Raises
    ------
    ConfigError
        If the config is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(path) as f:
        config = yaml.safe_load(f) or {}

    # Resolve inheritance
    config = load_config_with_inheritance(config, path.parent)

    # Merge with defaults
    config = merge_configs(DEFAULT_CONFIG, config)

    # Resolve environment variables
    config = resolve_env_vars(config)

    # Resolve subject config from subject database (fills in missing fields)
    config = resolve_subject_config(config, config_dir=path.parent)

    # Validate
    errors = validate_config(config)
    if errors:
        raise ConfigError(errors)

    return config


def load_config_with_inheritance(config: dict, base_dir: Path) -> dict:
    """Resolve the `inherit` chain in a config.

    Parameters
    ----------
    config : dict
        Config that may contain an `inherit` key.
    base_dir : Path
        Base directory for resolving relative inherit paths.

    Returns
    -------
    dict
        Config with all inherited values merged.
    """
    if "inherit" not in config:
        return config

    parent_path = base_dir / config.pop("inherit")
    if not parent_path.exists():
        raise ConfigError(f"Inherited config not found: {parent_path}")

    with open(parent_path) as f:
        parent_config = yaml.safe_load(f) or {}

    # Recurse: parent may also inherit
    parent_config = load_config_with_inheritance(parent_config, parent_path.parent)

    # Child overrides parent
    return merge_configs(parent_config, config)


def merge_configs(base: dict, override: dict) -> dict:
    """Deep-merge two config dicts. Override wins for scalar values.

    Parameters
    ----------
    base : dict
        Base/default configuration.
    override : dict
        Override configuration (takes precedence).

    Returns
    -------
    dict
        Merged configuration.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def resolve_env_vars(config: dict) -> dict:
    """Resolve ${ENV_VAR} and ${ENV_VAR:default} patterns in string values.

    Parameters
    ----------
    config : dict
        Config with potential env var references.

    Returns
    -------
    dict
        Config with env vars resolved.
    """
    if isinstance(config, dict):
        return {k: resolve_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [resolve_env_vars(v) for v in config]
    elif isinstance(config, str):
        return _resolve_env_string(config)
    return config


_ENV_PATTERN = re.compile(r'\$\{([^}]+)\}')


def _resolve_env_string(s: str) -> str:
    """Resolve environment variable references in a string.

    Supports:
        ${VAR}           — required, raises if not set
        ${VAR:default}   — uses default if VAR not set
    """
    def replacer(match):
        expr = match.group(1)
        if ':' in expr:
            var_name, default = expr.split(':', 1)
            return os.environ.get(var_name.strip(), default.strip())
        else:
            var_name = expr.strip()
            value = os.environ.get(var_name)
            if value is None:
                return match.group(0)  # Leave unresolved
            return value

    return _ENV_PATTERN.sub(replacer, s)


def load_study_config(path: str | Path) -> dict:
    """Load and validate a study-scope YAML config.

    Top-level shape only — deep checks (referenced group YAMLs load?
    each has a top-level ``group:``?) happen inside
    :meth:`StudyOrchestrator._collect_groups`.
    """
    from fmriflow.config.schema import validate_study_config

    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Study config file not found: {path}")

    with open(path) as f:
        config = yaml.safe_load(f) or {}

    config = load_config_with_inheritance(config, path.parent)
    config = resolve_env_vars(config)
    # Stash the source path so StudyOrchestrator (or anything else that
    # gets a bare dict) can resolve relative ``groups[i].config`` paths
    # against the study YAML's own directory.
    config.setdefault('_source_path', str(path.resolve()))

    errors = validate_study_config(config)
    if errors:
        raise ConfigError(errors)

    return config


def load_group_config(path: str | Path) -> dict:
    """Load and validate a group-scope YAML config.

    Mirrors :func:`load_config` but skips the subject-pipeline schema
    (the group config does not carry ``experiment`` / ``subject`` at the
    root — those are filled in per-subject from ``subject_template``).

    Subject configs derived from the group config are validated against
    :func:`fmriflow.config.schema.validate_config` at fan-out time by
    :class:`fmriflow.group_orchestrator.GroupOrchestrator`.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Group config file not found: {path}")

    with open(path) as f:
        config = yaml.safe_load(f) or {}

    config = load_config_with_inheritance(config, path.parent)
    config = resolve_env_vars(config)

    errors = validate_group_config(config)
    if errors:
        raise ConfigError(errors)

    return config
