"""StudyCrossModalFlatmap — per-subject cross-modal prediction flatmaps.

For every shared subject between two groups in the study run, apply one
modality's estimated semantic-model weights to the OTHER modality's
held-out test features, score the predictions against the other
modality's held-out test responses per voxel, and render as a
native-space flatmap. Two variants per subject:

* ``all``         — every cortical voxel coloured
* ``significant`` — voxels below ``threshold`` set to NaN so quickflat
                    shows curvature through them (= grey cortex)

One reporter entry renders one *direction* (a→b). List the entry twice
in ``study_report:`` to cover both directions (listening→reading and
reading→listening), mirroring the ``cross_modal_prediction`` analyzer's
config pattern.

Math:

    W_delayed = X_train_a_delayed.T @ dual_coef_a       # (n_delays·fdim, n_voxels)
    pred_b    = X_test_b_delayed @ W_delayed            # (n_test, n_voxels)
    score     = pearson(pred_b, Y_test_b)               # (n_voxels,)

Reads ``intermediates/prepare.joblib.gz`` + ``intermediates/model.joblib.gz``
per subject from disk, so it works on any study run where the group
configs saved both bundles. Sidesteps the dual-coefficient gap in the
subject-scope projection helpers — same trade-off as
``study_semantic_rgb_flatmap``.
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path

import numpy as np

from fmriflow.core.array_utils import make_delayed
from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_reporter
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_reporter("study_cross_modal_flatmap")
class StudyCrossModalFlatmapReporter:
    """Render per-subject cross-modal prediction-accuracy flatmaps."""

    name = "study_cross_modal_flatmap"
    PARAM_SCHEMA = {
        "weights_from": {
            "type": "str",
            "required": True,
            "description": (
                "Study-scope group label whose model weights are applied "
                "(the model side of the prediction)."
            ),
        },
        "features_from": {
            "type": "str",
            "required": True,
            "description": (
                "Study-scope group label whose X_test supplies the test "
                "features AND whose Y_test serves as ground truth."
            ),
        },
        "feature": {
            "type": "str",
            "default": "english1000",
            "description": (
                "Feature whose weights + test design columns are used. "
                "Must be the only feature in the model (single-band) for "
                "the matmul to make sense; otherwise the analyzer would "
                "need to slice the right block first."
            ),
        },
        "threshold": {
            "type": "float",
            "default": 0.10,
            "description": (
                "Per-voxel r-floor for the 'significant' variant. Default "
                "0.10 is a reasonable cross-modal FDR proxy at n_test≈300, "
                "~80k voxels; swap for per-subject FDR-derived values "
                "(e.g. from valmodelcorr CV folds) once available."
            ),
        },
        "render_variants": {
            "type": "list[str]",
            "default": ["all", "significant"],
            "description": "Which versions to emit per subject.",
        },
        "cmap": {"type": "str", "default": "hot"},
        "vmin": {"type": "float", "default": 0.0},
        "vmax": {"type": "float", "default": 0.4},
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename_pattern": {
            "type": "str",
            "default": "cross_pred_{weights_from}_to_{features_from}_sub-{subject}_{variant}.png",
            "description": (
                "Output filename template. Tokens: {subject}, {variant}, "
                "{weights_from}, {features_from}."
            ),
        },
    }

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        weights_from = cfg.get("weights_from")
        features_from = cfg.get("features_from")
        if not (weights_from and features_from):
            logger.warning(
                "study_cross_modal_flatmap: 'weights_from' and 'features_from' "
                "are required — skipping")
            return {}
        if weights_from == features_from:
            logger.warning(
                "study_cross_modal_flatmap: weights_from == features_from "
                "(%s) — within-modality already rendered by the r_flatmap "
                "subject reporter; skipping", weights_from)
            return {}

        try:
            import cortex                                                  # noqa: F401
        except ImportError as exc:
            logger.warning(
                "study_cross_modal_flatmap: pycortex not importable (%s) — skipping",
                exc)
            return {}

        feature = cfg.get("feature", "english1000")
        threshold = float(cfg.get("threshold", 0.10))
        variants = cfg.get("render_variants", ["all", "significant"])
        cmap = cfg.get("cmap", "hot")
        vmin = float(cfg.get("vmin", 0.0))
        vmax = float(cfg.get("vmax", 0.4))
        with_curvature = bool(cfg.get("with_curvature", True))
        dpi = int(cfg.get("dpi", 100))
        pattern = cfg.get(
            "filename_pattern",
            "cross_pred_{weights_from}_to_{features_from}_sub-{subject}_{variant}.png")

        out_dir = Path(config.get("output_dir", ".")).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            group_w = study.group(weights_from)
            group_f = study.group(features_from)
        except KeyError as exc:
            logger.warning("study_cross_modal_flatmap: %s — skipping", exc)
            return {}

        # Map subject → SubjectResult for each group, then intersect.
        w_by = {sr.subject: sr for sr in group_w.subjects}
        f_by = {sr.subject: sr for sr in group_f.subjects}
        common = sorted(set(w_by) & set(f_by))
        if not common:
            logger.warning(
                "study_cross_modal_flatmap: no shared subjects between '%s' and '%s'",
                weights_from, features_from)
            return {}
        logger.info(
            "study_cross_modal_flatmap: %s→%s — %d shared subjects: %s",
            weights_from, features_from, len(common), ", ".join(common))

        outputs: dict[str, str] = {}
        for sub in common:
            try:
                paths = _render_one(
                    sub=sub, sr_w=w_by[sub], sr_f=f_by[sub],
                    feature=feature, threshold=threshold,
                    variants=variants, out_dir=out_dir, pattern=pattern,
                    weights_from=weights_from, features_from=features_from,
                    cmap=cmap, vmin=vmin, vmax=vmax,
                    with_curvature=with_curvature, dpi=dpi,
                )
            except Exception as exc:
                logger.warning(
                    "study_cross_modal_flatmap: %s failed (%s) — skipping",
                    sub, exc, exc_info=True)
                continue
            for variant, p in paths.items():
                outputs[
                    f"cross_pred.{weights_from}_to_{features_from}.{sub}.{variant}"
                ] = str(p)
        return outputs

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        if not cfg.get("weights_from"):
            errors.append("study_cross_modal_flatmap.weights_from is required")
        if not cfg.get("features_from"):
            errors.append("study_cross_modal_flatmap.features_from is required")
        if cfg.get("weights_from") and cfg.get("weights_from") == cfg.get("features_from"):
            errors.append("study_cross_modal_flatmap: weights_from must differ from features_from")
        return errors


# ── helpers ────────────────────────────────────────────────────────────


def _read_subject_meta(run_dir: Path) -> tuple[str, str, str, list[int]] | None:
    """Return (surface, transform, mask_type, model_delays)."""
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


def _load_bundle(run_dir: Path) -> dict | None:
    """Load prepared + model intermediates from disk."""
    import joblib
    prep_pkl = run_dir / "intermediates" / "prepare.joblib.gz"
    model_pkl = run_dir / "intermediates" / "model.joblib.gz"
    if not (prep_pkl.exists() and model_pkl.exists()):
        return None
    with gzip.open(prep_pkl) as f:
        prepared = joblib.load(f)
    with gzip.open(model_pkl) as f:
        model_result = joblib.load(f)
    return {
        "X_train": np.asarray(prepared.X_train, dtype=np.float32),
        "X_test": np.asarray(prepared.X_test, dtype=np.float32),
        "Y_test": np.asarray(prepared.Y_test, dtype=np.float32),
        "feature_dims": [int(x) for x in prepared.feature_dims],
        "feature_names": list(prepared.feature_names),
        "weights": np.asarray(model_result.weights, dtype=np.float32),
        "is_dual": (model_result.metadata or {}).get("is_dual") is True,
    }


def _primal_delayed(bundle: dict, delays: list[int]) -> np.ndarray:
    """Recover delayed primal weights (n_delays·fdim, n_voxels)."""
    if not bundle["is_dual"]:
        return bundle["weights"]
    X_delayed = make_delayed(bundle["X_train"], delays).astype(np.float32)
    primal = X_delayed.T @ bundle["weights"]
    return primal.astype(np.float32)


def _pearson_per_voxel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-column Pearson r between two (n_rows, n_voxels) matrices."""
    a = a.astype(np.float64) - a.mean(axis=0, keepdims=True)
    b = b.astype(np.float64) - b.mean(axis=0, keepdims=True)
    num = (a * b).sum(axis=0)
    den = np.sqrt((a * a).sum(axis=0) * (b * b).sum(axis=0))
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(den > 0, num / den, np.nan)
    return r.astype(np.float32)


