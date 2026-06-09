"""QA reporters for the ``model`` stage (ModelResult).

Each plugin renders one diagnostic PNG (sometimes plus a JSON sidecar)
into its own directory under ``<run_dir>/qa/model/<plugin>/``.

These plugins assume only ``ModelResult`` + the run config. They run
identically during the pipeline and against a reloaded
``model.joblib`` intermediate, so a plot you add today regenerates
against last week's run.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import qa_reporter
from fmriflow.modules.qa_reporters._base import (
    banded_groups, ensure_dir, mpl_figure, save_png,
)


@qa_reporter("score_histogram", stage="model")
class ScoreHistogram:
    """Distribution of per-voxel prediction scores + percentile annotations."""

    name = "score_histogram"
    stage = "model"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: ModelResult, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        scores = np.asarray(value.scores)
        finite = scores[np.isfinite(scores)]
        n_vox = scores.size
        n_pos = int((finite > 0).sum())
        thresholds = (0.05, 0.1, 0.2, 0.3)
        frac_above = {
            f"frac_above_{t}": float((finite > t).mean()) if finite.size else 0.0
            for t in thresholds
        }
        percentiles = {
            f"p{p}": float(np.percentile(finite, p)) if finite.size else float('nan')
            for p in (50, 75, 90, 95, 99)
        }

        with mpl_figure(figsize=(8.5, 4.5)) as fig:
            ax = fig.add_subplot(111)
            ax.hist(finite, bins=80, color='steelblue', alpha=0.85, edgecolor='white')
            for p, color in (('p50', '#888'), ('p95', '#d35'), ('p99', '#922')):
                val = percentiles[p]
                if np.isfinite(val):
                    ax.axvline(val, color=color, linestyle='--', linewidth=1)
                    ax.text(val, ax.get_ylim()[1] * 0.95, f'{p}={val:.3f}',
                            color=color, fontsize=9, rotation=90,
                            va='top', ha='right')
            ax.set_xlabel('prediction score (r)')
            ax.set_ylabel('voxel count')
            ax.set_title(
                f'score histogram — n_voxels={n_vox}, n_pos={n_pos}, '
                f'mean={float(finite.mean()) if finite.size else float("nan"):.3f}, '
                f'max={float(finite.max()) if finite.size else float("nan"):.3f}'
            )
            fig.tight_layout()
            png = save_png(fig, output_dir / 'score_histogram.png')

        meta = {
            'n_voxels': int(n_vox),
            'n_pos': n_pos,
            'mean': float(finite.mean()) if finite.size else None,
            'std': float(finite.std()) if finite.size else None,
            'max': float(finite.max()) if finite.size else None,
            **percentiles,
            **frac_above,
        }
        json_path = output_dir / 'score_summary.json'
        json_path.write_text(json.dumps(meta, indent=2))
        return {'histogram': png, 'summary': str(json_path)}


@qa_reporter("score_rank_curve", stage="model")
class ScoreRankCurve:
    """Sorted scores on a log-rank X axis — long-tail shape diagnostic."""

    name = "score_rank_curve"
    stage = "model"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: ModelResult, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        scores = np.asarray(value.scores)
        finite = scores[np.isfinite(scores)]
        sorted_scores = np.sort(finite)[::-1]
        ranks = np.arange(1, sorted_scores.size + 1)

        with mpl_figure(figsize=(7.5, 4.5)) as fig:
            ax = fig.add_subplot(111)
            ax.plot(ranks, sorted_scores, color='steelblue', linewidth=1)
            ax.axhline(0, color='#888', linewidth=0.8)
            ax.set_xscale('log')
            ax.set_xlabel('voxel rank (log)')
            ax.set_ylabel('prediction score (r)')
            ax.set_title('score rank curve')
            ax.grid(True, alpha=0.3, which='both')
            fig.tight_layout()
            png = save_png(fig, output_dir / 'score_rank_curve.png')
        return {'curve': png}


@qa_reporter("alpha_histogram", stage="model")
class AlphaHistogram:
    """Selected α per voxel — peaks at the search boundary mean the
    search range is too narrow."""

    name = "alpha_histogram"
    stage = "model"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: ModelResult, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        alphas = np.asarray(value.alphas)
        # Banded-ridge writes per-band ``deltas`` (n_bands, n_voxels)
        # alongside the per-voxel best alpha.
        meta = value.metadata or {}
        deltas = meta.get('deltas')

        with mpl_figure(figsize=(8.5, 4.5)) as fig:
            ax = fig.add_subplot(111)
            data = alphas[np.isfinite(alphas)]
            log_alphas = np.log10(np.maximum(data, 1e-12))
            ax.hist(log_alphas, bins=40, color='goldenrod', alpha=0.85,
                    edgecolor='white')
            ax.set_xlabel('log10(α)')
            ax.set_ylabel('voxel count')
            ax.set_title(f'best α per voxel — n_voxels={data.size}')
            fig.tight_layout()
            png = save_png(fig, output_dir / 'alpha_histogram.png')

        out: dict[str, str] = {'histogram': png}

        if deltas is not None:
            d = np.asarray(deltas)
            if d.ndim == 2 and d.shape[0] > 0:
                with mpl_figure(figsize=(9.0, 1.0 + 1.2 * d.shape[0])) as fig:
                    n_bands = d.shape[0]
                    for bi in range(n_bands):
                        ax = fig.add_subplot(n_bands, 1, bi + 1)
                        band = d[bi][np.isfinite(d[bi])]
                        if band.size:
                            log_band = np.log10(np.maximum(band, 1e-12))
                            ax.hist(log_band, bins=40, color='teal',
                                    alpha=0.85, edgecolor='white')
                        ax.set_ylabel(f'band {bi}\nn={band.size}')
                        if bi == n_bands - 1:
                            ax.set_xlabel('log10(δ)')
                    fig.suptitle('per-band δ (banded ridge)')
                    fig.tight_layout()
                    out['per_band_delta'] = save_png(
                        fig, output_dir / 'per_band_delta.png')
        return out


@qa_reporter("weight_norms_per_band", stage="model")
class WeightNormsPerBand:
    """L2 norm of weights, broken down per feature × delay.

    Outlier columns reveal normalization bugs or a band quietly
    dominating the fit.
    """

    name = "weight_norms_per_band"
    stage = "model"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: ModelResult, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        W = np.asarray(value.weights)              # (n_cols, n_voxels)
        if W.ndim != 2:
            return {}
        col_norms = np.linalg.norm(W, axis=1)      # (n_cols,)

        groups = banded_groups(value)              # banded layout, optional
        # Fallback layout: derive (feature, delay) from feature_dims + delays.
        feature_names = list(value.feature_names or [])
        feature_dims = list(value.feature_dims or [])
        delays = list(value.delays or [1])
        per_band_norms: list[tuple[str, float]] = []
        if groups:
            for name, (s, e) in sorted(groups.items(), key=lambda kv: kv[1][0]):
                segment = col_norms[s:e]
                per_band_norms.append((str(name), float(np.linalg.norm(segment))))
        else:
            col = 0
            for name, n_dims in zip(feature_names, feature_dims):
                for di in range(len(delays)):
                    seg = col_norms[col:col + n_dims]
                    per_band_norms.append(
                        (f'{name}[d{di}]', float(np.linalg.norm(seg))))
                    col += n_dims

        with mpl_figure(figsize=(max(6.0, 0.4 * len(per_band_norms) + 2), 4.0)) as fig:
            ax = fig.add_subplot(111)
            xs = np.arange(len(per_band_norms))
            ax.bar(xs, [v for _, v in per_band_norms],
                   color='slategray', edgecolor='white')
            ax.set_xticks(xs)
            ax.set_xticklabels([n for n, _ in per_band_norms],
                               rotation=60, ha='right', fontsize=8)
            ax.set_ylabel('L2 weight norm')
            ax.set_title('per-(band|feature×delay) weight norms')
            fig.tight_layout()
            png = save_png(fig, output_dir / 'weight_norms.png')

        sidecar = output_dir / 'weight_norms.json'
        sidecar.write_text(json.dumps(
            {n: v for n, v in per_band_norms}, indent=2,
        ))
        return {'bars': png, 'json': str(sidecar)}
