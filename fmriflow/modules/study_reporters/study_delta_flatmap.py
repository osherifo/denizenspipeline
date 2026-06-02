"""StudyDeltaFlatmapReporter — render a study-level array on a flatmap.

Reads a study-artifact key (typically the output of ``group_delta`` or
``cohen_d_across_groups``) and renders it on the fsaverage cortical
surface via pycortex. Defaults to a diverging colormap centred on zero
since the prototypical input is an A-B delta.

``space:`` is fsaverage for v1; MNI volumetric support is an opt-in
once the lab's pycortex MNI transforms are wired up — same shape, just
swap the Vertex/Volume constructor.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_reporter
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_reporter("study_delta_flatmap")
class StudyDeltaFlatmapReporter:
    """Render a study-level array (delta-map, Cohen's d, etc.) on a flatmap."""

    name = "study_delta_flatmap"
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "description": (
                "Study-artifact key holding the array to render "
                "(e.g. 'study.delta_r_minus_l')."
            ),
        },
        "space": {
            "type": "str",
            "default": "fsaverage",
            "enum": ["fsaverage"],
            "description": "Common space the array is in. Only fsaverage in v1.",
        },
        "cmap": {"type": "string", "default": "RdBu_r"},
        "vmin": {"type": "float", "default": -0.2},
        "vmax": {"type": "float", "default": 0.2},
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename": {"type": "str", "description": "Output PNG filename."},
    }

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key")
        if not input_key:
            logger.warning("study_delta_flatmap: missing 'input_key' param")
            return {}
        if not study.has(input_key):
            logger.warning(
                "study_delta_flatmap: '%s' not in study artifacts — "
                "did a study_analyze plugin write it?", input_key)
            return {}

        space = cfg.get("space", "fsaverage")
        if space != "fsaverage":
            logger.warning(
                "study_delta_flatmap: space='%s' not supported in v1 "
                "(only 'fsaverage')", space)
            return {}

        arr = np.asarray(study.get(input_key)).astype(np.float32)

        try:
            import cortex
        except ImportError as exc:
            logger.warning("study_delta_flatmap: pycortex not importable: %s", exc)
            return {}

        outdir_str = cfg.get("output_dir") or config.get("output_dir")
        outdir = Path(outdir_str).resolve() if outdir_str else Path.cwd()
        outdir.mkdir(parents=True, exist_ok=True)
        default_fname = f"{input_key.replace('.', '_')}_flatmap.png"
        path = outdir / cfg.get("filename", default_fname)

        try:
            vert = cortex.Vertex(
                arr, "fsaverage",
                vmin=cfg.get("vmin", -0.2),
                vmax=cfg.get("vmax", 0.2),
                cmap=cfg.get("cmap", "RdBu_r"),
            )
        except Exception as exc:
            logger.warning("study_delta_flatmap: cortex.Vertex failed: %s", exc)
            return {}

        try:
            cortex.quickflat.make_png(
                str(path), vert,
                with_curvature=cfg.get("with_curvature", True),
                dpi=cfg.get("dpi", 100),
            )
        except Exception as exc:
            logger.warning(
                "study_delta_flatmap: quickflat.make_png failed: %s", exc)
            return {}
        return {"study_delta_flatmap": str(path)}

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        if not cfg.get("input_key"):
            return ["study_delta_flatmap.input_key is required"]
        return []
