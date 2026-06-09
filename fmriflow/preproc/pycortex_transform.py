"""Pycortex transform creation — the EPI→anatomy alignment step.

Runs *after* autoflatten (which imports the FreeSurfer subject into pycortex).
Given a functional **reference** volume (a boldref or the temporal mean of a run)
it produces a named pycortex **transform** (``xfm``) aligning that functional grid
to the subject's cortical surface, via ``cortex.align``:

- ``automatic``     — FreeSurfer ``bbregister`` + ``mri_coreg`` (pycortex's default). Requires the
  FreeSurfer subject to be discoverable under ``$SUBJECTS_DIR`` **named like the pycortex subject**.
- ``automatic_fsl`` — FSL FLIRT BBR using the pycortex-stored surfaces (no ``$SUBJECTS_DIR`` name
  dependency); requires FSL on PATH.
- ``manual``        — opens pycortex's interactive aligner (blocking; not headless).

The transform is stored in the pycortex **filestore** (never the FreeSurfer
subject folder). Downstream, flatmap reporters and ``project_to_fsaverage``
consume it via ``cortex.Volume(scores, surface, xfmname)`` /
``cortex.get_mapper(surface, xfmname, ...)``.

See ``devdocs/projectboard/cards/05-pycortex-transforms.md`` for the design and the
mask-voxel-count constraint (error KB 0035).
"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Reuse the pycortex availability check + subject-listing helper from autoflatten
# so there is one implementation of each.
from fmriflow.preproc.autoflatten import (
    check_pycortex_available,
    _pycortex_subject_list,
)

logger = logging.getLogger(__name__)

VALID_METHODS = ("automatic", "automatic_fsl", "manual")
DEFAULT_XFMNAME = "fmriflow"


# ── Config ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PycortexTransformConfig:
    """Configuration for creating a pycortex transform."""

    cx_subject: str               # pycortex subject name, e.g. "ANfs"
    reference: str                # path to the functional reference volume (NIfTI)
    xfmname: str = DEFAULT_XFMNAME
    method: str = "automatic"     # "automatic" | "manual"
    overwrite: bool = False

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty == valid)."""
        errors: list[str] = []

        if not self.cx_subject:
            errors.append("cx_subject is required (pycortex subject name)")
        if not self.xfmname:
            errors.append("xfmname is required")
        if self.method not in VALID_METHODS:
            errors.append(
                f"Invalid method '{self.method}'. "
                f"Must be one of: {', '.join(VALID_METHODS)}"
            )
        if not self.reference:
            errors.append("reference is required (path to a functional EPI volume)")
        elif not Path(self.reference).is_file():
            errors.append(f"Reference volume not found: {self.reference}")

        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PycortexTransformConfig":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in valid})


# ── Result ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PycortexTransformResult:
    """Result of a transform-creation run."""

    cx_subject: str
    xfmname: str
    reference: str
    method: str
    n_mask_voxels: int | None     # voxels in the 'thick' cortical mask, if computable
    filestore: str
    created: bool                 # True if newly created, False if reused existing
    elapsed_s: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Availability ──────────────────────────────────────────────────────────


def check_fsl_available() -> tuple[bool, str]:
    """Check whether FSL FLIRT is on PATH (needed for automatic alignment)."""
    if shutil.which("flirt") is not None:
        return True, "FSL flirt found"
    return False, (
        "FSL flirt not found on PATH — required for method='automatic'. "
        "Source FSL (e.g. `source /etc/fsl/fsl.sh`) or use method='manual'."
    )


# ── Core ──────────────────────────────────────────────────────────────────


def transform_exists(cx_subject: str, xfmname: str) -> bool:
    """Return True if ``xfmname`` already exists for ``cx_subject`` in the store."""
    import cortex

    try:
        cortex.db.get_xfm(cx_subject, xfmname)
        return True
    except Exception:
        return False


def mask_voxel_count(cx_subject: str, xfmname: str, mask_type: str = "thick") -> int | None:
    """Return the voxel count of the cortical mask for (subject, xfm), or None."""
    import cortex

    try:
        return int(cortex.db.get_mask(cx_subject, xfmname, mask_type).sum())
    except Exception as exc:  # pragma: no cover - depends on pycortex state
        logger.warning("Could not compute mask voxel count: %s", exc)
        return None


def create_transform(config: PycortexTransformConfig) -> PycortexTransformResult:
    """Create (or reuse) a pycortex transform aligning ``reference`` to ``cx_subject``.

    Execution:
      1. Validate config + pycortex availability (and FSL for automatic).
      2. Verify the pycortex subject exists (autoflatten must have imported it).
      3. If the transform exists and ``overwrite`` is False → reuse it.
      4. Otherwise run ``cortex.align.{automatic,manual}``.
      5. Report the resulting cortical-mask voxel count.
    """
    start = time.time()

    errs = config.validate()
    if errs:
        raise ValueError("Invalid PycortexTransformConfig:\n  " + "\n  ".join(errs))

    ok, msg = check_pycortex_available()
    if not ok:
        raise RuntimeError(msg)

    if config.method == "automatic_fsl":
        ok, msg = check_fsl_available()
        if not ok:
            raise RuntimeError(msg)

    import cortex
    import cortex.align

    filestore = str(cortex.database.default_filestore)

    subjects = _pycortex_subject_list(cortex)
    if config.cx_subject not in subjects:
        raise RuntimeError(
            f"pycortex subject '{config.cx_subject}' not found in the filestore "
            f"({filestore}). Run autoflatten / import the subject first. "
            f"Known subjects: {subjects}"
        )

    already = transform_exists(config.cx_subject, config.xfmname)
    if already and not config.overwrite:
        logger.info(
            "Transform '%s' already exists for '%s' — reusing (pass overwrite=True to redo).",
            config.xfmname, config.cx_subject,
        )
        n = mask_voxel_count(config.cx_subject, config.xfmname)
        return PycortexTransformResult(
            cx_subject=config.cx_subject,
            xfmname=config.xfmname,
            reference=config.reference,
            method=config.method,
            n_mask_voxels=n,
            filestore=filestore,
            created=False,
            elapsed_s=time.time() - start,
        )

    logger.info(
        "Creating pycortex transform '%s' for '%s' (method=%s) against %s",
        config.xfmname, config.cx_subject, config.method, config.reference,
    )

    if config.method == "automatic":
        cortex.align.automatic(config.cx_subject, config.xfmname, config.reference)
    elif config.method == "automatic_fsl":
        cortex.align.automatic_fsl(config.cx_subject, config.xfmname, config.reference)
    else:  # manual — opens the interactive aligner (blocking)
        cortex.align.manual(config.cx_subject, config.xfmname, config.reference)

    n = mask_voxel_count(config.cx_subject, config.xfmname)
    logger.info(
        "Transform '%s' created for '%s'; cortical mask = %s voxels",
        config.xfmname, config.cx_subject, n,
    )

    return PycortexTransformResult(
        cx_subject=config.cx_subject,
        xfmname=config.xfmname,
        reference=config.reference,
        method=config.method,
        n_mask_voxels=n,
        filestore=filestore,
        created=True,
        elapsed_s=time.time() - start,
    )
