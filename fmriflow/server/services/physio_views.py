"""What the physio nodes left behind, shaped for the node popup.

A ``physio_regressors`` node dir holds one ``physio_blocks_<run>.json`` +
``physio_regressors_<run>.tsv`` per run; a ``physio_clean`` MapNode dir holds
``mapflow/_<node>N/`` per run with ``physio_clean.json`` and the variance map.
:func:`scan_physio_node` turns either into a list of per-run rows, and the two
``render_*`` helpers draw a PNG next to the file they depict (regenerated when
the source is newer), with PIL only.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _iteration_dirs(node_dir: Path) -> list[Path]:
    mapflow = node_dir / "mapflow"
    if mapflow.is_dir():
        subs = [d for d in mapflow.iterdir() if d.is_dir()]
        def idx(d: Path) -> int:
            tail = d.name.rsplit("_", 1)[-1] if "_" in d.name else d.name
            digits = "".join(ch for ch in reversed(d.name) if ch.isdigit())[::-1]
            return int(digits) if digits else 0
        return sorted(subs, key=idx)
    return [node_dir]


def _fresh(png: Path, src: Path) -> bool:
    try:
        return png.exists() and png.stat().st_mtime >= src.stat().st_mtime
    except OSError:
        return False


def scan_physio_node(node_dir: Path) -> dict[str, Any]:
    """``{"kind": "regressors" | "clean" | None, "items": [...]}`` for a node work dir."""
    node_dir = Path(node_dir)
    if not node_dir.is_dir():
        return {"kind": None, "items": []}
    items: list[dict[str, Any]] = []
    blocks = sorted(node_dir.glob("physio_blocks*.json"))
    if blocks:
        for i, bj in enumerate(blocks):
            try:
                d = json.loads(bj.read_text())
            except Exception as e:
                items.append({"index": i, "error": f"{bj.name}: {e}"})
                continue
            sel = d.get("selected") or {}
            suffix = bj.name[len("physio_blocks"):-len(".json")]
            tsv = node_dir / f"physio_regressors{suffix}.tsv"
            items.append({
                "index": i,
                "run": Path(d.get("bold_file") or suffix.lstrip("_") or bj.stem).name,
                "session": d.get("session"),
                "block": sel.get("index"),
                "n_blocks": d.get("n_blocks"),
                "block_durations_s": [b.get("duration_s") for b in (d.get("blocks") or [])],
                "triggers": sel.get("n_pulses"),
                "bold_n_trs": d.get("bold_n_trs"),
                "tr_s": d.get("tr_s"),
                "order": d.get("order"),
                "acquisition_time_s": d.get("acquisition_time_s"),
                "n_regressors": d.get("n_regressors"),
                "regressors": d.get("regressors") or [],
                "skipped_runs": d.get("skipped_runs") or [],
                "recording": Path(d.get("source") or "").name,
                "sampling_rate": d.get("sampling_rate"),
                "regressors_file": str(tsv) if tsv.is_file() else None,
                "has_image": tsv.is_file(),
            })
        return {"kind": "regressors", "items": items}
    for i, d in enumerate(_iteration_dirs(node_dir)):
        sj = d / "physio_clean.json"
        if not sj.is_file():
            continue
        try:
            summary = json.loads(sj.read_text())
        except Exception as e:
            items.append({"index": i, "error": f"{sj}: {e}"})
            continue
        vmap = d / "physio_variance_removed.nii.gz"
        out = summary.get("out_file") or next((str(p) for p in d.glob("*_desc-physioclean_bold.nii.gz")), None)
        items.append({
            "index": i,
            "run": Path(summary.get("bold_file") or out or d.name).name,
            "out_file": out,
            "n_trs": summary.get("n_trs"),
            "n_regressors": summary.get("n_regressors"),
            "variance_removed_fraction": summary.get("variance_removed_fraction"),
            "variance_removed_p50": summary.get("variance_removed_p50"),
            "variance_removed_p95": summary.get("variance_removed_p95"),
            "n_nan_inf": summary.get("n_nan_inf"),
            "variance_map": str(vmap) if vmap.is_file() else None,
            "has_image": vmap.is_file(),
        })
    return {"kind": "clean" if items else None, "items": items}


def image_for(node_dir: Path, index: int) -> Path | None:
    """The PNG for item ``index`` of :func:`scan_physio_node`, rendered on demand."""
    view = scan_physio_node(Path(node_dir))
    items = view["items"]
    if not 0 <= index < len(items):
        return None
    item = items[index]
    if view["kind"] == "regressors" and item.get("regressors_file"):
        return render_regressors_png(Path(item["regressors_file"]), item.get("regressors") or [])
    if view["kind"] == "clean" and item.get("variance_map"):
        return render_variance_png(Path(item["variance_map"]))
    return None


# ── renderers (PIL only) ─────────────────────────────────────────────


def render_regressors_png(tsv: Path, names: list[str], *, row_px: int = 14, width: int = 900) -> Path | None:
    """One row per regressor, time left→right, z-scored blue–white–red."""
    out = tsv.with_suffix(".png")
    if _fresh(out, tsv):
        return out
    try:
        import numpy as np
        from PIL import Image, ImageDraw
        from fmriflow.preproc.physio.regress import read_regressors
        X, cols = read_regressors(tsv)
        names = cols or names
        if X.size == 0:
            return None
        Z = (X - X.mean(0)) / np.where(X.std(0) > 0, X.std(0), 1.0)
        Z = np.clip(Z / 3.0, -1, 1).T                       # (n_reg, n_trs) in [-1, 1]
        rgb = np.zeros((*Z.shape, 3), dtype=np.float32)
        pos, neg = np.clip(Z, 0, 1), np.clip(-Z, 0, 1)
        rgb[..., 0] = 1 - neg; rgb[..., 1] = 1 - pos - neg; rgb[..., 2] = 1 - pos
        img = Image.fromarray((rgb * 255).astype("uint8")).resize((width, row_px * Z.shape[0]), Image.NEAREST)
        label_w = 200
        canvas = Image.new("RGB", (label_w + width, img.height), "white")
        canvas.paste(img, (label_w, 0))
        draw = ImageDraw.Draw(canvas)
        for r, n in enumerate(names):
            draw.text((4, r * row_px + 1), n[:34], fill=(40, 40, 40))
        canvas.save(out)
        return out
    except Exception as e:
        logger.debug("regressor image for %s failed: %s", tsv, e)
        return None


def _heat_lut():
    import numpy as np
    t = np.linspace(0, 1, 256)
    r = np.clip(t * 2.2, 0, 1)
    g = np.clip(t * 1.4 - 0.25, 0, 1)
    b = np.clip(t * 0.9 - 0.65, 0, 1)
    return (np.stack([r, g, b], axis=1) * 255).astype("uint8")


def render_variance_png(nii: Path, *, n_slices: int = 8, tile: int = 150, vmax: float = 0.5) -> Path | None:
    """A montage of axial slices of the per-voxel variance-removed fraction (0 → black, ``vmax`` → yellow)."""
    out = nii.with_name(nii.name.replace(".nii.gz", "").replace(".nii", "") + ".png")
    if _fresh(out, nii):
        return out
    try:
        import nibabel as nib
        import numpy as np
        from PIL import Image
        data = np.asarray(nib.load(str(nii)).dataobj, dtype="float32")
        if data.ndim != 3:
            return None
        zs = np.linspace(data.shape[2] * 0.15, data.shape[2] * 0.85, n_slices).astype(int)
        lut = _heat_lut()
        tiles = []
        for z in zs:
            sl = np.clip(np.rot90(data[:, :, z]) / vmax, 0, 1)
            idx = (sl * 255).astype("uint8")
            tiles.append(Image.fromarray(lut[idx]).resize((tile, tile), Image.BILINEAR))
        cols = 4
        rows = (len(tiles) + cols - 1) // cols
        canvas = Image.new("RGB", (cols * tile, rows * tile), "black")
        for i, t in enumerate(tiles):
            canvas.paste(t, ((i % cols) * tile, (i // cols) * tile))
        canvas.save(out)
        return out
    except Exception as e:
        logger.debug("variance image for %s failed: %s", nii, e)
        return None
