"""QA reporters for the ``features`` stage (FeatureData).

Two layouts are supported:

- ``layout: combined`` (default) — every feature stacked vertically,
  every run concatenated along time, into one carpet per panel.
  Vertical red lines mark run boundaries, horizontal red lines + a
  right-margin label mark feature boundaries. Best for spotting global
  scale/alignment issues at a glance.

- ``layout: grid`` — an N-feature × M-run grid of small subplots,
  each cell is the carpet for that (feature, story) pair. Rows are
  labelled with the feature name on the left margin; columns are
  labelled with the run/story name across the top. Best when you want
  per-(feature, story) inspection without the per-feature scale
  differences squashing the colorbar.

Both layouts emit two PNGs: ``feature_matrix_zscored.png`` (each
feature column z-scored across time) and ``feature_matrix_raw.png``
(amplitudes as loaded). In grid mode the raw panel uses **per-row**
clipping (each feature's own 1/99th percentile) so a 6555-dim moten
row and a 1-dim numwords row stay legible side by side.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fmriflow.core.types import FeatureData
from fmriflow.modules._decorators import qa_reporter
from fmriflow.modules.qa_reporters._base import ensure_dir, save_png


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
        "layout": {
            "type": "string", "default": "combined",
            "enum": ["combined", "grid"],
            "description": (
                "'combined' = one stacked carpet (all features × all runs); "
                "'grid' = subplot per (feature, run) with row/column labels."
            ),
        },
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
            "description": (
                "matplotlib figure size in inches (combined layout only — "
                "grid layout sizes from cell_size × grid shape)."
            ),
        },
        "cell_size": {
            "type": "list[float]", "default": [1.4, 0.9],
            "description": (
                "Per-cell [width, height] in inches (grid layout only). "
                "Figure size = ncols × w + label margin, nrows × h + title margin."
            ),
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
        layout = str(cfg.get("layout", "combined"))
        max_dims = cfg.get("max_dims_per_feature", None)
        vmin_z = float(cfg.get("vmin_z", -3.0))
        vmax_z = float(cfg.get("vmax_z",  3.0))
        vmin_raw = cfg.get("vmin_raw", None)
        vmax_raw = cfg.get("vmax_raw", None)
        cmap = cfg.get("cmap", "viridis")
        figsize = tuple(cfg.get("figsize", [12.0, 7.0]))
        cell_size = tuple(cfg.get("cell_size", [1.4, 0.9]))
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

        # Global raw clip (used by combined layout + as the default for
        # the grid layout's z-scored panel; grid raw uses per-row clip).
        if vmin_raw is None:
            global_vmin_raw = float(np.nanpercentile(raw, 1))
        else:
            global_vmin_raw = float(vmin_raw)
        if vmax_raw is None:
            global_vmax_raw = float(np.nanpercentile(raw, 99))
        else:
            global_vmax_raw = float(vmax_raw)

        # Headline dim totals per feature for the title.
        per_feature_dims = {
            name: {
                "n_dims": int(value.features[name].n_dims),
                "n_dims_shown": int(len(dim_index[name])),
            }
            for name in feature_names
        }

        if layout == "grid":
            # Per-feature percentile clip for the raw grid so a
            # high-amplitude feature doesn't make low-amplitude ones
            # vanish. Each tuple is (vmin, vmax) for one feature row.
            per_feature_raw_clip: dict[str, tuple[float, float]] = {}
            for fname, start, end in feature_boundaries:
                cols = raw[:, start:end]
                lo = (float(np.nanpercentile(cols, 1))
                      if vmin_raw is None else float(vmin_raw))
                hi = (float(np.nanpercentile(cols, 99))
                      if vmax_raw is None else float(vmax_raw))
                per_feature_raw_clip[fname] = (lo, hi)

            out.update(self._render_grid(
                output_dir / "feature_matrix_zscored.png",
                data=z, run_lengths=run_lengths, run_names=run_names_used,
                feature_boundaries=feature_boundaries,
                cell_size=cell_size, cmap=cmap, dpi=dpi,
                kind="z-scored per dim", colorbar_label="z",
                shared_clip=(vmin_z, vmax_z),
                per_row_clip=None,
            ))
            out.update(self._render_grid(
                output_dir / "feature_matrix_raw.png",
                data=raw, run_lengths=run_lengths, run_names=run_names_used,
                feature_boundaries=feature_boundaries,
                cell_size=cell_size, cmap=cmap, dpi=dpi,
                kind="raw amplitudes", colorbar_label="value",
                shared_clip=None,
                per_row_clip=per_feature_raw_clip,
            ))
        else:
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
                vmin=global_vmin_raw, vmax=global_vmax_raw, cmap=cmap,
                figsize=figsize, dpi=dpi,
                kind="raw amplitudes", colorbar_label="value",
            ))

        sidecar = output_dir / "feature_matrix.json"
        sidecar.write_text(json.dumps({
            "layout": layout,
            "n_runs": len(run_names_used),
            "n_trs": n_trs,
            "run_names": run_names_used,
            "run_lengths": run_lengths,
            "feature_names": feature_names,
            "per_feature": per_feature_dims,
            "total_dims_shown": total_shown_dims,
            "zscored_clip": [vmin_z, vmax_z],
            "raw_clip": [global_vmin_raw, global_vmax_raw],
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
        import matplotlib
        matplotlib.use('Agg', force=False)
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=figsize, dpi=dpi)
        try:
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
        finally:
            plt.close(fig)
        return {path.name: str(path)}

    @staticmethod
    def _render_grid(
        path: Path, *, data: np.ndarray, run_lengths: list[int],
        run_names: list[str],
        feature_boundaries: list[tuple[str, int, int]],
        cell_size: tuple[float, float], cmap: str, dpi: int,
        kind: str, colorbar_label: str,
        shared_clip: tuple[float, float] | None,
        per_row_clip: dict[str, tuple[float, float]] | None,
    ) -> dict[str, str]:
        """Render a (features × runs) grid of small carpets.

        ``data`` is the same ``(T_total, total_dims)`` matrix used by
        the combined render — we slice it by feature column ranges
        (from ``feature_boundaries``) and run row ranges (cumulative
        ``run_lengths``).

        Exactly one of ``shared_clip`` or ``per_row_clip`` must be set:
        - ``shared_clip=(vmin, vmax)``: one colorbar at the right of
          the figure (typical for z-scored).
        - ``per_row_clip={fname: (vmin, vmax)}``: each feature row
          uses its own clip, with a small colorbar at the right of
          each row (typical for raw, so very different scales remain
          legible).
        """
        import matplotlib
        matplotlib.use('Agg', force=False)
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec

        n_features = len(feature_boundaries)
        n_runs = len(run_lengths)

        # Run row-ranges (start, end) along the time axis.
        run_ranges: list[tuple[int, int]] = []
        t = 0
        for L in run_lengths:
            run_ranges.append((t, t + L))
            t += L

        # Figure size: cells + outer label margins + colorbar column.
        w_cell, h_cell = float(cell_size[0]), float(cell_size[1])
        left_label_w = 1.4         # inches reserved for the row labels
        top_title_h = 0.6          # inches reserved for column headers
        cbar_w = 0.35              # inches reserved for the colorbar column
        fig_w = left_label_w + n_runs * w_cell + cbar_w + 0.4
        fig_h = top_title_h + n_features * h_cell + 0.6

        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
        try:
            # width_ratios: [n_runs cell columns] + [colorbar column].
            # Cells are equal width; the colorbar is narrower.
            width_ratios = [1.0] * n_runs + [0.12]
            gs = GridSpec(
                n_features, n_runs + 1,
                width_ratios=width_ratios,
                left=left_label_w / fig_w,
                right=1.0 - 0.05 / fig_w,
                top=1.0 - top_title_h / fig_h,
                bottom=0.45 / fig_h,
                wspace=0.08, hspace=0.18,
                figure=fig,
            )

            cell_images = []
            for r, (fname, c_start, c_end) in enumerate(feature_boundaries):
                if per_row_clip is not None:
                    vmin_r, vmax_r = per_row_clip[fname]
                else:
                    assert shared_clip is not None
                    vmin_r, vmax_r = shared_clip

                for c, run in enumerate(run_names):
                    t_start, t_end = run_ranges[c]
                    cell = data[t_start:t_end, c_start:c_end]  # (T_run, n_dims_f)
                    ax = fig.add_subplot(gs[r, c])
                    img = ax.imshow(
                        cell.T, aspect='auto', interpolation='nearest',
                        cmap=cmap, vmin=vmin_r, vmax=vmax_r,
                    )
                    if r == 0:
                        ax.set_title(run, fontsize=7, pad=2)
                    if c == 0:
                        # Row label on the left margin (feature name).
                        ax.text(
                            -0.06, 0.5, fname,
                            transform=ax.transAxes,
                            fontsize=8, ha='right', va='center',
                            color='black',
                        )
                    ax.set_xticks([])
                    ax.set_yticks([])
                    for spine in ax.spines.values():
                        spine.set_linewidth(0.5)
                        spine.set_color('lightgray')
                    cell_images.append(img)

                # Per-row colorbar (raw mode).
                if per_row_clip is not None:
                    cax = fig.add_subplot(gs[r, n_runs])
                    last_img = cell_images[-1]
                    cb = fig.colorbar(last_img, cax=cax)
                    cb.ax.tick_params(labelsize=6, length=2)

            # Shared colorbar (zscored mode) spans every row.
            if shared_clip is not None and cell_images:
                cax = fig.add_subplot(gs[:, n_runs])
                cb = fig.colorbar(cell_images[0], cax=cax,
                                  label=colorbar_label)
                cb.ax.tick_params(labelsize=7)

            fig.suptitle(
                f"Feature matrix grid — {kind} "
                f"({n_features} features × {n_runs} runs)",
                fontsize=10, y=1.0 - 0.06 / fig_h,
            )
            save_png(fig, path)
        finally:
            plt.close(fig)
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
