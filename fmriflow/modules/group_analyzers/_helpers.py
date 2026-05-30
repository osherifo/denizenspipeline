"""Shared helpers for group analyzers."""

from __future__ import annotations

from typing import Any

from fmriflow.context import PipelineContext


def resolve_subject_key(ctx: PipelineContext | None, key: str) -> Any | None:
    """Resolve a dotted path into a subject's :class:`PipelineContext`.

    ``ctx.get(key)`` only does a flat lookup against the context store, but
    subject artifacts are nested objects (e.g. ``result.scores`` is the
    ``scores`` attribute of the ``ModelResult`` stored under ``result``).
    This helper handles both: the first segment is a context key, the
    remaining segments are attribute / item lookups.

    Returns None if any part of the path is missing.
    """
    if ctx is None:
        return None
    parts = key.split(".")
    if not ctx.has(parts[0]):
        return None
    obj: Any = ctx.get(parts[0])
    for part in parts[1:]:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            obj = getattr(obj, part, None)
    return obj


def my_cfg(config: dict, name: str) -> dict:
    """Pull the params block for a named group analyzer / reporter entry.

    Group config has shape::

        group_analyze:
          - name: voxelwise_mean
            params:
              input_key: result.scores

    Returns ``{}`` if the section / params are absent.
    """
    for section in ("group_analyze", "group_report"):
        for entry in config.get(section, []) or []:
            if entry.get("name") == name:
                return entry.get("params", {}) or {}
    return {}
