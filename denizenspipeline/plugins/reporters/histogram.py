"""HistogramReporter — matplotlib histogram of score distribution."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from denizenspipeline.core.types import ModelResult


class HistogramReporter:
    """Generates a histogram of per-voxel prediction scores.

    Per-reporter options are read from ``config['reporting']['histogram']``:

    - **bins** (int): Number of histogram bins. Default ``50``.
    - **threshold** (float | None): Draw a vertical reference line.
    - **show_stats** (bool): Overlay mean/median/n_significant. Default ``True``.
    - **figsize** (list[int]): Figure size ``[width, height]``. Default ``[8, 5]``.
    - **dpi** (int): PNG resolution. Default ``150``.
    """

    name = "histogram"

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        opts = config.get('reporting', {}).get('histogram', {})
        bins = opts.get('bins', 50)
        threshold = opts.get('threshold', None)
        show_stats = opts.get('show_stats', True)
        figsize = tuple(opts.get('figsize', [8, 5]))
        dpi = opts.get('dpi', 150)

        scores = result.scores

        fig, ax = plt.subplots(figsize=figsize)
        ax.hist(scores, bins=bins, color='steelblue', edgecolor='white', alpha=0.85)
        ax.set_xlabel('Prediction Score (r)')
        ax.set_ylabel('Number of Voxels')
        ax.set_title('Voxelwise Prediction Accuracy')

        if threshold is not None:
            ax.axvline(threshold, color='crimson', linestyle='--', linewidth=1.5,
                       label=f'threshold = {threshold}')
            ax.legend()

        if show_stats:
            mean_score = float(scores.mean())
            median_score = float(np.median(scores))
            n_sig = int((scores > (threshold or 0)).sum()) if threshold else int((scores > 0).sum())
            stats_text = (
                f'mean = {mean_score:.4f}\n'
                f'median = {median_score:.4f}\n'
                f'n > {"threshold" if threshold else "0"} = {n_sig}'
            )
            ax.text(0.97, 0.95, stats_text, transform=ax.transAxes,
                    fontsize=9, verticalalignment='top', horizontalalignment='right',
                    bbox=dict(boxstyle='round,pad=0.4', facecolor='wheat', alpha=0.7))

        fig.tight_layout()
        path = output_dir / 'score_histogram.png'
        fig.savefig(str(path), dpi=dpi)
        plt.close(fig)

        return {'histogram': str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
