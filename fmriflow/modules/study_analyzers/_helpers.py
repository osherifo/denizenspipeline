"""Shared helpers for study analyzers + reporters.

Mirrors ``fmriflow.modules.group_analyzers._helpers`` one scope up:
``my_cfg`` pulls the params block for a named ``study_analyze`` /
``study_report`` entry; ``resolve_group_key`` walks a dotted key
against a :class:`GroupResult` (artifacts first, then attributes).
"""

from __future__ import annotations

from typing import Any

from fmriflow.core.context_keys import resolve_group_key  # noqa: F401  (public helper)
from fmriflow.core.group_types import GroupResult  # noqa: F401


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

