"""StudyPCCorrelationBar — per-PC scatter + bar across subjects.

Reads a ``(n_subjects, n_components)`` correlation matrix produced by
``semantic_pc_correlation`` and plots a per-PC scatter with the
across-subject mean overlaid. One coloured marker per subject per PC,
one bar per PC for the across-subject mean. A dotted line indicates
the 95th-percentile of a permutation null derived from per-PC
sign-flipping when ``permutations:`` is set, giving a one-sided
significance band on each bar.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_reporter
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_reporter("study_pc_correlation_bar")
class StudyPCCorrelationBarReporter:
    """Per-PC correlation chart across subjects."""

    name = "study_pc_correlation_bar"
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "study.semantic_pc_correlation",
            "description": (
                "Study-artifact key for the (n_subjects, n_components) "
                "correlation matrix."
            ),
        },
        "n_components": {
            "type": "int",
            "default": 10,
            "description": "Maximum number of PCs to display.",
        },
        "permutations": {
            "type": "int",
            "default": 0,
            "description": (
                "If >0, draw a 95th-percentile null line from "
                "sign-flip permutations of the per-subject correlations."
            ),
        },
        "ylim": {
            "type": "list[float]",
            "default": [-0.2, 1.0],
            "description": "Y axis range as [low, high].",
        },
        "figsize": {
            "type": "list[float]",
            "default": [8.0, 4.5],
            "description": "matplotlib figure size in inches.",
        },
        "dpi": {"type": "int", "default": 150, "min": 50},
        "filename": {
            "type": "str",
            "default": "fig5_semantic_pc_correlation.png",
            "description": "Output PNG filename.",
        },
    }

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key", "study.semantic_pc_correlation")
        if not study.has(input_key):
            logger.warning(
                "study_pc_correlation_bar: '%s' not in study artifacts — "
                "did semantic_pc_correlation run?", input_key)
            return {}

        matrix = np.asarray(study.get(input_key))      # (n_subj, K)
        if matrix.ndim != 2:
            logger.warning(
                "study_pc_correlation_bar: expected 2-D matrix, got shape %s",
                matrix.shape)
            return {}
        n_components = min(int(cfg.get("n_components", 10)), matrix.shape[1])
        sub_matrix = matrix[:, :n_components]
        meta_key = f"{input_key}.meta"
        subjects = (
            (study.get(meta_key) or {}).get("subjects")
            if study.has(meta_key) else None
        )
        if subjects is None or len(subjects) != sub_matrix.shape[0]:
            subjects = [f"S{i+1}" for i in range(sub_matrix.shape[0])]

        try:
            import matplotlib
            matplotlib.use("Agg", force=True)
            import matplotlib.pyplot as plt
        except ImportError as exc:
            logger.warning(
                "study_pc_correlation_bar: matplotlib not importable (%s) "
                "— skipping", exc)
            return {}

        figsize = tuple(cfg.get("figsize", [8.0, 4.5]))
        fig, ax = plt.subplots(figsize=figsize, dpi=cfg.get("dpi", 150))

        x = np.arange(1, n_components + 1)
        means = np.nanmean(sub_matrix, axis=0)

        ax.bar(x, means, color="lightgrey", edgecolor="dimgrey",
               width=0.7, zorder=1, label="across-subject mean")

        cmap = plt.get_cmap("tab10")
        for i, sub in enumerate(subjects):
            ax.scatter(x, sub_matrix[i, :], marker="D",
                       s=42, color=cmap(i % 10), edgecolor="black",
                       linewidth=0.5, label=sub, zorder=2)

        n_perm = int(cfg.get("permutations", 0))
        if n_perm > 0 and sub_matrix.shape[0] > 1:
            rng = np.random.default_rng(0)
            null = np.empty((n_perm, n_components))
            for j in range(n_perm):
                signs = rng.choice([-1.0, 1.0], size=sub_matrix.shape[0])
                null[j] = np.nanmean(sub_matrix * signs[:, None], axis=0)
            thresh = np.quantile(null, 0.95, axis=0)
            ax.plot(x, thresh, "k--", linewidth=1.0,
                    label="95% sign-flip null", zorder=3)

        ax.set_xlabel("Semantic principal component")
        ax.set_ylabel("Pearson r (listening vs reading projection)")
        ax.set_title("Semantic-PC consistency across modalities")
        ylim = cfg.get("ylim", [-0.2, 1.0])
        ax.set_ylim(float(ylim[0]), float(ylim[1]))
        ax.set_xticks(x)
        ax.axhline(0.0, color="black", linewidth=0.5)
        ax.legend(loc="upper right", fontsize=8, ncol=2)
        fig.tight_layout()

        outdir_str = cfg.get("output_dir") or config.get("output_dir")
        outdir = Path(outdir_str).resolve() if outdir_str else Path.cwd()
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / cfg.get(
            "filename", "fig5_semantic_pc_correlation.png")
        try:
            fig.savefig(path, dpi=cfg.get("dpi", 150))
        finally:
            plt.close(fig)
        return {"study_pc_correlation_bar": str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
