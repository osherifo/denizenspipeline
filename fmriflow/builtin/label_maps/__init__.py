"""Label-map loader for fMRIPrep node friendly names.

YAML files in this directory map raw nipype node/workflow ids to
human-readable names, keyed by fMRIPrep major version. The loader
flattens the nested YAML structure into a simple ``{raw: friendly}``
dict the frontend can consume directly.
"""

from __future__ import annotations

import re
from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml

_DIR = Path(__file__).parent


def _flatten(obj: Any, out: dict[str, str]) -> None:
    """Recursively collect all ``str: str`` pairs from a nested dict."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                out[k] = v
            elif isinstance(v, dict):
                _flatten(v, out)


@lru_cache(maxsize=8)
def load_label_map(version: str) -> dict[str, str]:
    """Load and flatten the label map for a given fMRIPrep major version.

    Looks for ``fmriprep_{major}.yaml`` in this directory, where
    *major* is the integer part before the first dot (e.g. ``25`` for
    ``25.1.3``). Returns an empty dict if no file matches.
    """
    m = re.match(r"(\d+)", version)
    if not m:
        return {}
    major = m.group(1)
    path = _DIR / f"fmriprep_{major}.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    skip = {"schema_version", "source_versions", "target_config", "conventions", "patterns"}
    for section_key, section_val in data.items():
        if section_key in skip:
            continue
        _flatten(section_val, out)
    return out


def available_versions() -> list[str]:
    """Return the list of major versions with label maps on disk."""
    versions: list[str] = []
    for p in sorted(_DIR.glob("fmriprep_*.yaml")):
        m = re.match(r"fmriprep_(\d+)\.yaml", p.name)
        if m:
            versions.append(m.group(1))
    return versions
