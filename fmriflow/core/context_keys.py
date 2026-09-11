"""Resolve dotted keys against pipeline contexts and group results.

Two key layouts coexist in module configs:

1. **Literal dotted key**: analyzers store outputs under strings such as
   ``'analysis.fsaverage_scores'``; that exact string is the context key.
2. **Attribute walk**: ``'result.scores'`` means the ``scores`` attribute of
   the ``result`` context value (a ``ModelResult``). Dict values are walked by
   item instead of attribute.

Every resolver tries (1) first and falls back to (2), returning ``None`` when
neither resolves.
"""

from __future__ import annotations

from typing import Any


def _walk(obj: Any, parts: list[str]) -> Any | None:
    for part in parts:
        if obj is None:
            return None
        obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part, None)
    return obj


def resolve_context_key(ctx: Any, key: str) -> Any | None:
    """Resolve *key* against a :class:`~fmriflow.context.PipelineContext`."""
    if ctx is None:
        return None
    if ctx.has(key):
        return ctx.get(key)
    parts = key.split(".")
    if not ctx.has(parts[0]):
        return None
    return _walk(ctx.get(parts[0]), parts[1:])


def resolve_group_key(group: Any, key: str) -> Any | None:
    """Resolve *key* against a :class:`~fmriflow.core.group_types.GroupResult`.

    Looks in the group's artifacts first (literal key, then a walk from the
    first segment), then falls back to attributes of the result itself.
    """
    if group is None:
        return None
    arts = group.artifacts or {}
    if key in arts:
        return arts[key]
    parts = key.split(".")
    if parts[0] in arts:
        return _walk(arts[parts[0]], parts[1:])
    if hasattr(group, parts[0]):
        return _walk(getattr(group, parts[0]), parts[1:])
    return None
