"""Preflight checks for registered preproc workflows (and later, transforms).

A workflow declares its hard requirements at class level:

- ``REQUIRED_PYTHON`` — PEP 508 requirement strings (e.g. ``["nipype>=1.8"]``).
- ``REQUIRED_TOOLS`` — executables that must be on ``PATH`` (e.g. ``["mcflirt"]``).
- ``REQUIRED_ENV`` — env vars that must be set, and if their value
  looks like a filesystem path, that path must exist.

``preflight(workflow)`` runs all three checks and returns a structured
``PreflightResult``. The UI calls this on workflow-select so the user
sees "ready" or "missing FSL" *before* clicking Run, and the launch
endpoint calls it again before registering the run so a missing dep
can't leave a half-spawned subprocess in the registry.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of a preflight check.

    ``errors`` are hard blockers (registration / launch refused).
    ``warnings`` are advisory (rendered in the UI but don't block).
    """

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Individual check helpers (also exported for narrow callers) ────


def check_python_packages(requirements: list[str]) -> list[str]:
    """Return a list of human-readable errors for missing / mismatched packages.

    Accepts PEP 508 requirement strings. Uses ``packaging`` if available
    for a real version-spec match; falls back to a name-only existence
    check otherwise (packaging ships with pip so this fallback is
    rarely exercised, but keeps the helper usable in minimal envs).
    """
    errors: list[str] = []
    try:
        from packaging.requirements import Requirement
        from packaging.version import Version
    except ImportError:  # pragma: no cover — packaging is ubiquitous
        Requirement = None  # type: ignore[assignment]
        Version = None  # type: ignore[assignment]

    for req_str in requirements:
        if Requirement is None:
            # Fallback: parse just the bare name.
            name = req_str.split(";")[0].split("=")[0].split(">")[0].split("<")[0].strip()
            try:
                importlib_metadata.version(name)
            except importlib_metadata.PackageNotFoundError:
                errors.append(
                    f"Missing Python package '{name}' (required: {req_str}). "
                    f"Install with: pip install '{req_str}'"
                )
            continue

        try:
            req = Requirement(req_str)
        except Exception as e:
            errors.append(f"Could not parse requirement '{req_str}': {e}")
            continue

        try:
            installed = importlib_metadata.version(req.name)
        except importlib_metadata.PackageNotFoundError:
            errors.append(
                f"Missing Python package '{req.name}' (required: {req_str}). "
                f"Install with: pip install '{req_str}'"
            )
            continue

        if req.specifier and not req.specifier.contains(Version(installed), prereleases=True):
            errors.append(
                f"Python package '{req.name}' version {installed} does not match "
                f"required spec '{req.specifier}'. Reinstall with: pip install '{req_str}'"
            )

    return errors


def check_tools(tools: list[str]) -> list[str]:
    """Return errors for executables not found on PATH."""
    errors: list[str] = []
    for tool in tools:
        if shutil.which(tool) is None:
            errors.append(
                f"Missing executable '{tool}' on PATH. "
                f"Install the upstream package that provides it (e.g. FSL, ANTs, FreeSurfer)."
            )
    return errors


def check_env(env_vars: list[str]) -> list[str]:
    """Return errors for unset env vars; also checks path existence
    for vars whose value looks like a filesystem path.

    "Looks like a path" is intentionally fuzzy: an absolute path, or
    a value containing ``/`` and pointing at an existing parent, gets
    the path-exists check. Everything else just gets the "set" check.
    """
    errors: list[str] = []
    for var in env_vars:
        value = os.environ.get(var)
        if value is None or value == "":
            errors.append(f"Required environment variable '{var}' is not set.")
            continue
        if value.startswith("/") or value.startswith("~"):
            expanded = Path(value).expanduser()
            if not expanded.exists():
                errors.append(
                    f"Environment variable '{var}' points to a non-existent path: {value}"
                )
    return errors


# ── Top-level entry point ──────────────────────────────────────────


def preflight(workflow: Any) -> PreflightResult:
    """Run all three checks against a workflow's REQUIRED_* attributes.

    The workflow can be a class or an instance — only class attributes
    are read. Missing attributes default to empty lists (treated as
    "no requirements").
    """
    required_python = list(getattr(workflow, "REQUIRED_PYTHON", []) or [])
    required_tools = list(getattr(workflow, "REQUIRED_TOOLS", []) or [])
    required_env = list(getattr(workflow, "REQUIRED_ENV", []) or [])

    errors = (
        check_python_packages(required_python)
        + check_tools(required_tools)
        + check_env(required_env)
    )

    # Container-bound workflows are advisory-warned, not blocked — the
    # launcher decides at run-time whether docker/singularity is
    # available.
    warnings: list[str] = []
    container = getattr(workflow, "CONTAINER", None)
    if container:
        warnings.append(
            f"Workflow is container-bound ({container}); preflight only checked "
            f"host environment. The launcher must have docker or singularity available."
        )

    return PreflightResult(ok=not errors, errors=errors, warnings=warnings)
