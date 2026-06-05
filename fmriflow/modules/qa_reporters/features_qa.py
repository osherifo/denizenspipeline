"""QA reporters for the ``features`` stage (FeatureData).

A feature-matrix carpet is the standard sanity check on feature
loading: feature dimensions on the y-axis, time on the x-axis, colour
by amplitude. Lets the user catch a misaligned feature, a flipped
delay, or a per-feature scaling problem before anything downstream.

Layout per PNG: every feature stacked vertically (english1000 above
letters above numwords above moten), every run concatenated along
time, with red **vertical** lines at run boundaries and **horizontal**
lines + right-margin labels at feature boundaries. Two views are
emitted per call — ``feature_matrix_zscored.png`` (each column
z-scored, the standard QA view) and ``feature_matrix_raw.png`` (raw
amplitudes, clipped to the data's 1/99th percentile by default).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fmriflow.core.types import FeatureData
from fmriflow.modules._decorators import qa_reporter
from fmriflow.modules.qa_reporters._base import ensure_dir, mpl_figure, save_png


@qa_reporter("feature_matrix", stage="features")
class FeatureMatrix:
    """Stacked feature-dimensions × time carpet for the loaded features.

    Walks ``FeatureData.features`` in declared order, stacks each run
    horizontally along the dim axis (so all features for one run are
    one strip in time), then concatenates run-strips along the time
    axis. The resulting ``(T_total, total_dims)`` matrix is rendered
    twice — z-scored per column and raw — so you can spot both
    structure (z) and per-feature scaling issues (raw).
    """

    name = "feature_matrix"
    stage = "features"
    PARAM_SCHEMA = {
        "max_dims_per_feature": {
            "type": "int", "default": None,
            "description": (
                "Cap per feature on the number of dimensions shown "
                "(evenly subsampled along the dim axis). ``null`` "
                "shows every dim. Useful when one feature like motion "
                "energy is 6555-dim and dwarfs the others."
            ),
        },
        # Z-scored panel range (always emitted)
        "vmin_z": {"type": "float", "default": -3.0},
        "vmax_z": {"type": "float", "default": 3.0},
        # Raw panel range — None lets the plugin auto-scale to the
        # 1–99 percentile so wildly different feature scales still
        # plot legibly side by side.
        "vmin_raw": {
            "type": "float", "default": None,
            "description": "Raw-panel colour-scale min; null = 1st percentile.",
        },
        "vmax_raw": {
            "type": "float", "default": None,
            "description": "Raw-panel colour-scale max; null = 99th percentile.",
        },
        "cmap": {"type": "string", "default": "viridis"},
        "figsize": {
            "type": "list[float]", "default": [12.0, 7.0],
            "description": "matplotlib figure size in inches.",
        },
        "dpi": {"type": "int", "default": 110, "min": 50},
        "runs": {
            "type": "list[string]",
            "description": (
                "Optional whitelist of run names to include "
                "(default: every run in the first feature's data)."
            ),
        },
    }

    def report(
        self, value: FeatureData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        cfg = self._my_cfg(config)
        max_dims = cfg.get("max_dims_per_feature", None)
        vmin_z = float(cfg.get("vmin_z", -3.0))
        vmax_z = float(cfg.get("vmax_z",  3.0))
        vmin_raw = cfg.get("vmin_raw", None)
        vmax_raw = cfg.get("vmax_raw", None)
        cmap = cfg.get("cmap", "viridis")
        figsize = tuple(cfg.get("figsize", [12.0, 7.0]))
        dpi = int(cfg.get("dpi", 110))
        runs_filter = cfg.get("runs") or None

        out: dict[str, str] = {}
        feature_names = list(value.feature_names)
        if not feature_names:
            sidecar = output_dir / "feature_matrix.json"
            sidecar.write_text(json.dumps({"skipped": "no features"}))
            return {"feature_matrix.json": str(sidecar)}

        # Use the first feature's run dict as the canonical ordering.
        first_fs = value.features[feature_names[0]]
        run_order = list(first_fs.data.keys())
        if runs_filter:
            run_order = [r for r in run_order if r in runs_filter]
        if not run_order:
            sidecar = output_dir / "feature_matrix.json"
            sidecar.write_text(json.dumps(
                {"skipped": "no matching runs after filter"}))
            return {"feature_matrix.json": str(sidecar)}

        # For each feature, decide which dims to render (subsample if
        # the cap is set + the feature exceeds it) so all run blocks
        # share a consistent column layout.
        dim_index: dict[str, np.ndarray] = {}
        for fname in feature_names:
            fs = value.features[fname]
            n = int(fs.n_dims)
            if max_dims and n > int(max_dims):
                dim_index[fname] = np.linspace(
                    0, n - 1, int(max_dims)).astype(int)
            else:
                dim_index[fname] = np.arange(n)

        # Build per-run strips: each strip is (n_trs_run, total_shown_dims).
        # Feature boundaries (in the dim axis) come from cumulative sums
        # of ``len(dim_index[fname])``.
        feature_boundaries: list[tuple[str, int, int]] = []
        col = 0
        for fname in feature_names:
            width = int(len(dim_index[fname]))
            feature_boundaries.append((fname, col, col + width))
            col += width
        total_shown_dims = col

        strips: list[np.ndarray] = []
        run_lengths: list[int] = []
        run_names_used: list[str] = []
        for run in run_order:
            cols: list[np.ndarray] = []
            run_len: int | None = None
            run_ok = True
            for fname in feature_names:
                fs = value.features[fname]
                arr = fs.data.get(run)
                if arr is None:
                    # Whole run is missing this feature — drop the
                    # run so we don't insert NaNs that break the
                    # carpet scale.
                    run_ok = False
                    break
                arr = np.asarray(arr)
                if arr.ndim != 2:
                    run_ok = False
                    break
                if run_len is None:
                    run_len = int(arr.shape[0])
                elif int(arr.shape[0]) != run_len:
                    # Feature row count mismatch — concatenate would
                    # have errored later anyway, so flag + skip.
                    run_ok = False
                    break
                cols.append(arr[:, dim_index[fname]])
            if not run_ok or run_len is None:
                continue
            strips.append(np.hstack(cols).astype(np.float64))
            run_lengths.append(run_len)
            run_names_used.append(run)
        if not strips:
            sidecar = output_dir / "feature_matrix.json"
            sidecar.write_text(json.dumps(
                {"skipped": "no run had every feature with matching row counts"}))
            return {"feature_matrix.json": str(sidecar)}

        raw = np.vstack(strips)                        # (T_total, total_shown_dims)
        n_trs = int(raw.shape[0])

        # Per-column z-score (each dim across time).
        mu = raw.mean(axis=0, keepdims=True)
        sigma = raw.std(axis=0, keepdims=True)
        with np.errstate(invalid='ignore', divide='ignore'):
            z = (raw - mu) / np.where(sigma > 0, sigma, 1.0)
        z[~np.isfinite(z)] = 0.0

        if vmin_raw is None:
            vmin_raw = float(np.nanpercentile(raw, 1))
        if vmax_raw is None:
            vmax_raw = float(np.nanpercentile(raw, 99))
        vmin_raw = float(vmin_raw)
        vmax_raw = float(vmax_raw)

        # Headline dim totals per feature for the title.
        per_feature_dims = {
            name: {
                "n_dims": int(value.features[name].n_dims),
                "n_dims_shown": int(len(dim_index[name])),
            }
            for name in feature_names
        }

        out.update(self._render(
            output_dir / "feature_matrix_zscored.png",
            data=z, run_lengths=run_lengths, run_names=run_names_used,
            feature_boundaries=feature_boundaries,
            total_shown_dims=total_shown_dims, n_trs=n_trs,
            vmin=vmin_z, vmax=vmax_z, cmap=cmap, figsize=figsize, dpi=dpi,
            kind="z-scored per dim", colorbar_label="z",
        ))
        out.update(self._render(
            output_dir / "feature_matrix_raw.png",
            data=raw, run_lengths=run_lengths, run_names=run_names_used,
            feature_boundaries=feature_boundaries,
            total_shown_dims=total_shown_dims, n_trs=n_trs,
            vmin=vmin_raw, vmax=vmax_raw, cmap=cmap, figsize=figsize, dpi=dpi,
            kind="raw amplitudes", colorbar_label="value",
        ))

        sidecar = output_dir / "feature_matrix.json"
        sidecar.write_text(json.dumps({
            "n_runs": len(run_names_used),
            "n_trs": n_trs,
            "run_names": run_names_used,
            "run_lengths": run_lengths,
            "feature_names": feature_names,
            "per_feature": per_feature_dims,
            "total_dims_shown": total_shown_dims,
            "zscored_clip": [vmin_z, vmax_z],
            "raw_clip": [vmin_raw, vmax_raw],
        }, indent=2))
        out["feature_matrix.json"] = str(sidecar)
        return out

    @staticmethod
    def _render(
        path: Path, *, data: np.ndarray, run_lengths: list[int],
        run_names: list[str],
        feature_boundaries: list[tuple[str, int, int]],
        total_shown_dims: int, n_trs: int,
        vmin: float, vmax: float, cmap: str,
        figsize: tuple[float, float], dpi: int,
        kind: str, colorbar_label: str,
    ) -> dict[str, str]:
        with mpl_figure(figsize=figsize, dpi=dpi) as fig:
            ax = fig.add_subplot(111)
            ax.imshow(
                data.T, aspect='auto', interpolation='nearest',
                cmap=cmap, vmin=vmin, vmax=vmax,
            )
            # Vertical lines at run boundaries (between successive runs).
            t_boundary = 0
            for length in run_lengths[:-1]:
                t_boundary += length
                ax.axvline(t_boundary - 0.5, color='red',
                           linewidth=0.6, alpha=0.6)
            # Horizontal lines between features + right-margin labels.
            for i, (fname, start, end) in enumerate(feature_boundaries):
                if i > 0:
                    ax.axhline(start - 0.5, color='red',
                               linewidth=0.6, alpha=0.6)
                ax.text(
                    1.005, (start + end) / 2.0,
                    fname, transform=ax.get_yaxis_transform(),
                    fontsize=7, va='center', color='dimgray',
                )
            ax.set_xlabel(f"TR ({n_trs} total, {len(run_lengths)} runs)")
            ax.set_ylabel("feature dim")
            ax.set_title(f"Feature matrix — {kind}")
            fig.colorbar(ax.images[0], ax=ax, shrink=0.7,
                         label=colorbar_label)
            save_png(fig, path)
        return {path.name: str(path)}

    @staticmethod
    def _my_cfg(config: dict) -> dict:
        qa = (config or {}).get("qa") or {}
        block = qa.get("features")
        if isinstance(block, dict):
            params = block.get("feature_matrix")
            if isinstance(params, dict):
                return params
        return {}
