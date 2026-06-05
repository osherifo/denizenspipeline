"""QA reporters for the ``prepare`` stage (PreparedData).

The most damaging bugs in this pipeline live here:
train/test contamination, delays applied in the wrong direction,
``feature_row_ranges`` off-by-one. These plots are designed to make
each of those bugs visually obvious.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fmriflow.core.types import PreparedData
from fmriflow.modules._decorators import qa_reporter
from fmriflow.modules.qa_reporters._base import (
    ensure_dir, feature_column_layout, mpl_figure, save_png,
)


@qa_reporter("sample_counts", stage="prepare")
class SampleCounts:
    """Train / test / dropped TR counts + shapes as JSON + bar chart."""

    name = "sample_counts"
    stage = "prepare"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: PreparedData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        info = {
            'X_train_shape': list(value.X_train.shape),
            'Y_train_shape': list(value.Y_train.shape),
            'X_test_shape':  list(value.X_test.shape),
            'Y_test_shape':  list(value.Y_test.shape),
            'n_train_trs':   int(value.X_train.shape[0]),
            'n_test_trs':    int(value.X_test.shape[0]),
            'n_features':    len(value.feature_names),
            'feature_names': list(value.feature_names),
            'feature_dims':  list(value.feature_dims),
            'delays':        list(value.delays),
            'train_runs':    list(value.train_runs),
            'test_runs':     list(value.test_runs),
        }
        sidecar = output_dir / 'sample_counts.json'
        sidecar.write_text(json.dumps(info, indent=2))

        with mpl_figure(figsize=(6.0, 3.5)) as fig:
            ax = fig.add_subplot(111)
            ax.bar(['train TRs', 'test TRs'],
                   [info['n_train_trs'], info['n_test_trs']],
                   color=['steelblue', 'goldenrod'], edgecolor='white')
            for i, v in enumerate([info['n_train_trs'], info['n_test_trs']]):
                ax.text(i, v, f'{v}', ha='center', va='bottom', fontsize=10)
            ax.set_ylabel('TR count')
            ax.set_title(
                f'sample counts — '
                f'X cols={info["X_train_shape"][1]}, '
                f'Y voxels={info["Y_train_shape"][1]}'
            )
            fig.tight_layout()
            png = save_png(fig, output_dir / 'sample_counts.png')

        return {'counts': png, 'json': str(sidecar)}


@qa_reporter("train_test_timeline", stage="prepare")
class TrainTestTimeline:
    """Per-run train/test colour-coded timeline + overlap receipt.

    Train/test contamination is the most damaging silent bug in the
    pipeline. This plot makes any overlap impossible to miss.
    """

    name = "train_test_timeline"
    stage = "prepare"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: PreparedData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        train = list(value.train_runs)
        test = list(value.test_runs)
        overlap = sorted(set(train) & set(test))
        ordered: list[str] = []
        seen: set[str] = set()
        for r in train + test:
            if r not in seen:
                ordered.append(r)
                seen.add(r)

        with mpl_figure(figsize=(max(8.0, 0.5 * len(ordered) + 2), 2.5)) as fig:
            ax = fig.add_subplot(111)
            for i, run in enumerate(ordered):
                in_train = run in train
                in_test = run in test
                color = (
                    '#d35'      if in_train and in_test else
                    'steelblue' if in_train else
                    'goldenrod'
                )
                ax.bar(i, 1, color=color, edgecolor='white')
                ax.text(i, 0.5, run, ha='center', va='center',
                        rotation=90, fontsize=8, color='white')
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(
                f'train/test split — '
                f'{len(train)} train · {len(test)} test'
                + (f' · {len(overlap)} OVERLAP' if overlap else '')
            )
            # Legend
            from matplotlib.patches import Patch
            ax.legend(handles=[
                Patch(color='steelblue', label='train'),
                Patch(color='goldenrod', label='test'),
                Patch(color='#d35',      label='in BOTH (contamination!)'),
            ], loc='upper right', fontsize=8)
            fig.tight_layout()
            png = save_png(fig, output_dir / 'train_test_timeline.png')

        receipt = {
            'train_runs': train,
            'test_runs': test,
            'overlap': overlap,
            'configured_test_runs': (config.get('split') or {}).get('test_runs'),
        }
        sidecar = output_dir / 'split_receipt.json'
        sidecar.write_text(json.dumps(receipt, indent=2))
        return {'timeline': png, 'receipt': str(sidecar)}


@qa_reporter("delay_structure_heatmap", stage="prepare")
class DelayStructureHeatmap:
    """First ~50 rows of X_train rendered as a heatmap.

    For a single feature with N delays, you should see N adjacent
    columns each shifted down by 1 TR — a staircase pattern. Anything
    else means delays aren't being applied (or are applied in the
    wrong direction).
    """

    name = "delay_structure_heatmap"
    stage = "prepare"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: PreparedData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        X = np.asarray(value.X_train)
        if X.ndim != 2 or X.size == 0:
            return {}
        n_rows = min(60, X.shape[0])
        # If X is very wide, sample columns at one-per-delayed-block so
        # the heatmap stays readable.
        layout = feature_column_layout(value)
        if layout:
            sample_cols = []
            for _, _, s, _ in layout:
                sample_cols.append(s)
            sample_cols = np.unique(np.array(sample_cols))[:80]
        else:
            sample_cols = np.linspace(
                0, X.shape[1] - 1, min(80, X.shape[1]),
            ).astype(int)
        sub = X[:n_rows][:, sample_cols]

        with mpl_figure(figsize=(8.0, 4.5)) as fig:
            ax = fig.add_subplot(111)
            ax.imshow(sub, aspect='auto', cmap='RdBu_r',
                      interpolation='nearest',
                      vmin=-np.nanmax(np.abs(sub)) if sub.size else None,
                      vmax=np.nanmax(np.abs(sub)) if sub.size else None)
            ax.set_xlabel(f'sampled X columns ({len(sample_cols)} of {X.shape[1]})')
            ax.set_ylabel('TR (first 60 of train)')
            ax.set_title('delay structure — staircase = delays applied correctly')
            fig.tight_layout()
            png = save_png(fig, output_dir / 'delay_structure.png')
        return {'heatmap': png}


@qa_reporter("feature_row_ranges", stage="prepare")
class FeatureRowRanges:
    """Visualize which X columns map to which (feature, delay).

    Catches the off-by-one in ``feature_row_ranges`` bookkeeping —
    historically the kind of bug that makes banded ridge weights map
    to the wrong feature when reporters slice them.
    """

    name = "feature_row_ranges"
    stage = "prepare"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: PreparedData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        layout = feature_column_layout(value)
        if not layout:
            return {}

        feature_names = list(value.feature_names or [])
        # Map each feature → a stable colour.
        cmap_idx = {name: i for i, name in enumerate(feature_names)}
        import matplotlib.cm as cm
        palette = cm.get_cmap('tab20', max(len(cmap_idx), 1))

        with mpl_figure(figsize=(11.0, 2.5)) as fig:
            ax = fig.add_subplot(111)
            for name, delay_idx, s, e in layout:
                color = palette(cmap_idx.get(name, 0) % palette.N)
                ax.barh(0, e - s, left=s, color=color,
                        edgecolor='white', linewidth=0.5)
                if (e - s) > 6:
                    ax.text((s + e) / 2, 0, f'{name}[d{delay_idx}]',
                            ha='center', va='center', fontsize=7,
                            color='black', rotation=0)
            ax.set_xlim(0, max(e for _, _, _, e in layout))
            ax.set_yticks([])
            ax.set_xlabel('X column index')
            ax.set_title(
                f'feature×delay → X-column mapping '
                f'({len(feature_names)} features × {len(value.delays)} delays)'
            )
            fig.tight_layout()
            png = save_png(fig, output_dir / 'feature_row_ranges.png')

        sidecar = output_dir / 'feature_row_ranges.json'
        sidecar.write_text(json.dumps([
            {'feature': name, 'delay_idx': di, 'col_start': s, 'col_end': e}
            for name, di, s, e in layout
        ], indent=2))
        return {'mapping': png, 'json': str(sidecar)}


@qa_reporter("zscore_check", stage="prepare")
class ZScoreCheck:
    """Per-column mean / std distributions on X_train, X_test, Y_train, Y_test.

    Properly z-scored data peaks at 0 mean / 1 std for train; test
    centred slightly off (since train stats are applied) is the
    expected pattern. Test centred at exactly 0 = test-set stats
    leaked into normalisation.
    """

    name = "zscore_check"
    stage = "prepare"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: PreparedData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        arrays = {
            'X_train': value.X_train,
            'X_test':  value.X_test,
            'Y_train': value.Y_train,
            'Y_test':  value.Y_test,
        }
        with mpl_figure(figsize=(10.0, 6.0)) as fig:
            for i, (label, arr) in enumerate(arrays.items()):
                arr = np.asarray(arr)
                if arr.ndim != 2 or arr.size == 0:
                    continue
                col_mean = arr.mean(axis=0)
                col_std = arr.std(axis=0)
                ax_m = fig.add_subplot(4, 2, 2 * i + 1)
                ax_s = fig.add_subplot(4, 2, 2 * i + 2)
                ax_m.hist(col_mean, bins=60, color='steelblue',
                          edgecolor='white', alpha=0.85)
                ax_m.axvline(0, color='#d35', linestyle='--', linewidth=1)
                ax_m.set_title(f'{label}: column mean (n_cols={arr.shape[1]})',
                               fontsize=10)
                ax_s.hist(col_std, bins=60, color='goldenrod',
                          edgecolor='white', alpha=0.85)
                ax_s.axvline(1, color='#d35', linestyle='--', linewidth=1)
                ax_s.set_title(f'{label}: column std', fontsize=10)
            fig.tight_layout()
            png = save_png(fig, output_dir / 'zscore_check.png')
        return {'zscore': png}
