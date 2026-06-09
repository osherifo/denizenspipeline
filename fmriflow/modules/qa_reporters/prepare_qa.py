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


@qa_reporter("per_story_shape", stage="prepare")
class PerStoryShape:
    """Per-story TR counts + feature dim composition.

    Two-panel diagnostic that confirms (and visualizes) that responses
    and features ended up time-aligned per story by the time
    ``concatenate`` ran. The bare fact of reaching this stage is
    already proof that they aligned (``concatenate`` raises on
    mismatch) — this plot just makes the per-story TR landscape
    visible so you can spot a story with a wildly unexpected length,
    a misordered split, or a missing run.

    Panel 1 (left): bar per story, height = post-trim TR count
    (from ``PreparedData.metadata['run_lengths']``), coloured by
    train vs test. Each bar annotated with its TR count.

    Panel 2 (right): stacked horizontal bar showing the X column
    composition — one block per feature, width proportional to that
    feature's dim count. Annotated with feature name + dim count.
    """

    name = "per_story_shape"
    stage = "prepare"
    PARAM_SCHEMA: dict = {}

    def report(
        self, value: PreparedData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)

        run_lengths = {}
        meta = getattr(value, 'metadata', None) or {}
        if isinstance(meta, dict):
            run_lengths = dict(meta.get('run_lengths') or {})

        train_runs = list(value.train_runs)
        test_runs = list(value.test_runs)
        if not run_lengths:
            # Older runs may pre-date the metadata stash; fall back to
            # length-of-zero so the plot still emits a structural view.
            run_lengths = {r: 0 for r in train_runs + test_runs}

        # Preserve config order: train first, then test.
        ordered = [r for r in train_runs if r in run_lengths] + \
                  [r for r in test_runs if r in run_lengths]
        # Tail any runs in run_lengths that weren't in train/test (rare,
        # but possible if the split was patched mid-run).
        for r in run_lengths:
            if r not in ordered:
                ordered.append(r)

        train_set = set(train_runs)
        test_set = set(test_runs)
        n_stories = len(ordered)
        feature_names = list(value.feature_names)
        feature_dims = list(value.feature_dims)
        total_dims = int(sum(feature_dims)) if feature_dims else 0
        n_voxels = int(value.Y_train.shape[1]) if value.Y_train.size else 0
        n_train_trs = int(value.X_train.shape[0]) if value.X_train.size else 0
        n_test_trs = int(value.X_test.shape[0]) if value.X_test.size else 0

        with mpl_figure(figsize=(11.0, 4.5)) as fig:
            ax_l = fig.add_subplot(1, 2, 1)
            ax_r = fig.add_subplot(1, 2, 2)

            # ── Left panel: per-story TR counts ───────────────────
            counts = [int(run_lengths.get(r, 0)) for r in ordered]
            colors = [
                'steelblue' if r in train_set
                else 'goldenrod' if r in test_set
                else 'lightgray'
                for r in ordered
            ]
            xs = np.arange(n_stories)
            ax_l.bar(xs, counts, color=colors, edgecolor='white')
            for i, v in enumerate(counts):
                ax_l.text(i, v, f'{v}', ha='center', va='bottom',
                          fontsize=8)
            ax_l.set_xticks(xs)
            ax_l.set_xticklabels(ordered, rotation=40, ha='right',
                                 fontsize=8)
            ax_l.set_ylabel('TR count (post-trim)')
            ax_l.set_title(
                f'per-story TR counts — '
                f'features ({total_dims} dims) ↔ responses '
                f'({n_voxels} voxels) aligned'
            )
            # Legend
            from matplotlib.patches import Patch
            legend_items = [
                Patch(facecolor='steelblue', label=f'train ({len(train_runs)})'),
                Patch(facecolor='goldenrod', label=f'test ({len(test_runs)})'),
            ]
            ax_l.legend(handles=legend_items, fontsize=8, loc='upper right')

            # ── Right panel: feature dim composition ──────────────
            if feature_names and feature_dims:
                cmap = _palette(len(feature_names))
                left = 0.0
                for i, (fname, d) in enumerate(zip(feature_names, feature_dims)):
                    ax_r.barh(
                        0, d, left=left, height=0.5,
                        color=cmap[i], edgecolor='white',
                    )
                    # Label inside the bar if it's wide enough, else above.
                    label = f'{fname}\n({d})'
                    midpoint = left + d / 2
                    fs = 7 if d / max(total_dims, 1) > 0.05 else 6
                    ax_r.text(
                        midpoint, 0, label, ha='center', va='center',
                        fontsize=fs, color='white',
                    )
                    left += d
                ax_r.set_xlim(0, total_dims if total_dims else 1)
                ax_r.set_ylim(-1, 1)
                ax_r.set_yticks([])
                ax_r.set_xlabel('X-column index')
                ax_r.set_title(
                    f'feature composition — '
                    f'{len(feature_names)} features, {total_dims} total dims'
                )
            else:
                ax_r.set_axis_off()
                ax_r.text(0.5, 0.5, 'no feature dims recorded',
                          ha='center', va='center')

            fig.tight_layout()
            png = save_png(fig, output_dir / 'per_story_shape.png')

        sidecar = output_dir / 'per_story_shape.json'
        sidecar.write_text(json.dumps({
            'per_story_trs': {r: int(run_lengths.get(r, 0)) for r in ordered},
            'train_runs': train_runs,
            'test_runs': test_runs,
            'feature_names': feature_names,
            'feature_dims': feature_dims,
            'total_feature_dims': total_dims,
            'n_voxels': n_voxels,
            'n_train_trs_total': n_train_trs,
            'n_test_trs_total': n_test_trs,
            'aligned_message': (
                'features and responses time-aligned for every story: '
                'concatenate would have errored otherwise.'
            ),
        }, indent=2))
        return {'shape': png, 'json': str(sidecar)}


