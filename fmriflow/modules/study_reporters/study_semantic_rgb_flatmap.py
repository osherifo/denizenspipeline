"""StudySemanticRgbFlatmap — per-subject Fig 4 equivalents at study scope.

For every subject in every group of the study run, project the subject's
single-feature model weights onto a pre-existing semantic PCA basis and
render an RGB flatmap (PC channels → R/G/B). Two variants per subject:

* ``all``        — every cortical voxel coloured by its PC projection
* ``significant`` — voxels below ``thresholds[<modality>]`` are masked
                    transparent so they read as grey cortex

Lives at study scope rather than subject scope because:

1. It needs the per-modality significance thresholds (which are study-level
   knowledge — different value per group).
2. It works off saved disk intermediates (``intermediates/prepare.joblib.gz``
   + ``intermediates/model.joblib.gz``), so it doesn't depend on the
   ``project_to_subspace`` second-pass mechanic — relevant when the model
   stores dual coefficients (e.g. kernelized banded ridge) and the
   subject-scope projection helpers would slice the wrong matrix.

Materialises **primal feature weights** from dual coefficients on the fly:

    W_delayed = X_train_delayed.T @ dual_coef    # (n_delays·fdim, n_voxels)
    W_feature = mean over delays of W_delayed    # (fdim, n_voxels)
    projection = basis[:, :K].T @ W_feature      # (K, n_voxels)

Caches the per-subject (fdim, n_voxels) primal block as
``intermediates/weights_feature_avg.npy`` next to the model bundle so
threshold / channel iteration re-renders fast.
"""

from __future__ import annotations

import gzip
import logging
from pathlib import Path
from typing import Any

import numpy as np

