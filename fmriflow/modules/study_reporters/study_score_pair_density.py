"""StudyScorePairDensity — per-subject 2-D log-density of paired voxel scores.

Reads the per-subject ``{'a': array, 'b': array}`` pairs produced by
``cross_group_score_pairs`` and renders one log-density scatter per
subject. Darker bins mark higher voxel density. The diagonal is drawn
for reference; optional ``a_threshold`` / ``b_threshold`` add dashed
significance lines (constant across subjects unless extended later).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_reporter
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_reporter("study_score_pair_density")
class StudyScorePairDensityReporter:
    """One 2-D log-density plot per subject of paired prediction scores."""

    name = "study_score_pair_density"
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "study.score_pairs",
            "description": (
                "Study-artifact key produced by ``cross_group_score_pairs``. "
                "Expects a dict ``{subject: {'a': array, 'b': array}}``."
            ),
        },
        "a_label": {
            "type": "str",
            "default": "",
            "description": (
                "X-axis label. Defaults to '<a_group> prediction accuracy' "
                "using the analyzer's meta."
            ),
        },
        "b_label": {
            "type": "str",
            "default": "",
            "description": "Y-axis label. Defaults to '<b_group> prediction accuracy'.",
        },
        "a_threshold": {
            "type": "float",
            "default": None,
            "description": (
                "Optional dashed vertical line at this x-value — voxels "
                "to the left are below significance on axis a."
            ),
        },
        "b_threshold": {
            "type": "float",
            "default": None,
            "description": "Optional dashed horizontal line at this y-value.",
        },
        "xlim": {
            "type": "list[float]",
            "default": [-0.3, 0.7],
            "description": "X-axis limits as [low, high].",
        },
        "ylim": {
            "type": "list[float]",
            "default": [-0.3, 0.7],
            "description": "Y-axis limits as [low, high].",
        },
        "bins": {
            "type": "int",
            "default": 60,
            "description": "Number of 2-D histogram bins per axis.",
        },
        "cmap": {
            "type": "str",
            "default": "Purples",
            "description": "Matplotlib colormap for the density bins.",
        },
        "figsize": {
            "type": "list[float]",
            "default": [4.5, 4.5],
            "description": "matplotlib figure size in inches.",
        },
        "dpi": {"type": "int", "default": 150, "min": 50},
        "filename_pattern": {
            "type": "str",
            "default": "score_pair_density_sub-{subject}.png",
            "description": (
                "Output filename template. ``{subject}`` is replaced with "
                "the subject id."
            ),
        },
    }

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key", "study.score_pairs")
        if not study.has(input_key):
            logger.warning(
                "study_score_pair_density: '%s' not in study artifacts — "
                "did cross_group_score_pairs run?", input_key)
            return {}

        pairs = study.get(input_key)
        if not isinstance(pairs, dict) or not pairs:
            logger.warning(
                "study_score_pair_density: '%s' is not a non-empty dict",
                input_key)
            return {}

        meta_key = f"{input_key}.meta"
        meta = study.get(meta_key) if study.has(meta_key) else {}
        a_group = meta.get("a_group", "a") if isinstance(meta, dict) else "a"
        b_group = meta.get("b_group", "b") if isinstance(meta, dict) else "b"
        a_label = cfg.get("a_label") or f"{a_group} prediction accuracy"
        b_label = cfg.get("b_label") or f"{b_group} prediction accuracy"

        try:
            import matplotlib
            matplotlib.use("Agg", force=True)
            import matplotlib.pyplot as plt
            from matplotlib.colors import LogNorm
        except ImportError as exc:
            logger.warning(
                "study_score_pair_density: matplotlib not importable (%s) "
                "— skipping", exc)
            return {}

        outdir_str = cfg.get("output_dir") or config.get("output_dir")
        outdir = Path(outdir_str).resolve() if outdir_str else Path.cwd()
        outdir.mkdir(parents=True, exist_ok=True)

        xlim = tuple(float(v) for v in cfg.get("xlim", [-0.3, 0.7]))
        ylim = tuple(float(v) for v in cfg.get("ylim", [-0.3, 0.7]))
        bins = int(cfg.get("bins", 60))
        cmap = cfg.get("cmap", "Purples")
        figsize = tuple(cfg.get("figsize", [4.5, 4.5]))
        dpi = int(cfg.get("dpi", 150))
        pattern = cfg.get(
            "filename_pattern", "score_pair_density_sub-{subject}.png")
        a_thr = cfg.get("a_threshold")
        b_thr = cfg.get("b_threshold")

        outputs: dict[str, str] = {}
        for sub, entry in pairs.items():
            if not isinstance(entry, dict):
                continue
            a = np.asarray(entry.get("a"))
            b = np.asarray(entry.get("b"))
            if a.size == 0 or b.size == 0 or a.shape != b.shape:
                logger.warning(
                    "study_score_pair_density: subject %s has bad arrays "
                    "(a=%s, b=%s) — skipping", sub, a.shape, b.shape)
                continue

            fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
            # hist2d with LogNorm gives a darker-where-denser map per the
            # paper-style 2-D density plots; clamp the lower bound so the
            # colorbar's log scale doesn't choke on empty bins.
            _, _, _, img = ax.hist2d(
                a, b,
                bins=bins,
                range=[list(xlim), list(ylim)],
                cmap=cmap,
                norm=LogNorm(vmin=1),
            )
            cbar = fig.colorbar(img, ax=ax, shrink=0.85)
            cbar.set_label("voxel count (log scale)", fontsize=9)

            ax.plot(xlim, xlim, color="0.4", linewidth=0.8, linestyle=":")
            if a_thr is not None:
                ax.axvline(float(a_thr), color="0.3",
                           linewidth=0.7, linestyle="--")
            if b_thr is not None:
                ax.axhline(float(b_thr), color="0.3",
                           linewidth=0.7, linestyle="--")
            ax.axhline(0.0, color="0.8", linewidth=0.5)
            ax.axvline(0.0, color="0.8", linewidth=0.5)

            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            ax.set_xlabel(a_label)
            ax.set_ylabel(b_label)
            ax.set_title(f"sub-{sub}  ({a.size} voxels)")
            ax.set_aspect("equal")
            fig.tight_layout()

            path = outdir / pattern.format(subject=sub)
            try:
                fig.savefig(path, dpi=dpi)
            finally:
                plt.close(fig)
            outputs[f"score_pair_density.sub-{sub}"] = str(path)

        return outputs

    def validate_config(self, config: dict) -> list[str]:
        return []
