"""Conversion runner — orchestrates heudiconv execution, BIDS validation,
and manifest generation."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from denizenspipeline.convert.dicom_utils import extract_scanner_info
from denizenspipeline.convert.errors import ConvertError, HeudiconvError
from denizenspipeline.convert.heuristics import build_heuristic_ref, resolve_heuristic
from denizenspipeline.convert.manifest import (
    ConvertConfig,
    ConvertManifest,
    ConvertRunRecord,
    now_iso,
)
from denizenspipeline.convert.validation import run_bids_validator

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "convert_manifest.json"


def run_conversion(config: ConvertConfig) -> ConvertManifest:
    """Run a full DICOM-to-BIDS conversion.

    1. Resolve the heuristic (registry name or file path).
    2. Validate heudiconv is available.
    3. Run heudiconv.
    4. Build manifest from outputs.
    5. Optionally run BIDS validation.
    6. Write the manifest.

    Returns the manifest.
    """
    # Check heudiconv
    if not shutil.which("heudiconv"):
        raise ConvertError(
            "heudiconv not found. Install via: pip install heudiconv",
            subject=config.subject,
        )

    heuristic_path = resolve_heuristic(config.heuristic)

    cmd = [
        "heudiconv",
        "--files", config.source_dir,
        "-o", config.bids_dir,
        "-s", config.subject,
        "-f", str(heuristic_path),
        "--bids",
    ]
    if config.sessions:
        cmd.extend(["-ss", config.sessions[0]])
    if config.grouping:
        cmd.extend(["--grouping", config.grouping])
    if config.minmeta:
        cmd.append("--minmeta")
    if config.overwrite:
        cmd.append("--overwrite")

    logger.info("Running heudiconv: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True,
    )
    output_lines = []
    for line in proc.stdout:
        output_lines.append(line)
        logger.info("[heudiconv] %s", line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        raise HeudiconvError(
            f"heudiconv exited with code {proc.returncode}",
            subject=config.subject,
            returncode=proc.returncode,
            stderr="".join(output_lines),
        )

    # Build manifest from outputs
    manifest = collect_bids(config)

    # Optional BIDS validation
    if config.validate_bids:
        manifest = run_bids_validator(manifest)

    # Save manifest
    manifest_path = Path(config.bids_dir) / MANIFEST_FILENAME
    manifest.save(manifest_path)
    logger.info("Manifest written to %s", manifest_path)

    return manifest


def collect_bids(config: ConvertConfig) -> ConvertManifest:
    """Build a manifest from an existing BIDS dataset without re-converting.

    Useful when conversion was done externally (or by a previous run)
    and you just want to register the outputs with provenance.
    """
    bids_dir = Path(config.bids_dir)
    runs: list[ConvertRunRecord] = []

    for nii in sorted(bids_dir.rglob(f"sub-{config.subject}/**/*.nii.gz")):
        entities = _parse_bids_filename(nii.name)
        sidecar = nii.with_suffix("").with_suffix(".json")

        tr = None
        n_volumes = 0
        shape: list[int] = []

        try:
            import nibabel as nib
            img = nib.load(nii)
            shape = list(img.shape)
            n_volumes = shape[-1] if len(shape) == 4 else 1
        except ImportError:
            logger.debug("nibabel not available — skipping shape extraction")
        except Exception:
            logger.warning("Could not load %s", nii, exc_info=True)

        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text())
                tr = meta.get("RepetitionTime")
            except Exception:
                pass

        runs.append(ConvertRunRecord(
            run_name=entities.get("run", "01"),
            task=entities.get("task", ""),
            session=entities.get("ses", ""),
            source_series="",
            output_file=str(nii.relative_to(bids_dir)),
            sidecar_file=str(sidecar.relative_to(bids_dir)) if sidecar.exists() else "",
            n_volumes=n_volumes,
            modality=_infer_modality(nii.name),
            shape=shape,
            tr=tr,
            notes=None,
        ))

    heuristic_ref = None
    if config.heuristic:
        try:
            heuristic_ref = build_heuristic_ref(config.heuristic)
        except Exception:
            logger.debug("Could not build heuristic ref for '%s'", config.heuristic)

    return ConvertManifest(
        subject=config.subject,
        dataset=config.dataset_name or bids_dir.name,
        sessions=config.sessions or _detect_sessions(bids_dir, config.subject),
        runs=runs,
        heudiconv_version=_get_heudiconv_version(),
        heuristic=heuristic_ref,
        parameters={"grouping": config.grouping, "minmeta": config.minmeta},
        source_dir=config.source_dir,
        scanner=extract_scanner_info(config.source_dir) if config.source_dir else None,
        bids_dir=str(bids_dir),
        dataset_description=_read_dataset_description(bids_dir),
        bids_valid=None,
        bids_errors=[],
        bids_warnings=[],
        created=now_iso(),
        pipeline_version=None,
        checksum=None,
    )


def dry_run(config: ConvertConfig) -> str:
    """Preview what heudiconv would produce without actually converting.

    Returns the raw heudiconv output as a string.
    """
    if not shutil.which("heudiconv"):
        raise ConvertError(
            "heudiconv not found. Install via: pip install heudiconv",
            subject=config.subject,
        )

    heuristic_path = resolve_heuristic(config.heuristic)
    cmd = [
        "heudiconv",
        "--files", config.source_dir,
        "-s", config.subject,
        "-f", str(heuristic_path),
        "--command", "none",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


# ── Internal helpers ─────────────────────────────────────────────────────

_BIDS_ENTITY_RE = re.compile(r"([a-zA-Z]+)-([a-zA-Z0-9]+)")


def _parse_bids_filename(filename: str) -> dict[str, str]:
    """Extract BIDS entities from a filename.

    e.g. "sub-AN_ses-session01-reading_run-01_bold.nii.gz"
    → {"sub": "sub01", "ses": "session01", "task": "reading", "run": "01"}
    """
    return dict(_BIDS_ENTITY_RE.findall(filename))


def _infer_modality(filename: str) -> str:
    """Infer modality from a BIDS filename suffix."""
    name = filename.lower()
    if "_bold" in name:
        return "bold"
    if "_t1w" in name:
        return "T1w"
    if "_t2w" in name:
        return "T2w"
    if "_dwi" in name:
        return "dwi"
    if "_fmap" in name or "_phasediff" in name or "_magnitude" in name:
        return "fmap"
    if "_epi" in name:
        return "epi"
    return "unknown"


def _detect_sessions(bids_dir: Path, subject: str) -> list[str]:
    """Detect session labels from the BIDS directory structure."""
    sub_dir = bids_dir / f"sub-{subject}"
    if not sub_dir.is_dir():
        return []
    sessions = []
    for d in sorted(sub_dir.iterdir()):
        if d.is_dir() and d.name.startswith("ses-"):
            sessions.append(d.name.removeprefix("ses-"))
    return sessions


def _read_dataset_description(bids_dir: Path) -> dict | None:
    """Read dataset_description.json if it exists."""
    desc_file = bids_dir / "dataset_description.json"
    if desc_file.is_file():
        try:
            return json.loads(desc_file.read_text())
        except Exception:
            return None
    return None


def _get_heudiconv_version() -> str:
    """Get the installed heudiconv version."""
    try:
        result = subprocess.run(
            ["heudiconv", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        version = result.stdout.strip()
        if not version:
            version = result.stderr.strip()
        return version or "unknown"
    except Exception:
        return "unknown"
