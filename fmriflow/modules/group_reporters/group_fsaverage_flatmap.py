"""GroupFsaverageFlatmapReporter — render an fsaverage-space group artifact.

Reads a group artifact key (default ``group.fsaverage_scores_mean``) — typically
the output of ``voxelwise_mean`` operating on per-subject
``analysis.fsaverage_scores`` — and renders it on the fsaverage flatmap.

Typical use: render the group's mean prediction-accuracy map. The
companion subjects-passing-threshold "consistency" map uses the same
plumbing — point ``input_key`` at the count artifact and adjust
``vmin/vmax/cmap`` for discrete-count colouring.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.group_types import GroupResult
from fmriflow.modules._decorators import group_reporter
from fmriflow.modules.group_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@group_reporter("group_fsaverage_flatmap")
class GroupFsaverageFlatmapReporter:
    """Render a group-level fsaverage array on the fsaverage cortical surface."""

    name = "group_fsaverage_flatmap"
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "group.fsaverage_scores_mean",
            "description": "Key on GroupResult.artifacts holding the fsaverage array.",
        },
        "cmap": {"type": "string", "default": "inferno"},
        "vmin": {"type": "float", "default": 0.0},
        "vmax": {"type": "float", "default": 0.5},
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename": {"type": "str", "default": "group_fsaverage_flatmap.png"},
    }

    def report(self, group: GroupResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key", "group.fsaverage_scores_mean")
        if not group.has(input_key):
            logger.warning(
                "group_fsaverage_flatmap: '%s' not in group artifacts — "
                "did 'voxelwise_mean' run on a fsaverage-space input_key?",
                input_key)
            return {}
        arr = np.asarray(group.get(input_key)).astype(np.float32)

        try:
            import cortex
        except ImportError as exc:
            logger.warning(
                "group_fsaverage_flatmap: pycortex not importable: %s", exc)
            return {}

        outdir_str = cfg.get("output_dir") or config.get("output_dir")
        outdir = Path(outdir_str).resolve() if outdir_str else Path.cwd()
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / cfg.get("filename", "group_fsaverage_flatmap.png")

        try:
            vert = cortex.Vertex(
                arr, "fsaverage",
                vmin=cfg.get("vmin", 0.0),
                vmax=cfg.get("vmax", 0.5),
                cmap=cfg.get("cmap", "inferno"),
            )
        except Exception as exc:
            logger.warning(
                "group_fsaverage_flatmap: cortex.Vertex failed: %s", exc)
            return {}

        kwargs = dict(with_curvature=cfg.get("with_curvature", True), dpi=cfg.get("dpi", 100))
        try:
            cortex.quickflat.make_png(str(path), vert, **kwargs)
        except RuntimeError as exc:
            if 'inkscape' not in str(exc).lower():
                logger.warning("group_fsaverage_flatmap: quickflat.make_png failed: %s", exc)
                return {}
            logger.warning("inkscape not available — rendering group flatmap without ROI overlays")
            try:
                cortex.quickflat.make_png(str(path), vert, with_rois=False, with_labels=False, **kwargs)
            except Exception as exc2:
                logger.warning("group_fsaverage_flatmap: fallback render failed: %s", exc2)
                return {}
        except Exception as exc:
            logger.warning("group_fsaverage_flatmap: quickflat.make_png failed: %s", exc)
            return {}
        return {"group_fsaverage_flatmap": str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