from fmriflow.core.array_utils import make_delayed
from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_reporter
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_reporter("study_semantic_rgb_flatmap")
class StudySemanticRgbFlatmapReporter:
    """Per-subject semantic-PC RGB flatmap, with per-modality significance mask."""

    name = "study_semantic_rgb_flatmap"
    PARAM_SCHEMA = {
        "basis_path": {
            "type": "path",
            "required": True,
            "description": (
                "HDF5 file with a square ``(fdim, fdim)`` PCA basis under "
                "key ``c`` (Gallant-lab convention), columns ordered by "
                "descending variance. e.g. the english1000 semantic PCs."
            ),
        },
        "basis_key": {
            "type": "str",
            "default": "c",
            "description": "HDF5 dataset name for the basis matrix.",
        },
        "feature": {
            "type": "str",
            "default": "english1000",
            "description": (
                "Feature in each subject's ModelResult whose weight block "
                "to project. Must match exactly."
            ),
        },
        "n_components": {
            "type": "int",
            "default": 3,
            "description": "Number of leading PCs to project onto.",
        },
        "channels": {
            "type": "list[int]",
            "default": [0, 1, 2],
            "description": (
                "Which PC indices map to R, G, B respectively. The paper "
                "text reads 'first red, second blue, third green' which is "
                "[0, 2, 1]; the public-simplified.pkl viewer used [0, 1, 2]."
            ),
        },
        "thresholds": {
            "type": "dict",
            "default": {},
            "description": (
                "Mapping study-scope group label → per-voxel score floor "
                "for the 'significant' variant (e.g. {listening: 0.17, "
                "reading: 0.19}). Groups missing here use threshold 0."
            ),
        },
        "render_variants": {
            "type": "list[str]",
            "default": ["all", "significant"],
            "description": (
                "Which versions to emit. 'all' = no alpha mask, "
                "'significant' = alpha-mask via the modality's threshold."
            ),
        },
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename_pattern": {
            "type": "str",
            "default": "fig4_semantic_rgb_{group}_sub-{subject}_{variant}.png",
            "description": "Filename template. Tokens: {group}, {subject}, {variant}.",
        },
    }

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        basis_path = cfg.get("basis_path")
        if not basis_path or not Path(basis_path).is_file():
            logger.warning(
                "study_semantic_rgb_flatmap: basis_path missing or not a "
                "file: %s — skipping", basis_path)
            return {}

        try:
            import cortex                                          # noqa: F401
            from fmriflow.core.mask_utils import has_real_mask, unmask_scores
            import h5py
        except ImportError as exc:
            logger.warning(
                "study_semantic_rgb_flatmap: missing dep (%s) — skipping", exc)
            return {}

        n_components = int(cfg.get("n_components", 3))
        feature = cfg.get("feature", "english1000")
        channels = cfg.get("channels", [0, 1, 2])
        if len(channels) != 3:
            logger.warning(
                "study_semantic_rgb_flatmap: 'channels' must have 3 entries, "
                "got %s — skipping", channels)
            return {}
        if max(channels) + 1 > n_components:
            n_components = max(channels) + 1

        with h5py.File(basis_path, "r") as h:
            basis = np.asarray(h[cfg.get("basis_key", "c")],
                               dtype=np.float32)[:, :n_components]

        thresholds = cfg.get("thresholds") or {}
        variants = cfg.get("render_variants", ["all", "significant"])
        pattern = cfg.get(
            "filename_pattern",
            "fig4_semantic_rgb_{group}_sub-{subject}_{variant}.png")
        with_curvature = bool(cfg.get("with_curvature", True))
        dpi = int(cfg.get("dpi", 100))

        out_dir = Path(config.get("output_dir", ".")).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, str] = {}
        for group in study.groups:
            label = getattr(group, "study_label", None) or group.group_name
            threshold = float(thresholds.get(label, 0.0))
            logger.info(
                "study_semantic_rgb_flatmap: group=%s threshold=%.3f",
                label, threshold)
            for sr in group.subjects:
                run_dir = Path(sr.run_dir)
                try:
                    paths = _render_subject(
                        run_dir=run_dir, subject=sr.subject, group_label=label,
                        basis=basis, feature=feature, channels=channels,
                        threshold=threshold, variants=variants,
                        out_dir=out_dir, pattern=pattern,
                        with_curvature=with_curvature, dpi=dpi,
                    )
                except Exception as exc:
                    logger.warning(
                        "study_semantic_rgb_flatmap: %s/%s failed (%s) — skipping",
                        label, sr.subject, exc, exc_info=True)
                    continue
                for variant, p in paths.items():
                    outputs[f"semantic_rgb.{label}.{sr.subject}.{variant}"] = str(p)
        return outputs

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        if not cfg.get("basis_path"):
            errors.append("study_semantic_rgb_flatmap.basis_path is required")
        elif not Path(cfg["basis_path"]).is_file():
            errors.append(
                f"study_semantic_rgb_flatmap.basis_path not found: {cfg['basis_path']}")
        return errors


# ── helpers ────────────────────────────────────────────────────────────


def _read_subject_meta(run_dir: Path) -> tuple[str, str, str, list[int]] | None:
    """Return (surface, transform, mask_type, model_delays)."""
    import json
    summary = run_dir / "run_summary.json"
    if not summary.exists():
        return None
    cfg = (json.loads(summary.read_text()).get("config_snapshot") or {})
    sc = cfg.get("subject_config") or {}
    if not sc.get("surface") or not sc.get("transform"):
        return None
    mask_type = (cfg.get("response") or {}).get("mask_type") or "thick"
    delays = ((cfg.get("model") or {}).get("params") or {}).get("delays") or [1, 2, 3, 4]
    return sc["surface"], sc["transform"], mask_type, list(delays)