def _render_one(
    *, sub: str, sr_w, sr_f, feature: str, threshold: float,
    variants: list[str], out_dir: Path, pattern: str,
    weights_from: str, features_from: str,
    cmap: str, vmin: float, vmax: float, with_curvature: bool, dpi: int,
) -> dict[str, Path]:
    import cortex
    from fmriflow.core.mask_utils import has_real_mask, unmask_scores

    w_dir = Path(sr_w.run_dir)
    f_dir = Path(sr_f.run_dir)

    # Pycortex surface/transform come from the features-side subject (the
    # held-out responses define the cortical canvas we're rendering on).
    meta = _read_subject_meta(f_dir)
    if meta is None:
        logger.warning("  %s: no pycortex meta — skipping", sub)
        return {}
    surface, transform, mask_type, delays = meta

    w_bundle = _load_bundle(w_dir)
    f_bundle = _load_bundle(f_dir)
    if w_bundle is None or f_bundle is None:
        logger.warning("  %s: missing intermediates — skipping", sub)
        return {}

    if feature not in w_bundle["feature_names"]:
        logger.warning(
            "  %s: feature '%s' not in %s side (%s) — skipping",
            sub, feature, weights_from, w_bundle["feature_names"])
        return {}
    if w_bundle["feature_names"] != [feature]:
        logger.warning(
            "  %s: cross-modal flatmap assumes single-band model, found %s "
            "— skipping", sub, w_bundle["feature_names"])
        return {}

    W = _primal_delayed(w_bundle, delays)                      # (n_delays·fdim, n_voxels)
    X_test_delayed = make_delayed(f_bundle["X_test"], delays).astype(np.float32)
    Y_pred = X_test_delayed @ W
    del X_test_delayed, W
    score = _pearson_per_voxel(Y_pred, f_bundle["Y_test"])
    del Y_pred

    try:
        resp_mask = cortex.db.get_mask(surface, transform, mask_type)
    except Exception as exc:
        logger.warning(
            "  %s: get_mask(%s, %s, %s) failed: %s — skipping",
            sub, surface, transform, mask_type, exc)
        return {}

    if has_real_mask(resp_mask):
        full = unmask_scores(score, resp_mask, fill_value=np.nan)
    else:
        full = score

    paths: dict[str, Path] = {}
    for variant in variants:
        rendered = full.copy()
        if variant == "significant":
            rendered[rendered < threshold] = np.nan
        try:
            vol = cortex.Volume(rendered, surface, transform,
                                vmin=vmin, vmax=vmax, cmap=cmap)
        except Exception as exc:
            logger.warning("  %s: Volume %s failed: %s", sub, variant, exc)
            continue
        path = out_dir / pattern.format(
            subject=sub, variant=variant,
            weights_from=weights_from, features_from=features_from)
        try:
            cortex.quickflat.make_png(
                str(path), vol, with_curvature=with_curvature, dpi=dpi)
        except Exception as exc:
            logger.warning("  %s: quickflat %s failed: %s", sub, variant, exc)
            continue
        logger.info("  wrote %s", path.name)
        paths[variant] = path
    return paths
