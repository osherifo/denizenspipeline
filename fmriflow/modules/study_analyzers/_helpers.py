"""Shared helpers for study analyzers + reporters.

Mirrors ``fmriflow.modules.group_analyzers._helpers`` one scope up:
``my_cfg`` pulls the params block for a named ``study_analyze`` /
``study_report`` entry; ``resolve_group_key`` walks a dotted key
against a :class:`GroupResult` (artifacts first, then attributes).
"""

from __future__ import annotations

from typing import Any

from fmriflow.core.group_types import GroupResult


def my_cfg(config: dict, name: str) -> dict:
    """Pull the params block for a named study analyzer / reporter entry.

    Study config has shape::

        study_analyze:
          - name: group_delta
            params:
              input_key: group.scores_mean
              a: reading
              b: listening

    Returns ``{}`` if the section / params are absent.
    """
    for section in ("study_analyze", "study_report"):
        for entry in config.get(section, []) or []:
            if entry.get("name") == name:
                return entry.get("params", {}) or {}
    return {}


def resolve_group_key(group: GroupResult | None, key: str) -> Any | None:
    """Resolve a dotted key against a :class:`GroupResult`.

    Tries the artifacts dict first (literal-key, then dotted walk),
    then falls back to attribute access on the GroupResult itself.
    Returns ``None`` if no path resolves.
    """
    if group is None:
        return None
    arts = group.artifacts or {}
    # Literal full-key match.
    if key in arts:
        return arts[key]
    # Dotted walk inside artifacts (first segment as artifact key,
    # remaining as attribute / dict chain on the value).
    parts = key.split(".")
    if parts[0] in arts:
        obj: Any = arts[parts[0]]
        for part in parts[1:]:
            if obj is None:
                return None
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = getattr(obj, part, None)
        return obj
    # Last resort: attribute access on the GroupResult.
    if hasattr(group, parts[0]):
        obj = getattr(group, parts[0])
        for part in parts[1:]:
            if obj is None:
                return None
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = getattr(obj, part, None)
        return obj
    return None