def _compute_feature_weights(run_dir: Path) -> np.ndarray | None:
    """Recover the delay-averaged primal weights (fdim, n_voxels). Cached."""
    import joblib

    cache = run_dir / "intermediates" / "weights_feature_avg.npy"
    model_pkl = run_dir / "intermediates" / "model.joblib.gz"
    prep_pkl = run_dir / "intermediates" / "prepare.joblib.gz"
    if not (model_pkl.exists() and prep_pkl.exists()):
        return None
    if cache.exists() and cache.stat().st_mtime >= model_pkl.stat().st_mtime:
        return np.load(cache, mmap_mode="r")

    with gzip.open(prep_pkl) as f:
        prepared = joblib.load(f)
    with gzip.open(model_pkl) as f:
        result = joblib.load(f)

    if (result.metadata or {}).get("is_dual") is True:
        meta = _read_subject_meta(run_dir)
        delays = meta[3] if meta else [1, 2, 3, 4]
        X = np.asarray(prepared.X_train, dtype=np.float32)
        X_delayed = make_delayed(X, delays).astype(np.float32)
        dual = np.asarray(result.weights, dtype=np.float32)
        primal_delayed = X_delayed.T @ dual                        # (n_delays·fdim, n_voxels)
        del X_delayed, dual
    else:
        primal_delayed = np.asarray(result.weights, dtype=np.float32)

    fdim = sum(int(x) for x in prepared.feature_dims)
    n_delays = primal_delayed.shape[0] // fdim
    primal = primal_delayed.reshape(n_delays, fdim,
                                    primal_delayed.shape[1]).mean(axis=0)
    primal = primal.astype(np.float32)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, primal)
    return primal


def _normalise_for_rgb(channel: np.ndarray) -> np.ndarray:
    """Symmetric-around-zero scale → [0, 255] uint8."""
    v = channel.astype(np.float32)
    scale = max(abs(np.nanmin(v)), abs(np.nanmax(v)), 1e-9)
    normed = (np.clip(v / scale, -1.0, 1.0) + 1.0) * 0.5 * 255.0
    return np.nan_to_num(normed, nan=0.0).astype(np.uint8)


def _render_subject(
    *, run_dir: Path, subject: str, group_label: str,
    basis: np.ndarray, feature: str, channels: list[int],
    threshold: float, variants: list[str],
    out_dir: Path, pattern: str,
    with_curvature: bool, dpi: int,
) -> dict[str, Path]:
    import cortex
    from fmriflow.core.mask_utils import has_real_mask, unmask_scores

    meta = _read_subject_meta(run_dir)
    if meta is None:
        logger.warning("  no pycortex meta for %s/%s — skipping",
                       group_label, subject)
        return {}
    surface, transform, mask_type, _ = meta

    primal = _compute_feature_weights(run_dir)
    if primal is None:
        logger.warning("  missing intermediates for %s/%s — skipping",
                       group_label, subject)
        return {}
    primal = np.asarray(primal)
    if primal.shape[0] != basis.shape[0]:
        logger.warning(
            "  basis fdim=%d but weights fdim=%d — skipping %s/%s",
            basis.shape[0], primal.shape[0], group_label, subject)
        return {}
    projection = basis.T @ primal                                  # (K, n_voxels)

    try:
        resp_mask = cortex.db.get_mask(surface, transform, mask_type)
    except Exception as exc:
        logger.warning(
            "  cortex.db.get_mask(%s, %s, %s) failed: %s — skipping",
            surface, transform, mask_type, exc)
        return {}

    rgb_channels: list[np.ndarray] = []
    for ch in channels:
        v = projection[ch]
        if has_real_mask(resp_mask):
            v = unmask_scores(v, resp_mask)
        rgb_channels.append(_normalise_for_rgb(v))

    scores = np.load(run_dir / "scores.npy").astype(np.float32)
    if has_real_mask(resp_mask):
        scores_full = unmask_scores(scores, resp_mask, fill_value=-np.inf)
    else:
        scores_full = scores

    paths: dict[str, Path] = {}
    for variant in variants:
        alpha = (
            (scores_full > threshold).astype(np.uint8) * 255
            if variant == "significant" else None
        )
        try:
            vol = cortex.VolumeRGB(
                rgb_channels[0], rgb_channels[1], rgb_channels[2],
                subject=surface, xfmname=transform, alpha=alpha,
            )
        except Exception as exc:
            logger.warning("  VolumeRGB %s failed: %s", variant, exc)
            continue
        path = out_dir / pattern.format(
            group=group_label, subject=subject, variant=variant)
        try:
            cortex.quickflat.make_png(
                str(path), vol, with_curvature=with_curvature, dpi=dpi)
        except Exception as exc:
            logger.warning("  quickflat make_png %s failed: %s", variant, exc)
            continue
        logger.info("  wrote %s", path.name)
        paths[variant] = path
    return paths
