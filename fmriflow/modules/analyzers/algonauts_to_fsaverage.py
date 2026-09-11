"""Expand Algonauts 2023 challenge-space vertex scores onto the full fsaverage surface.

The Algonauts response loader delivers scores over each subject's *challenge
space* (the per-subject subset of fsaverage vertices with valid data), which
differs between subjects.  To average or compare across subjects, each subject's
scores must live on a common grid.  This analyzer expands ``result.scores`` back
onto the full fsaverage surface (LH then RH concatenated), zero-filling vertices
outside the subject's challenge space, and stores the result at
``analysis.<output_key>``.

Group-scope ``voxelwise_mean`` (a plain mean) can then average the shape-
consistent per-subject arrays, and ``group_fsaverage_flatmap`` can render the
group-average prediction-accuracy map.  Zeros are used (not NaN) so the plain
group mean stays defined over the *union* of subjects' challenge spaces;
non-visual cortex reads ~0 anyway.

Fails gracefully (logs + stores nothing) when the ``algonauts2023`` response
loader's ``fsaverage_masks`` / ``hemi_dims`` metadata is absent.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.modules._decorators import analyzer

logger = logging.getLogger(__name__)


@analyzer("algonauts_to_fsaverage")
class AlgonautsToFsaverageAnalyzer:
    """Map Algonauts challenge-space ``result.scores`` onto full fsaverage vertices."""

    name = "algonauts_to_fsaverage"
    PARAM_SCHEMA = {
        "input_key": {"type": "str", "default": "result.scores", "description": "Dotted context path to the per-vertex scores"},
        "output_key": {"type": "str", "default": "analysis.fsaverage_scores", "description": "Where to store the (n_fsavg_verts,) array"},
    }

    def analyze(self, context, config: dict) -> None:
        acfg = _my_cfg(config, self.name)
        input_key = acfg.get("input_key", "result.scores")
        output_key = acfg.get("output_key", "analysis.fsaverage_scores")

        scores = _resolve_subject_key(context, input_key)
        if scores is None:
            logger.warning("algonauts_to_fsaverage: '%s' not in context — skipping", input_key)
            return
        if not context.has("responses"):
            logger.warning("algonauts_to_fsaverage: no responses in context — skipping")
            return
        resp = context.get("responses", ResponseData)
        masks = resp.metadata.get("fsaverage_masks", {})
        hemi_dims = resp.metadata.get("hemi_dims", {})
        hemis = resp.metadata.get("hemispheres", ["lh", "rh"])
        if not masks or not hemi_dims:
            logger.warning("algonauts_to_fsaverage: response carries no fsaverage_masks/"
                           "hemi_dims (need the algonauts2023 loader) — skipping")
            return

        # The loader only carries masks for hemispheres whose mask file exists;
        # skip clearly on any missing hemisphere or score-length mismatch rather
        # than KeyError-ing or producing an incorrectly offset expansion.
        missing = [h for h in hemis if h not in masks or h not in hemi_dims]
        if missing:
            logger.warning("algonauts_to_fsaverage: missing fsaverage_masks/hemi_dims "
                           "for %s — skipping", missing)
            return

        scores = np.asarray(scores, dtype=np.float32)
        total = sum(hemi_dims[h] for h in hemis)
        if scores.shape[0] != total:
            logger.warning("algonauts_to_fsaverage: scores length %d != sum(hemi_dims) "
                           "%d — skipping", scores.shape[0], total)
            return
        parts, offset = [], 0
        for h in hemis:
            d = hemi_dims[h]
            full = np.zeros(masks[h].shape[0], dtype=np.float32)
            full[masks[h]] = scores[offset:offset + d]
            offset += d
            parts.append(full)
        fsaverage = np.concatenate(parts)   # lh then rh
        context.put(output_key, fsaverage)
        logger.info("algonauts_to_fsaverage: stored %s %s", output_key, fsaverage.shape)

    def validate_config(self, config: dict) -> list[str]:
        return []


# ─── helpers (mirrors project_to_fsaverage) ───────────────────────

def _my_cfg(config: dict, name: str) -> dict:
    for entry in config.get("analysis", []) or []:
        if entry.get("name") == name:
            return entry.get("params", {}) or {}
    return {}


from fmriflow.core.context_keys import resolve_context_key as _resolve_subject_key  # noqa: E402
