"""Manifest validation and optional BIDS validator integration."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from denizenspipeline.convert.manifest import ConvertManifest

logger = logging.getLogger(__name__)


def validate_manifest(manifest: ConvertManifest,
                      config: dict | None = None) -> list[str]:
    """Check that a convert manifest is internally consistent.

    Returns a list of error/warning strings (empty = valid).
    """
    errors: list[str] = []
    bids_dir = Path(manifest.bids_dir)

    # Check output files exist
    for run in manifest.runs:
        output_path = bids_dir / run.output_file
        if not output_path.exists():
            errors.append(f"Output file not found: {output_path}")
        sidecar_path = bids_dir / run.sidecar_file
        if run.sidecar_file and not sidecar_path.exists():
            errors.append(f"Sidecar file not found: {sidecar_path}")

    # Check volume counts match actual files
    for run in manifest.runs:
        output_path = bids_dir / run.output_file
        if output_path.exists() and run.shape:
            try:
                import nibabel as nib
                img = nib.load(output_path)
                actual_shape = list(img.shape)
                if actual_shape != run.shape:
                    errors.append(
                        f"Shape mismatch for {run.output_file}: "
                        f"manifest says {run.shape}, file is {actual_shape}"
                    )
            except ImportError:
                pass  # nibabel not available, skip shape check
            except Exception as e:
                errors.append(f"Cannot load {run.output_file}: {e}")

    # Check TR consistency from sidecars
    for run in manifest.runs:
        if run.tr is not None and run.sidecar_file:
            sidecar_path = bids_dir / run.sidecar_file
            if sidecar_path.exists():
                try:
                    meta = json.loads(sidecar_path.read_text())
                    sidecar_tr = meta.get("RepetitionTime")
                    if sidecar_tr is not None and abs(sidecar_tr - run.tr) > 0.001:
                        errors.append(
                            f"TR mismatch for {run.output_file}: "
                            f"manifest says {run.tr}s, sidecar says {sidecar_tr}s"
                        )
                except Exception:
                    pass

    # If an analysis config was provided, check compatibility
    if config:
        errors.extend(_validate_against_config(manifest, config))

    return errors


def run_bids_validator(manifest: ConvertManifest) -> ConvertManifest:
    """Run the BIDS validator on the BIDS dataset and return an updated
    manifest with validation results.

    If the BIDS validator is not installed, returns the manifest unchanged
    with ``bids_valid=None``.
    """
    if not shutil.which("bids-validator"):
        logger.info("bids-validator not found — skipping validation")
        return manifest

    bids_dir = manifest.bids_dir
    try:
        result = subprocess.run(
            ["bids-validator", bids_dir, "--json"],
            capture_output=True, text=True, timeout=120,
        )
        output = json.loads(result.stdout) if result.stdout.strip() else {}
        issues = output.get("issues", {})

        bids_errors = [
            e.get("reason", str(e))
            for e in issues.get("errors", [])
        ]
        bids_warnings = [
            w.get("reason", str(w))
            for w in issues.get("warnings", [])
        ]
        bids_valid = len(bids_errors) == 0

        if bids_valid:
            logger.info("BIDS validation passed")
        else:
            logger.warning("BIDS validation found %d errors", len(bids_errors))

        # Return updated manifest (frozen, so rebuild)
        return ConvertManifest(
            subject=manifest.subject,
            dataset=manifest.dataset,
            sessions=manifest.sessions,
            runs=manifest.runs,
            heudiconv_version=manifest.heudiconv_version,
            heuristic=manifest.heuristic,
            parameters=manifest.parameters,
            source_dir=manifest.source_dir,
            scanner=manifest.scanner,
            bids_dir=manifest.bids_dir,
            dataset_description=manifest.dataset_description,
            bids_valid=bids_valid,
            bids_errors=bids_errors,
            bids_warnings=bids_warnings,
            created=manifest.created,
            pipeline_version=manifest.pipeline_version,
            checksum=manifest.checksum,
        )

    except subprocess.TimeoutExpired:
        logger.warning("BIDS validator timed out")
        return manifest
    except Exception:
        logger.warning("BIDS validator failed", exc_info=True)
        return manifest


def _validate_against_config(manifest: ConvertManifest,
                             config: dict) -> list[str]:
    """Check manifest compatibility with an analysis or preproc config."""
    errors: list[str] = []

    # Check subject match
    config_subject = config.get("subject")
    if config_subject and config_subject != manifest.subject:
        errors.append(
            f"Subject mismatch: manifest has '{manifest.subject}', "
            f"config has '{config_subject}'"
        )

    return errors
