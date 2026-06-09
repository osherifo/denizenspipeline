"""Shared helpers for group analyzers."""

from __future__ import annotations

from typing import Any

from fmriflow.context import PipelineContext


def resolve_subject_key(ctx: PipelineContext | None, key: str) -> Any | None:
    """Resolve a (possibly dotted) key against a subject's :class:`PipelineContext`.

    Two layouts coexist in the codebase:

    1. **Literal dotted key** — analyzers put their outputs under strings
       like ``'analysis.fsaverage_scores'``. ``ctx.put('analysis.fsaverage_scores', arr)``
       stores under that exact string. The reader calls ``ctx.get(<that exact string>)``.
    2. **Attribute walk** — ``'result.scores'`` means "the ``scores`` attribute
       of the ``result`` context value", because ``result`` holds a ``ModelResult``
       dataclass.

    This helper tries (1) first, then falls back to (2). Returns ``None`` if
    neither path resolves.
    """
    if ctx is None:
        return None
    # 1. Literal full-key lookup
    if ctx.has(key):
        return ctx.get(key)
    # 2. Attribute / dict-item walk from the first segment
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