def _palette(n: int) -> list[str]:
    """Return ``n`` distinct hex colours from a qualitative tab cycle."""
    import matplotlib.pyplot as plt
    cmap = plt.get_cmap('tab10' if n <= 10 else 'tab20')
    return [cmap(i % cmap.N) for i in range(n)]


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


@qa_reporter("responses_features_alignment", stage="prepare")
class ResponsesFeaturesAlignment:
    """Per-run side-by-side carpet of Y (voxels) and X (features).

    After ``concatenate`` the X / Y matrices are flat along time, but
    each run's TR count is stashed in ``PreparedData.metadata.run_lengths``
    so this plugin can slice them back out. For each run it draws
    two stacked carpets on the same time axis:

    * top    — X (features × time), grouped by feature with separators;
    * bottom — Y (voxels × time), voxels evenly subsampled.

    Misalignment between features and responses (off-by-one delays,
    flipped time, dropped TRs) shows up as the X structure being
    visibly shifted relative to the Y structure. Each run lands as a
    separate PNG so the QA tab gallery scrolls one run at a time.
    """

    name = "responses_features_alignment"
    stage = "prepare"
    PARAM_SCHEMA = {
        "max_voxels": {"type": "int", "default": 1500},
        "max_feature_cols": {"type": "int", "default": 800},
        "zscore_voxels": {"type": "bool", "default": True},
        "vmin_y": {"type": "float", "default": -3.0},
        "vmax_y": {"type": "float", "default": 3.0},
        "vmin_x": {"type": "float", "default": -3.0},
        "vmax_x": {"type": "float", "default": 3.0},
        "cmap": {"type": "string", "default": "gray"},
        "figsize": {"type": "list[float]", "default": [12.0, 7.0]},
        "dpi": {"type": "int", "default": 110, "min": 50},
        "runs": {
            "type": "list[string]",
            "description": (
                "Optional whitelist of run names to render (default: "
                "every train + test run)."
            ),
        },
    }

    def report(
        self, value: PreparedData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        cfg = self._my_cfg(config)
        max_voxels = cfg.get("max_voxels", 1500)
        max_feat_cols = cfg.get("max_feature_cols", 800)
        zscore_voxels = bool(cfg.get("zscore_voxels", True))
        vmin_y = float(cfg.get("vmin_y", -3.0))
        vmax_y = float(cfg.get("vmax_y", 3.0))
        vmin_x = float(cfg.get("vmin_x", -3.0))
        vmax_x = float(cfg.get("vmax_x", 3.0))
        cmap = cfg.get("cmap", "gray")
        figsize = tuple(cfg.get("figsize", [12.0, 7.0]))
        dpi = int(cfg.get("dpi", 110))
        runs_filter = cfg.get("runs") or []

        run_lengths = (value.metadata or {}).get("run_lengths") or {}
        out: dict[str, str] = {}
        sidecar: dict = {"runs": []}

        # Walk train then test runs in their declared order so each
        # ends up sliced at the right offset from the concatenated
        # matrices.
        for phase, run_list, X, Y in (
            ("train", value.train_runs, value.X_train, value.Y_train),
            ("test", value.test_runs, value.X_test, value.Y_test),
        ):
            if X is None or Y is None:
                continue
            offset = 0
            for run in run_list:
                length = run_lengths.get(run)
                if not length:
                    sidecar["runs"].append({
                        "run": run, "phase": phase,
                        "skipped": "no run_lengths entry — concatenate "
                                   "step didn't record it"})
                    continue
                start, end = offset, offset + length
                offset = end
                if runs_filter and run not in runs_filter:
                    continue
                Y_run = np.asarray(Y[start:end])
                X_run = np.asarray(X[start:end])
                png = self._render_run(
                    run=run, phase=phase, X_run=X_run, Y_run=Y_run,
                    feature_names=list(value.feature_names),
                    feature_dims=list(value.feature_dims),
                    delays=list(value.delays),
                    max_voxels=max_voxels, max_feat_cols=max_feat_cols,
                    zscore_voxels=zscore_voxels,
                    vmin_y=vmin_y, vmax_y=vmax_y,
                    vmin_x=vmin_x, vmax_x=vmax_x,
                    cmap=cmap, figsize=figsize, dpi=dpi,
                    output_dir=output_dir,
                )
                if png:
                    out[f"{phase}/{run}.png"] = png
                    sidecar["runs"].append({
                        "run": run, "phase": phase,
                        "n_trs": int(length),
                        "Y_shape": list(Y_run.shape),
                        "X_shape": list(X_run.shape),
                        "png": png,
                    })

        sidecar_path = output_dir / "responses_features_alignment.json"
        sidecar_path.write_text(json.dumps(sidecar, indent=2))
        out["alignment_index.json"] = str(sidecar_path)
        return out

    @staticmethod
    def _my_cfg(config: dict) -> dict:
        qa = (config or {}).get("qa") or {}
        block = qa.get("prepare")
        if isinstance(block, dict):
            params = block.get("responses_features_alignment")
            if isinstance(params, dict):
                return params
        return {}

    def _render_run(
        self, *, run: str, phase: str, X_run: np.ndarray, Y_run: np.ndarray,
        feature_names: list, feature_dims: list, delays: list,
        max_voxels: int, max_feat_cols: int, zscore_voxels: bool,
        vmin_y: float, vmax_y: float, vmin_x: float, vmax_x: float,
        cmap: str, figsize: tuple[float, float], dpi: int,
        output_dir: Path,
    ) -> str | None:
        if Y_run.ndim != 2 or X_run.ndim != 2 or Y_run.shape[0] == 0:
            return None
        Y = Y_run.astype(np.float64)
        if zscore_voxels:
            mu = Y.mean(axis=0, keepdims=True)
            sd = Y.std(axis=0, keepdims=True)
            with np.errstate(invalid='ignore', divide='ignore'):
                Y = (Y - mu) / np.where(sd > 0, sd, 1.0)
            Y[~np.isfinite(Y)] = 0.0
        n_voxels = Y.shape[1]
        if max_voxels and n_voxels > int(max_voxels):
            yidx = np.linspace(0, n_voxels - 1, int(max_voxels)).astype(int)
            Y = Y[:, yidx]
        n_feat_cols = X_run.shape[1]
        if max_feat_cols and n_feat_cols > int(max_feat_cols):
            xidx = np.linspace(0, n_feat_cols - 1, int(max_feat_cols)).astype(int)
            X_shown = X_run[:, xidx]
        else:
            X_shown = X_run

        with mpl_figure(figsize=figsize, dpi=dpi) as fig:
            # 2 panels stacked: top = features, bottom = voxels.
            # Share the x-axis explicitly via sharex so panning lines up.
            ax_x = fig.add_subplot(2, 1, 1)
            ax_y = fig.add_subplot(2, 1, 2, sharex=ax_x)
            im_x = ax_x.imshow(
                X_shown.T, aspect='auto', interpolation='nearest',
                cmap=cmap, vmin=vmin_x, vmax=vmax_x,
            )
            im_y = ax_y.imshow(
                Y.T, aspect='auto', interpolation='nearest',
                cmap=cmap, vmin=vmin_y, vmax=vmax_y,
            )

            # Feature boundaries (vertical lines on the X panel only
            # — would clutter the Y panel without adding info).
            n_delays = max(1, len(delays))
            col = 0
            for fname, fdim in zip(feature_names, feature_dims):
                width = int(fdim) * n_delays
                # Only annotate boundaries between features, not the
                # right edge.
                if col > 0:
                    # Project the boundary onto whatever indexing the
                    # subsample produced — translate via the same
                    # linspace ratio.
                    if max_feat_cols and n_feat_cols > max_feat_cols:
                        boundary_xs = (col - 0.5) * X_shown.shape[1] / n_feat_cols
                    else:
                        boundary_xs = col - 0.5
                    # The imshow's y axis is voxel/feature row index —
                    # so a vertical boundary is a horizontal line.
                    ax_x.axhline(boundary_xs, color='red',
                                 linewidth=0.5, alpha=0.6)
                # Feature label on the right margin.
                ax_x.text(
                    1.005, (col + width / 2) * X_shown.shape[1] / max(1, n_feat_cols),
                    fname, transform=ax_x.get_yaxis_transform(),
                    fontsize=7, va='center', color='dimgray',
                )
                col += width

            ax_x.set_ylabel('feature col')
            ax_x.set_title(
                f"{phase} · {run}  —  features (n_cols={n_feat_cols}"
                + (f", showing {X_shown.shape[1]}" if X_shown.shape[1] != n_feat_cols else "")
                + ")"
            )
            ax_y.set_xlabel(f"TR ({Y.shape[0]} total)")
            ax_y.set_ylabel('voxel')
            ax_y.set_title(
                f"responses (n_voxels={n_voxels}"
                + (f", showing {Y.shape[1]}" if Y.shape[1] != n_voxels else "")
                + (", z-scored" if zscore_voxels else "")
                + ")"
            )
            fig.colorbar(im_x, ax=ax_x, shrink=0.7, label='feature')
            fig.colorbar(im_y, ax=ax_y, shrink=0.7,
                         label='z' if zscore_voxels else 'BOLD')
            fig.tight_layout()
            run_dir = output_dir / phase
            run_dir.mkdir(parents=True, exist_ok=True)
            png = run_dir / f"{run}.png"
            return save_png(fig, png)
