"""BidsResponseLoader — loads fMRI responses from BIDS-formatted datasets."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.plugins._decorators import response_loader
from fmriflow.plugins.response_loaders.local import (
    LocalResponseLoader,
    _NO_MASK,
)

logger = logging.getLogger(__name__)

# Regex to extract BIDS entities from a filename
_ENTITY_RE = re.compile(r"([\w]+)-([\w]+)")


def _parse_bids_entities(filename: str) -> dict[str, str]:
    """Extract BIDS key-value entities from a filename stem.

    Example: ``sub-01_ses-movie_task-movie_run-01_bold``
    → ``{'sub': '01', 'ses': 'movie', 'task': 'movie', 'run': '01'}``
    """
    return dict(_ENTITY_RE.findall(filename))


@response_loader("bids")
class BidsResponseLoader:
    """Loads fMRI responses from a BIDS-formatted directory.

    Auto-discovers functional runs across sessions by parsing BIDS
    filenames, loads NIfTI data via nibabel, and handles cortical masking.

    Config keys (under ``response:``):

    - ``path`` — BIDS dataset root
    - ``task`` — BIDS task label (required)
    - ``sessions`` — list of session labels; auto-discovered if omitted
    - ``suffix`` — BIDS file suffix (default ``bold``)
    - ``extension`` — file extension (default ``.nii.gz``)
    - ``run_map`` — optional dict remapping BIDS run names to pipeline names
    - ``mask_type`` — pycortex mask type (default ``thick``)
    """

    name = "bids"

    PARAM_SCHEMA = {
        "path": {"type": "path", "required": True, "description": "BIDS dataset root directory"},
        "task": {"type": "string", "required": True, "description": "BIDS task label"},
        "sessions": {"type": "list[string]", "description": "Session labels (auto-discovered if omitted)"},
        "suffix": {"type": "string", "default": "bold", "description": "BIDS file suffix"},
        "extension": {"type": "string", "default": ".nii.gz", "description": "File extension"},
        "run_map": {"type": "dict", "description": "Remap BIDS run names to pipeline names"},
        "mask_type": {"type": "string", "default": "thick", "description": "Pycortex cortical mask type"},
    }

    def load(self, config: dict) -> ResponseData:
        try:
            import nibabel as nib
        except ImportError:
            raise ImportError(
                "nibabel is required for the BIDS response loader. "
                "Install it with: pip install 'fmriflow[bids]'"
            )

        resp_cfg = config.get("response", {})
        sub_cfg = config.get("subject_config", {})

        surface = sub_cfg.get("surface", "unknown")
        transform = sub_cfg.get("transform", "unknown")

        bids_root = Path(resp_cfg["path"])
        subject = config["subject"]
        task = resp_cfg["task"]
        suffix = resp_cfg.get("suffix", "bold")
        extension = resp_cfg.get("extension", ".nii.gz")
        sessions = resp_cfg.get("sessions")

        sub_dir = bids_root / f"sub-{subject}"

        # ── 1. Resolve sessions ──────────────────────────────────────
        if sessions is not None:
            session_dirs = []
            for ses in sessions:
                ses_label = ses if ses.startswith("ses-") else f"ses-{ses}"
                session_dirs.append((ses_label, sub_dir / ses_label / "func"))
        else:
            # Auto-discover ses-* directories
            ses_candidates = sorted(sub_dir.glob("ses-*"))
            if ses_candidates:
                session_dirs = [
                    (d.name, d / "func")
                    for d in ses_candidates
                    if d.is_dir() and (d / "func").is_dir()
                ]
            else:
                # Sessionless layout: sub-XX/func/
                session_dirs = [(None, sub_dir / "func")]

        # ── 2. Glob for matching NIfTI files ─────────────────────────
        glob_pattern = f"*_task-{task}_*_{suffix}{extension}"
        raw_responses: dict[str, np.ndarray] = {}

        for ses_label, func_dir in session_dirs:
            if not func_dir.is_dir():
                logger.warning("func directory not found: %s", func_dir)
                continue

            matches = sorted(func_dir.glob(glob_pattern))
            if not matches:
                logger.warning(
                    "No files matching task=%s in %s", task, func_dir
                )
                continue

            for nii_path in matches:
                entities = _parse_bids_entities(nii_path.name)

                # Build run name from session + run entities
                run_parts = []
                if ses_label is not None:
                    run_parts.append(ses_label)
                if "run" in entities:
                    run_parts.append(f"run-{entities['run']}")
                if run_parts:
                    run_name = "_".join(run_parts)
                else:
                    # Fallback: use filename without NIfTI extension (.nii or .nii.gz)
                    if nii_path.suffixes[-2:] == [".nii", ".gz"]:
                        # Strip full .nii.gz
                        run_name = nii_path.name[:-7]
                    else:
                        run_name = nii_path.stem

                # Load NIfTI
                img = nib.load(nii_path)
                data = img.get_fdata()
                # Squeeze trailing singleton dims (e.g. 4-D with dim4=1)
                while data.ndim > 2 and data.shape[-1] == 1:
                    data = data.squeeze(axis=-1)

                logger.info(
                    "Loaded %s → %s  shape=%s",
                    nii_path.name,
                    run_name,
                    data.shape,
                )
                raw_responses[run_name] = data

        # ── 3. Apply run_map ─────────────────────────────────────────
        run_map = resp_cfg.get("run_map", {})
        if run_map:
            raw_responses = {
                run_map.get(k, k): v for k, v in raw_responses.items()
            }

        # ── 4. Apply cortical mask (volumetric only) ─────────────────
        is_volumetric = any(arr.ndim > 2 for arr in raw_responses.values())

        if is_volumetric:
            responses, mask = LocalResponseLoader._apply_mask(
                raw_responses,
                surface,
                transform,
                resp_cfg.get("mask_type", "thick"),
            )
        else:
            if raw_responses:
                logger.info(
                    "Response data is 2-D (pre-masked), skipping "
                    "cortical mask extraction"
                )
            responses = raw_responses
            mask = _NO_MASK

        return ResponseData(
            responses=responses,
            mask=mask,
            surface=surface,
            transform=transform,
        )

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        resp_cfg = config.get("response", {})

        if "path" not in resp_cfg:
            errors.append("bids loader requires response.path (BIDS root)")
        elif not Path(resp_cfg["path"]).is_dir():
            errors.append(
                f"response.path is not a directory: {resp_cfg['path']}"
            )

        if "task" not in resp_cfg:
            errors.append(
                "bids loader requires response.task (BIDS task label)"
            )

        return errors
