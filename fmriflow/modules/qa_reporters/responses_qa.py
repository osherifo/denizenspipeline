"""QA reporters for the ``responses`` stage (ResponseData).

A carpet plot is the standard fMRI sanity check for response loading:
voxels on the y-axis, time on the x-axis, colour by amplitude. Lets
the user catch a bad mask, a flipped time axis, or a story with
runaway drift before any downstream modelling.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.modules._decorators import qa_reporter
from fmriflow.modules.qa_reporters._base import ensure_dir, mpl_figure, save_png


@qa_reporter("voxel_carpet", stage="responses")
class VoxelCarpet:
    """Voxels × time carpet plot of the loaded fMRI responses.

    Concatenates every run along the time axis and renders **two**
    carpets each run: ``voxel_carpet_zscored.png`` (each voxel
    z-scored across time — the standard QA view) and
    ``voxel_carpet_raw.png`` (BOLD signal as loaded, no normalisation
    — useful for spotting drift, scanner artefacts, intensity
    outliers). Subsampling is opt-in via ``max_voxels``; setting it
    to ``null`` shows every voxel.
    """

    name = "voxel_carpet"
    stage = "responses"
    PARAM_SCHEMA = {
        "max_voxels": {
            "type": "int", "default": None,
            "description": (
                "Cap on the number of voxels shown (evenly subsampled). "
                "``null`` (default) plots every voxel."
            ),
        },
        # Z-scored panel range (always emitted)
        "vmin_z": {"type": "float", "default": -3.0},
        "vmax_z": {"type": "float", "default": 3.0},
        # Raw panel range — None lets matplotlib auto-scale to the
        # 1–99 percentile so an arbitrary BOLD unit isn't a problem.
        "vmin_raw": {
            "type": "float", "default": None,
            "description": "Raw-panel colour-scale min; null = 1st percentile.",
        },
        "vmax_raw": {
            "type": "float", "default": None,
            "description": "Raw-panel colour-scale max; null = 99th percentile.",
        },
        "cmap": {"type": "string", "default": "gray"},
        "figsize": {
            "type": "list[float]", "default": [12.0, 5.0],
            "description": "matplotlib figure size in inches.",
        },
        "dpi": {"type": "int", "default": 110, "min": 50},
    }

    def report(
        self, value: ResponseData, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)
        out: dict[str, str] = {}

        my_cfg = self._my_cfg(config)
        max_voxels = my_cfg.get("max_voxels", None)
        vmin_z = float(my_cfg.get("vmin_z", -3.0))
        vmax_z = float(my_cfg.get("vmax_z",  3.0))
        vmin_raw = my_cfg.get("vmin_raw", None)
        vmax_raw = my_cfg.get("vmax_raw", None)
        cmap = my_cfg.get("cmap", "gray")
        figsize = tuple(my_cfg.get("figsize", [12.0, 5.0]))
        dpi = int(my_cfg.get("dpi", 110))

        # Stitch the per-run responses into one (T_total, n_voxels) matrix
        # in the dict's iteration order. Also track each run's boundary
        # so the carpet can be annotated with vertical separators.
        run_order = list(value.responses.keys())
        if not run_order:
            sidecar = output_dir / "voxel_carpet.json"
            sidecar.write_text(json.dumps({"skipped": "no runs in responses"}))
            return {"voxel_carpet.json": str(sidecar)}

        blocks: list[np.ndarray] = []
        run_lengths: list[int] = []
        for run in run_order:
            arr = np.asarray(value.responses[run])
            if arr.ndim != 2:
                continue
            blocks.append(arr)
            run_lengths.append(int(arr.shape[0]))
        if not blocks:
            sidecar = output_dir / "voxel_carpet.json"
            sidecar.write_text(json.dumps(
                {"skipped": "no 2-D runs in responses"}))
            return {"voxel_carpet.json": str(sidecar)}

        raw = np.vstack(blocks).astype(np.float64)            # (T, n_vox)
        n_trs, n_voxels = raw.shape

        # Per-voxel z-score (used by the zscored panel).
        mu = raw.mean(axis=0, keepdims=True)
        sigma = raw.std(axis=0, keepdims=True)
        with np.errstate(invalid='ignore', divide='ignore'):
            z = (raw - mu) / np.where(sigma > 0, sigma, 1.0)
        z[~np.isfinite(z)] = 0.0

        # Subsample voxels uniformly for legibility when requested.
        if max_voxels and n_voxels > int(max_voxels):
            idx = np.linspace(0, n_voxels - 1, int(max_voxels)).astype(int)
            raw_shown = raw[:, idx]
            z_shown = z[:, idx]
            n_shown = int(len(idx))
            sub_label = f" (showing {n_shown} of {n_voxels} voxels)"
        else:
            raw_shown = raw
            z_shown = z
            n_shown = n_voxels
            sub_label = f" ({n_voxels} voxels)"

        # Auto-pick the raw panel's clip range from percentiles when
        # the user didn't specify — same data lives on very different
        # BOLD scales depending on the loader.
        if vmin_raw is None:
            vmin_raw = float(np.nanpercentile(raw, 1))
        if vmax_raw is None:
            vmax_raw = float(np.nanpercentile(raw, 99))
        vmin_raw = float(vmin_raw)
        vmax_raw = float(vmax_raw)

        out.update(self._render(
            output_dir / "voxel_carpet_zscored.png",
            data=z_shown, run_lengths=run_lengths, run_order=run_order,
            n_trs=n_trs, vmin=vmin_z, vmax=vmax_z, cmap=cmap,
            figsize=figsize, dpi=dpi, kind="z-scored per voxel",
            sub_label=sub_label, colorbar_label="z",
        ))
        out.update(self._render(
            output_dir / "voxel_carpet_raw.png",
            data=raw_shown, run_lengths=run_lengths, run_order=run_order,
            n_trs=n_trs, vmin=vmin_raw, vmax=vmax_raw, cmap=cmap,
            figsize=figsize, dpi=dpi, kind="raw BOLD",
            sub_label=sub_label, colorbar_label="BOLD",
        ))

        sidecar = output_dir / "voxel_carpet.json"
        sidecar.write_text(json.dumps({
            "n_runs": len(run_order),
            "n_trs": n_trs,
            "n_voxels": n_voxels,
            "n_voxels_shown": n_shown,
            "run_names": run_order,
            "run_lengths": run_lengths,
            "zscored_clip": [vmin_z, vmax_z],
            "raw_clip": [vmin_raw, vmax_raw],
        }, indent=2))
        out["voxel_carpet.json"] = str(sidecar)
        return out

    @staticmethod
    def _render(
        path: Path, *, data: np.ndarray, run_lengths: list[int],
        run_order: list[str], n_trs: int, vmin: float, vmax: float,
        cmap: str, figsize: tuple[float, float], dpi: int, kind: str,
        sub_label: str, colorbar_label: str,
    ) -> dict[str, str]:
        with mpl_figure(figsize=figsize, dpi=dpi) as fig:
            ax = fig.add_subplot(111)
            ax.imshow(
                data.T, aspect='auto', interpolation='nearest',
                cmap=cmap, vmin=vmin, vmax=vmax,
            )
            boundary = 0
            for length in run_lengths[:-1]:
                boundary += length
                ax.axvline(boundary - 0.5, color='red',
                           linewidth=0.6, alpha=0.6)
            ax.set_xlabel(f"TR ({n_trs} total{sub_label})")
            ax.set_ylabel("voxel")
            ax.set_title(
                f"Response carpet — {len(run_order)} run(s), {kind}"
            )
            fig.colorbar(ax.images[0], ax=ax, shrink=0.7,
                         label=colorbar_label)
            save_png(fig, path)
        return {path.name: str(path)}

    @staticmethod
    def _my_cfg(config: dict) -> dict:
        """Pull this plugin's per-stage params from ``qa.responses.plugins``
        or ``qa.responses.<plugin_name>`` if the user wants to tune it."""
        qa = (config or {}).get("qa") or {}
        block = qa.get("responses")
        if isinstance(block, dict):
            params = block.get("voxel_carpet")
            if isinstance(params, dict):
                return params
        return {}
