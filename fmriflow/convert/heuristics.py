"""Heuristic registry — discover, validate, match, and manage heudiconv
heuristic files.

Heuristics live in a directory (default: ``~/.fmriflow/heuristics/``,
overridable via ``FMRIFLOW_HEURISTICS_DIR``).  Each heuristic is a Python
file with an optional companion YAML sidecar containing metadata.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fmriflow.convert.errors import HeuristicError
from fmriflow.convert.manifest import HeuristicRef, ScannerInfo

logger = logging.getLogger(__name__)

DEFAULT_HEURISTICS_DIR = Path("heuristics")


def _heuristics_dir() -> Path:
    """Return the heuristics registry directory, creating it if needed.

    Defaults to ``./heuristics/`` in the current working directory.
    Override with the ``FMRIFLOW_HEURISTICS_DIR`` environment variable.
    """
    d = Path(os.environ.get("FMRIFLOW_HEURISTICS_DIR", str(DEFAULT_HEURISTICS_DIR)))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── HeuristicInfo ────────────────────────────────────────────────────────

@dataclass
class HeuristicInfo:
    """Metadata about a registered heuristic."""

    name: str
    path: Path
    description: str | None = None
    scanner_pattern: str | None = None
    site: str | None = None
    author: str | None = None
    version: str | None = None
    tasks: list[str] | None = None
    notes: str | None = None


# ── Registry operations ─────────────────────────────────────────────────

def list_heuristics(scanner_pattern: str | None = None) -> list[HeuristicInfo]:
    """List available heuristics, optionally filtered by scanner pattern."""
    hdir = _heuristics_dir()
    results = []

    for py_file in sorted(hdir.glob("*.py")):
        info = _load_heuristic_info(py_file)
        if scanner_pattern and info.scanner_pattern:
            if scanner_pattern.lower() not in info.scanner_pattern.lower():
                continue
        results.append(info)

    return results


def get_heuristic(name: str) -> Path:
    """Return the path to a named heuristic file.

    Raises HeuristicError if not found.
    """
    hdir = _heuristics_dir()
    path = hdir / f"{name}.py"
    if path.is_file():
        return path

    available = [p.stem for p in hdir.glob("*.py")]
    raise HeuristicError(
        f"Heuristic '{name}' not found in {hdir}. "
        f"Available: {', '.join(available) or '(none)'}",
        subject="",
    )


def resolve_heuristic(name_or_path: str) -> Path:
    """Resolve a heuristic name or path to an absolute file path.

    If *name_or_path* is an existing file, return it directly.
    Otherwise, look it up in the registry.
    """
    p = Path(name_or_path)
    if p.is_file():
        return p.resolve()
    return get_heuristic(name_or_path)


def match_heuristic(scanner: ScannerInfo) -> HeuristicInfo | None:
    """Auto-select a heuristic based on scanner metadata.

    Matches scanner manufacturer + model against registered heuristic
    ``scanner_pattern`` fields.  Returns the best match, or ``None``.
    """
    if not scanner or (not scanner.manufacturer and not scanner.model):
        return None

    scanner_str = " ".join(
        s for s in [scanner.manufacturer, scanner.model] if s
    ).lower()

    for info in list_heuristics():
        if info.scanner_pattern and info.scanner_pattern.lower() in scanner_str:
            return info

    return None


def register_heuristic(
    path: str | Path,
    name: str | None = None,
    scanner_pattern: str | None = None,
    description: str | None = None,
    **metadata: Any,
) -> HeuristicInfo:
    """Copy a heuristic file into the registry and create its sidecar.

    Returns the ``HeuristicInfo`` for the registered heuristic.
    """
    src = Path(path)
    if not src.is_file():
        raise HeuristicError(
            f"Heuristic file not found: {src}",
            subject="",
        )

    hdir = _heuristics_dir()
    heuristic_name = name or src.stem
    dest = hdir / f"{heuristic_name}.py"

    # Copy the heuristic file
    shutil.copy2(src, dest)

    # Build sidecar
    sidecar_data: dict[str, Any] = {"name": heuristic_name}
    if description:
        sidecar_data["description"] = description
    if scanner_pattern:
        sidecar_data["scanner_pattern"] = scanner_pattern
    sidecar_data.update(metadata)

    sidecar_path = hdir / f"{heuristic_name}.yaml"
    sidecar_path.write_text(yaml.dump(sidecar_data, default_flow_style=False))

    logger.info("Registered heuristic '%s' at %s", heuristic_name, dest)
    return _load_heuristic_info(dest)


def read_heuristic_source(name: str) -> str:
    """Return the Python source code of a registered heuristic."""
    path = get_heuristic(name)
    return path.read_text()



def save_heuristic_code(name: str, code: str) -> HeuristicInfo:
    """Write *code* to the heuristic file for *name*.

    If the file already exists it is overwritten (edit).
    If it does not exist a new heuristic is created.
    Returns the ``HeuristicInfo`` for the saved file.
    """
    hdir = _heuristics_dir()
    dest = hdir / f"{name}.py"
    dest.write_text(code)
    logger.info("Saved heuristic '%s' at %s", name, dest)
    return _load_heuristic_info(dest)


def get_heuristic_template(name: str = "my_study") -> str:
    """Return the skeleton heudiconv template source code."""
    from fmriflow.convert.heuristic_template import render_template
    return render_template(name=name)


def remove_heuristic(name: str) -> None:
    """Remove a heuristic and its sidecar from the registry."""
    hdir = _heuristics_dir()
    py_file = hdir / f"{name}.py"
    yaml_file = hdir / f"{name}.yaml"

    if not py_file.exists():
        raise HeuristicError(
            f"Heuristic '{name}' not found in registry.",
            subject="",
        )

    py_file.unlink()
    if yaml_file.exists():
        yaml_file.unlink()
    logger.info("Removed heuristic '%s'", name)


# ── Building HeuristicRef from a path ───────────────────────────────────

def build_heuristic_ref(name_or_path: str) -> HeuristicRef:
    """Build a ``HeuristicRef`` for recording in the manifest."""
    path = resolve_heuristic(name_or_path)
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    # Try to load sidecar for metadata
    info = _load_heuristic_info(path)

    return HeuristicRef(
        name=info.name,
        path=str(path),
        content_hash=content_hash,
        scanner_pattern=info.scanner_pattern,
        description=info.description,
    )


# ── Internal helpers ─────────────────────────────────────────────────────

def _load_heuristic_info(py_path: Path) -> HeuristicInfo:
    """Load heuristic metadata from a YAML sidecar (if present)."""
    name = py_path.stem
    sidecar = py_path.with_suffix(".yaml")

    info = HeuristicInfo(name=name, path=py_path)

    if sidecar.is_file():
        try:
            data = yaml.safe_load(sidecar.read_text()) or {}
            info.description = data.get("description")
            info.scanner_pattern = data.get("scanner_pattern")
            info.site = data.get("site")
            info.author = data.get("author")
            info.version = data.get("version")
            info.tasks = data.get("tasks")
            info.notes = data.get("notes")
        except Exception:
            logger.warning("Could not parse sidecar %s", sidecar, exc_info=True)

    return info
