"""Project a subject's per-voxel scores onto the fsaverage cortical surface.

Two-step pipeline:

1. ``cortex.get_mapper(subject, xfm, 'nearest')`` produces a volume → subject
   native vertex mapping. Apply it to a ``cortex.Volume`` wrapping the scores.
2. For each hemisphere, ``cortex.freesurfer.mri_surf2surf(data, source_subj,
   'fsaverage', hemi)`` resamples the subject's native vertices onto fsaverage.
   The two hemispheres are concatenated into a single ``(2*n_fsavg_verts,)``
   array.

The result is stored in the subject's :class:`PipelineContext` under
``analysis.<output_key>`` (default ``analysis.fsaverage_scores``). Downstream
plugins that operate in fsaverage space (the ``fsaverage_flatmap`` reporter,
group-scope ``voxelwise_mean`` / ``significance_count`` analyzers) can then
consume a shape-consistent representation across subjects — required by
any cross-subject group flatmap or consistency analysis.

This analyzer fails gracefully when:
- pycortex's mask voxel count doesn't match ``result.scores.shape[0]`` (see
  error KB 0035 — same root cause as the flatmap-skip);
- FreeSurfer is not installed / ``$FREESURFER_HOME`` is unset;
- the source freesurfer subject is missing from ``$SUBJECTS_DIR``.

In all cases the analyzer logs a clear warning and stores nothing, so the rest
of the report stage proceeds.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

from fmriflow.core.mask_utils import has_real_mask, unmask_scores
from fmriflow.core.types import ModelResult, ResponseData
from fmriflow.modules._decorators import analyzer

logger = logging.getLogger(__name__)


@analyzer("project_to_fsaverage")
class ProjectToFsaverageAnalyzer:
    """Map ``result.scores`` (or any per-voxel array) onto fsaverage vertices."""

    name = "project_to_fsaverage"
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "result.scores",
            "description": (
                "Dotted path into context. Default reads the model's "
                "prediction-accuracy scores."
            ),
        },
        "output_key": {
            "type": "str",
            "default": "analysis.fsaverage_scores",
            "description": "Where to store the projected (n_fsavg_verts,) array.",
        },
        "freesurfer_subject": {
            "type": "str",
            "description": (
                "FreeSurfer subject name. Defaults to the pycortex surface "
                "name (e.g. 'sub01fs') which is the conventional layout in this lab."
            ),
        },
        "subjects_dir": {
            "type": "str",
            "description": (
                "FreeSurfer SUBJECTS_DIR. Defaults to $SUBJECTS_DIR env var."
            ),
        },
    }

    def analyze(self, context, config: dict) -> None:
        # The whole body is wrapped: a failure here must NOT take down the
        # analyze stage (which would also skip the report stage). The
        # analyzer is best-effort — its absence is recoverable downstream.
        try:
            self._do_analyze(context, config)
        except _SkipFsaverage as exc:
            logger.warning("project_to_fsaverage: skipped (%s)", exc)
        except Exception:
            logger.warning(
                "project_to_fsaverage: unexpected error — skipping. "
                "(See the traceback below; the report stage will still run.)",
                exc_info=True)

    def _do_analyze(self, context, config: dict) -> None:
        acfg = _my_cfg(config, self.name)
        input_key = acfg.get("input_key", "result.scores")
        output_key = acfg.get("output_key", "analysis.fsaverage_scores")

        scores = _resolve_subject_key(context, input_key)
        if scores is None:
            raise _SkipFsaverage(
                f"'{input_key}' not in context — nothing to project")
        scores = np.asarray(scores).astype(np.float32)

        if not context.has("responses"):
            raise _SkipFsaverage("'responses' missing from context")
        resp_data = context.get("responses", ResponseData)
        surface = resp_data.surface
        transform = resp_data.transform

        fs_subject = acfg.get("freesurfer_subject") or surface
        subjects_dir = acfg.get("subjects_dir") or os.environ.get("SUBJECTS_DIR")

        fsaverage = _project_to_fsaverage(
            scores, surface=surface, transform=transform,
            fs_subject=fs_subject, subjects_dir=subjects_dir,
            resp_mask=resp_data.mask,
        )

        context.put(output_key, fsaverage)
        logger.info(
            "project_to_fsaverage: wrote '%s' shape=%s dtype=%s",
            output_key, fsaverage.shape, fsaverage.dtype)

    def validate_config(self, config: dict) -> list[str]:
        return []


# ─── helpers ───────────────────────────────────────────────────


class _SkipFsaverage(Exception):
    """Raised by the projection helper to skip cleanly with a log message."""


def _my_cfg(config: dict, name: str) -> dict:
    for entry in config.get("analysis", []) or []:
        if entry.get("name") == name:
            return entry.get("params", {}) or {}
    return {}


from fmriflow.core.context_keys import resolve_context_key as _resolve_subject_key  # noqa: E402


def _project_to_fsaverage(scores: np.ndarray, *, surface: str, transform: str,
                          fs_subject: str, subjects_dir: str | None,
                          resp_mask: np.ndarray) -> np.ndarray:
    """Return scores resampled onto fsaverage vertices (L + R concatenated)."""
    try:
        import cortex
        from cortex.freesurfer import mri_surf2surf
    except ImportError as exc:
        raise _SkipFsaverage(f"pycortex not importable: {exc}") from exc

    # Step 1: wrap scores in a Volume; expand to full volume if there's a
    # real mask (matches flatmap reporter behaviour).
    s = scores.copy()
    if has_real_mask(resp_mask):
        s = unmask_scores(s, resp_mask)
    try:
        vol = cortex.Volume(s, surface, transform)
    except ValueError as exc:
        if "mask" in str(exc).lower():
            n_scores = s.shape[-1] if s.ndim > 1 else s.shape[0]
            try:
                db_mask = cortex.db.get_mask(surface, transform, "thick")
                n_mask = int(db_mask.sum())
            except Exception:
                n_mask = "?"
            raise _SkipFsaverage(
                f"mask/voxel mismatch: scores={n_scores} mask={n_mask}"
            ) from exc
        raise
    except KeyError as exc:
        # pycortex raises KeyError when the subject isn't in its DB.
        raise _SkipFsaverage(
            f"pycortex subject '{surface}' not found in DB"
        ) from exc

    # Step 2: volume → subject native vertices.
    mapper = cortex.get_mapper(surface, transform, "nearest")
    vertex = mapper(vol)
    # Vertex.data is a flat (n_lh + n_rh,) array; .left and .right slice it.
    data_lh = np.asarray(vertex.left)
    data_rh = np.asarray(vertex.right)

    # Step 3: subject-native vertices → fsaverage vertices via FreeSurfer.
    if not subjects_dir:
        raise _SkipFsaverage(
            "SUBJECTS_DIR not set and 'subjects_dir' param not given — "
            "FreeSurfer mri_surf2surf needs a subjects directory")
    if not os.environ.get("FREESURFER_HOME"):
        raise _SkipFsaverage(
            "FREESURFER_HOME not set — source SetUpFreeSurfer.sh first")
    sd_path = Path(subjects_dir)
    if not (sd_path / fs_subject).is_dir():
        raise _SkipFsaverage(
            f"FreeSurfer subject '{fs_subject}' not found under {sd_path}")

    try:
        # mri_surf2surf returns (1, n_fsavg_verts) for a single image input.
        lh_fs = mri_surf2surf(data_lh[None, :], fs_subject, "fsaverage", "lh",
                              subjects_dir=str(sd_path))
        rh_fs = mri_surf2surf(data_rh[None, :], fs_subject, "fsaverage", "rh",
                              subjects_dir=str(sd_path))
    except Exception as exc:
        raise _SkipFsaverage(f"mri_surf2surf failed: {exc}") from exc

    lh_fs = np.asarray(lh_fs).reshape(-1)
    rh_fs = np.asarray(rh_fs).reshape(-1)
    return np.concatenate([lh_fs, rh_fs]).astype(np.float32)
