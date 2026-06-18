"""StudyAmodalFlatmap — per-subject within-vs-cross 2-channel flatmaps.

For every shared subject between two groups, pair:

* **Within-modality** per voxel = ``max(scores_a, scores_b)`` from the
  per-subject ``scores.npy`` files already on disk.
* **Cross-modal** per voxel    = ``mean(cross_a_to_b, cross_b_to_a)``
  computed in-place via the same primal-from-dual matmul that
  ``study_cross_modal_flatmap`` uses.

Map the pair onto an RGB scheme so a single flatmap reads as the
amodal-vs-modality-specific summary the paper's Fig 9 conveys:

* **Orange** (R=hi, G=mid, B=lo) — well predicted only within-modality
* **White**  (R=hi, G=hi,  B=hi) — well predicted both
* **Blue**   (R=lo, G=mid, B=hi) — well predicted only across-modality
* **Grey**   (transparent → curvature) — neither

Two variants per subject:

* ``all``         — alpha scales with ``max(within_norm, cross_norm)``
                    so sub-threshold voxels fade smoothly to grey cortex.
* ``significant`` — hard mask: voxels with ``within < within_threshold``
                    AND ``cross < cross_threshold`` are fully transparent.

Disk-driven (reads each subject's ``intermediates/{prepare,model}.joblib.gz``
+ ``scores.npy``) so it works on any study run that saved both
intermediate bundles. Same trade-off as ``study_semantic_rgb_flatmap``
and ``study_cross_modal_flatmap`` — sidesteps the dual-coefficient gap
in the subject-scope projection helpers.
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


@study_reporter("study_amodal_flatmap")
class StudyAmodalFlatmapReporter:
    """Per-subject within-vs-cross amodal flatmap with 4-corner colour scheme."""

    name = "study_amodal_flatmap"
    PARAM_SCHEMA = {
        "a": {
            "type": "str",
            "required": True,
            "description": "Study-scope label of the first group (e.g. listening).",
        },
        "b": {
            "type": "str",
            "required": True,
            "description": "Study-scope label of the second group (e.g. reading).",
        },
        "feature": {
            "type": "str",
            "default": "english1000",
            "description": (
                "Single-band feature whose weights drive the cross-modal "
                "prediction. Must be the only feature in both groups' models."
            ),
        },
        "within_threshold": {
            "type": "float",
            "default": 0.17,
            "description": "Per-voxel r-floor for within-modality significance.",
        },
        "cross_threshold": {
            "type": "float",
            "default": 0.10,
            "description": (
                "Per-voxel r-floor for cross-modal significance. Defaults "
                "to 0.10 as a cross-modal FDR proxy at n_test≈300; tune "
                "with cohort-specific values when available."
            ),
        },
        "within_vmax": {
            "type": "float",
            "default": 0.5,
            "description": "Saturation ceiling for within-modality colour intensity.",
        },
        "cross_vmax": {
            "type": "float",
            "default": 0.3,
            "description": "Saturation ceiling for cross-modal colour intensity.",
        },
        "render_variants": {
            "type": "list[str]",
            "default": ["all", "significant"],
            "description": "Which versions to emit per subject.",
        },
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename_pattern": {
            "type": "str",
            "default": "amodal_within_vs_cross_sub-{subject}_{variant}.png",
            "description": "Tokens: {subject}, {variant}.",
        },
    }

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        label_a = cfg.get("a")
        label_b = cfg.get("b")
        if not (label_a and label_b):
            logger.warning(
                "study_amodal_flatmap: 'a' and 'b' are required — skipping")
            return {}
        if label_a == label_b:
            logger.warning(
                "study_amodal_flatmap: 'a' and 'b' must differ — skipping")
            return {}

        try:
            import cortex                                                  # noqa: F401
        except ImportError as exc:
            logger.warning(
                "study_amodal_flatmap: pycortex not importable (%s) — skipping",
                exc)
            return {}

        feature = cfg.get("feature", "english1000")
        w_thr = float(cfg.get("within_threshold", 0.17))
        c_thr = float(cfg.get("cross_threshold", 0.10))
        w_vmax = float(cfg.get("within_vmax", 0.5))
        c_vmax = float(cfg.get("cross_vmax", 0.3))
        variants = cfg.get("render_variants", ["all", "significant"])
        with_curvature = bool(cfg.get("with_curvature", True))
        dpi = int(cfg.get("dpi", 100))
        pattern = cfg.get(
            "filename_pattern",
            "amodal_within_vs_cross_sub-{subject}_{variant}.png")

        out_dir = Path(config.get("output_dir", ".")).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            group_a = study.group(label_a)
            group_b = study.group(label_b)
        except KeyError as exc:
            logger.warning("study_amodal_flatmap: %s — skipping", exc)
            return {}

        a_by = {sr.subject: sr for sr in group_a.subjects}
        b_by = {sr.subject: sr for sr in group_b.subjects}
        common = sorted(set(a_by) & set(b_by))
        if not common:
            logger.warning(
                "study_amodal_flatmap: no shared subjects between '%s' and '%s'",
                label_a, label_b)
            return {}
        logger.info(
            "study_amodal_flatmap: %s↔%s — %d shared subjects: %s",
            label_a, label_b, len(common), ", ".join(common))

        outputs: dict[str, str] = {}
        for sub in common:
            try:
                paths = _render_amodal(
                    sub=sub, sr_a=a_by[sub], sr_b=b_by[sub],
                    feature=feature,
                    within_threshold=w_thr, cross_threshold=c_thr,
                    within_vmax=w_vmax, cross_vmax=c_vmax,
                    variants=variants, out_dir=out_dir, pattern=pattern,
                    with_curvature=with_curvature, dpi=dpi,
                )
            except Exception as exc:
                logger.warning(
                    "study_amodal_flatmap: %s failed (%s) — skipping",
                    sub, exc, exc_info=True)
                continue
            for variant, p in paths.items():
                outputs[f"amodal.{sub}.{variant}"] = str(p)
        return outputs

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        if not cfg.get("a"):
            errors.append("study_amodal_flatmap.a is required")
        if not cfg.get("b"):
            errors.append("study_amodal_flatmap.b is required")
        if cfg.get("a") and cfg.get("a") == cfg.get("b"):
            errors.append("study_amodal_flatmap: 'a' and 'b' must differ")
        return errors


# ── helpers ────────────────────────────────────────────────────────────


def _read_meta(run_dir: Path) -> tuple[str, str, str, list[int]] | None:
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
    import joblib
    prep_pkl = run_dir / "intermediates" / "prepare.joblib.gz"
    model_pkl = run_dir / "intermediates" / "model.joblib.gz"
    if not (prep_pkl.exists() and model_pkl.exists()):
        return None
    with gzip.open(prep_pkl) as f:
        prepared = joblib.load(f)
    with gzip.open(model_pkl) as f:
        result = joblib.load(f)
    return {
        "X_train": np.asarray(prepared.X_train, dtype=np.float32),
        "X_test": np.asarray(prepared.X_test, dtype=np.float32),
        "Y_test": np.asarray(prepared.Y_test, dtype=np.float32),
        "feature_names": list(prepared.feature_names),
        "weights": np.asarray(result.weights, dtype=np.float32),
        "is_dual": (result.metadata or {}).get("is_dual") is True,
    }


def _primal_delayed(bundle: dict, delays: list[int]) -> np.ndarray:
    if not bundle["is_dual"]:
        return bundle["weights"]
    X_delayed = make_delayed(bundle["X_train"], delays).astype(np.float32)
    return (X_delayed.T @ bundle["weights"]).astype(np.float32)


def _pearson_per_voxel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a.astype(np.float64) - a.mean(axis=0, keepdims=True)
    b = b.astype(np.float64) - b.mean(axis=0, keepdims=True)
    num = (a * b).sum(axis=0)
    den = np.sqrt((a * a).sum(axis=0) * (b * b).sum(axis=0))
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(den > 0, num / den, np.nan)
    return r.astype(np.float32)


def _cross_score(weights_bundle: dict, features_bundle: dict,
                 delays: list[int]) -> np.ndarray:
    W = _primal_delayed(weights_bundle, delays)
    X_other_delayed = make_delayed(features_bundle["X_test"], delays).astype(np.float32)
    Y_pred = X_other_delayed @ W
    del W, X_other_delayed
    return _pearson_per_voxel(Y_pred, features_bundle["Y_test"])


def _to_uint8(channel: np.ndarray) -> np.ndarray:
    out = np.clip(channel, 0.0, 1.0) * 255.0
    return np.nan_to_num(out, nan=0.0).astype(np.uint8)


def _render_amodal(
    *, sub: str, sr_a, sr_b, feature: str,
    within_threshold: float, cross_threshold: float,
    within_vmax: float, cross_vmax: float,
    variants: list[str], out_dir: Path, pattern: str,
    with_curvature: bool, dpi: int,
) -> dict[str, Path]:
    import cortex
    from fmriflow.core.mask_utils import has_real_mask, unmask_scores

    a_dir = Path(sr_a.run_dir)
    b_dir = Path(sr_b.run_dir)

    meta = _read_meta(a_dir)
    if meta is None:
        logger.warning("  %s: no pycortex meta — skipping", sub)
        return {}
    surface, transform, mask_type, delays = meta

    within_a = np.load(a_dir / "scores.npy").astype(np.float32)
    within_b = np.load(b_dir / "scores.npy").astype(np.float32)
    if within_a.shape != within_b.shape:
        logger.warning(
            "  %s: within shape mismatch %s vs %s — skipping",
            sub, within_a.shape, within_b.shape)
        return {}
    within = np.maximum(within_a, within_b)

    a_bundle = _load_bundle(a_dir)
    b_bundle = _load_bundle(b_dir)
    if a_bundle is None or b_bundle is None:
        logger.warning("  %s: missing intermediates — skipping", sub)
        return {}
    if a_bundle["feature_names"] != [feature] or b_bundle["feature_names"] != [feature]:
        logger.warning(
            "  %s: amodal flatmap assumes single-band model with feature '%s', "
            "found %s vs %s — skipping",
            sub, feature, a_bundle["feature_names"], b_bundle["feature_names"])
        return {}

    cross_a_to_b = _cross_score(a_bundle, b_bundle, delays)
    cross_b_to_a = _cross_score(b_bundle, a_bundle, delays)
    if cross_a_to_b.shape != within.shape or cross_b_to_a.shape != within.shape:
        logger.warning("  %s: cross-modal shape mismatch — skipping", sub)
        return {}
    cross = 0.5 * (cross_a_to_b + cross_b_to_a)
    del a_bundle, b_bundle, cross_a_to_b, cross_b_to_a

    try:
        resp_mask = cortex.db.get_mask(surface, transform, mask_type)
    except Exception as exc:
        logger.warning(
            "  %s: get_mask(%s, %s, %s) failed: %s — skipping",
            sub, surface, transform, mask_type, exc)
        return {}

    w = np.clip(within / max(within_vmax, 1e-9), 0.0, 1.0).astype(np.float32)
    c = np.clip(cross / max(cross_vmax, 1e-9), 0.0, 1.0).astype(np.float32)
    R = w
    G = 0.5 * (w + c)
    B = c

    if has_real_mask(resp_mask):
        R_full = unmask_scores(R, resp_mask, fill_value=0.0)
        G_full = unmask_scores(G, resp_mask, fill_value=0.0)
        B_full = unmask_scores(B, resp_mask, fill_value=0.0)
        within_full = unmask_scores(within, resp_mask, fill_value=-np.inf)
        cross_full = unmask_scores(cross, resp_mask, fill_value=-np.inf)
        w_full = unmask_scores(w, resp_mask, fill_value=0.0)
        c_full = unmask_scores(c, resp_mask, fill_value=0.0)
    else:
        R_full, G_full, B_full = R, G, B
        within_full, cross_full = within, cross
        w_full, c_full = w, c

    R_u, G_u, B_u = _to_uint8(R_full), _to_uint8(G_full), _to_uint8(B_full)

    paths: dict[str, Path] = {}
    for variant in variants:
        if variant == "all":
            alpha_f = np.maximum(w_full, c_full) * 255.0
            alpha = np.nan_to_num(alpha_f, nan=0.0).astype(np.uint8)
        elif variant == "significant":
            sig = ((within_full > within_threshold)
                   | (cross_full > cross_threshold)).astype(np.uint8)
            alpha = sig * 255
        else:
            logger.warning("  %s: unknown variant '%s'", sub, variant)
            continue
        try:
            vol = cortex.VolumeRGB(
                R_u, G_u, B_u,
                subject=surface, xfmname=transform, alpha=alpha,
            )
        except Exception as exc:
            logger.warning("  %s: VolumeRGB %s failed: %s", sub, variant, exc)
            continue
        path = out_dir / pattern.format(subject=sub, variant=variant)
        try:
            cortex.quickflat.make_png(
                str(path), vol,
                with_curvature=with_curvature, dpi=dpi,
            )
        except Exception as exc:
            logger.warning("  %s: quickflat %s failed: %s", sub, variant, exc)
            continue
        logger.info("  wrote %s", path.name)
        paths[variant] = path
    return paths
