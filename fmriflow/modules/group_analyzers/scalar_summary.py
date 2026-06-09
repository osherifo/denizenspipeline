"""Mean ± SEM of a per-subject scalar across the group.

Standard cross-subject error-bar reduction: each subject contributes
one scalar (e.g. the correlation of two model maps), and the group
reports mean, std, and SEM.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.group_types import GroupResult
from fmriflow.modules._decorators import group_analyzer
from fmriflow.modules.group_analyzers._helpers import my_cfg, resolve_subject_key

logger = logging.getLogger(__name__)


@group_analyzer("scalar_summary")
class ScalarSummaryAnalyzer:
    """Reduce a per-subject scalar (or array → ``reduce`` op) to mean ± SEM.

    Writes a dict to ``group.<output_key>`` with keys ``mean``, ``std``,
    ``sem``, ``n_subjects``, and ``per_subject`` (a list of per-subject
    values in the same order as ``group.subjects``).
    """

    name = "scalar_summary"
    produces_subject_artifact = False
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "result.scores",
            "description": "Dotted path into each subject's context.",
        },
        "reduce": {
            "type": "str",
            "default": "mean",
            "description": (
                "How to collapse an array-valued per-subject input to a "
                "scalar: 'mean' | 'max' | 'median' | 'none' (already scalar)."
            ),
        },
        "output_key": {
            "type": "str",
            "description": "Group-artifact key for the summary dict.",
        },
    }

    _REDUCERS = {
        "mean": np.mean,
        "max": np.max,
        "median": np.median,
    }

    def analyze(self, group: GroupResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key", "result.scores")
        reduce_op = cfg.get("reduce", "mean")
        output_key = cfg.get("output_key", f"group.{input_key}.summary")

        if reduce_op not in self._REDUCERS and reduce_op != "none":
            raise ValueError(
                f"scalar_summary: invalid reduce '{reduce_op}', must be "
                f"one of: {sorted(self._REDUCERS)} or 'none'")

        values: list[float] = []
        contributing: list[str] = []
        for sr in group.subjects:
            value = resolve_subject_key(sr.context, input_key)
            if value is None:
                logger.warning(
                    "scalar_summary: subject %s missing key '%s'",
                    sr.subject, input_key)
                continue
            if reduce_op == "none":
                scalar = float(value)
            else:
                scalar = float(self._REDUCERS[reduce_op](np.asarray(value)))
            values.append(scalar)
            contributing.append(sr.subject)

        if not values:
            raise ValueError(
                f"scalar_summary: no subjects produced key '{input_key}'")

        arr = np.asarray(values)
        n = arr.size
        sem = float(arr.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
        group.put(output_key, {
            "mean": float(arr.mean()),
            "std": float(arr.std(ddof=1)) if n > 1 else 0.0,
            "sem": sem,
            "n_subjects": n,
            "per_subject": dict(zip(contributing, values)),
        })

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        reduce_op = cfg.get("reduce", "mean")
        if reduce_op not in self._REDUCERS and reduce_op != "none":
            return [
                f"scalar_summary.reduce must be one of "
                f"{sorted(self._REDUCERS)} or 'none', got '{reduce_op}'"
            ]
        return []
