"""Preprocessing runner — orchestrates backend execution and confound
regression, then writes the manifest."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.preproc.backends import get_backend
from fmriflow.preproc.confounds import regress_confounds
from fmriflow.preproc.errors import PreprocError
from fmriflow.preproc.manifest import (
    ConfoundsConfig,
    PreprocConfig,
    PreprocManifest,
    RunRecord,
    now_iso,
)

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "preproc_manifest.json"


def run_preprocessing(config: PreprocConfig) -> PreprocManifest:
    """Run a full preprocessing pipeline.

    1. Validate the backend configuration.
    2. Invoke the backend (which runs the actual preprocessing tool).
    3. Optionally apply confound regression.
    4. Write the manifest to ``{output_dir}/sub-{subject}/preproc_manifest.json``.

    Returns the manifest.
    """
    backend = get_backend(config.backend)

    # Validate
    errors = backend.validate(config)
    if errors:
        raise PreprocError(
            "Backend validation failed:\n  " + "\n  ".join(errors),
            backend=config.backend,
            subject=config.subject,
        )

    # Run
    logger.info(
        "Starting preprocessing: backend=%s, subject=%s",
        config.backend, config.subject,
    )
    manifest = backend.run(config)

    # Optional confound regression
    if config.confounds:
        manifest = _apply_confounds(manifest, config.confounds)

    # Save manifest
    manifest_path = _manifest_path(config)
    manifest.save(manifest_path)
    logger.info("Manifest written to %s", manifest_path)

    return manifest


def collect_outputs(config: PreprocConfig) -> PreprocManifest:
    """Build a manifest from existing preprocessing outputs without re-running.

    Useful when preprocessing was done externally.
    """
    backend = get_backend(config.backend)
    manifest = backend.collect(config)

    # Optional confound regression
    if config.confounds:
        manifest = _apply_confounds(manifest, config.confounds)

    # Save manifest
    manifest_path = _manifest_path(config)
    manifest.save(manifest_path)
    logger.info("Manifest written to %s", manifest_path)

    return manifest


def _manifest_path(config: PreprocConfig) -> Path:
    """Determine where to write the manifest."""
    return Path(config.output_dir) / f"sub-{config.subject}" / MANIFEST_FILENAME


def _apply_confounds(
    manifest: PreprocManifest,
    confounds_cfg: ConfoundsConfig,
) -> PreprocManifest:
    """Apply confound regression to all runs and update the manifest."""
    output_dir = Path(manifest.output_dir)
    confounds_list = []
    updated_runs = []

    for run in manifest.runs:
        if not run.confounds_file:
            logger.warning(
                "Run '%s' has no confounds file — skipping regression.",
                run.run_name,
            )
            updated_runs.append(run)
            continue

        bold_path = output_dir / run.output_file
        confounds_path = output_dir / run.confounds_file

        if not bold_path.exists():
            logger.warning("BOLD file not found: %s", bold_path)
            updated_runs.append(run)
            continue

        # Load BOLD
        bold_data = _load_bold(bold_path, manifest.output_format)
        if bold_data is None:
            updated_runs.append(run)
            continue

        # Regress
        cleaned = regress_confounds(bold_data, confounds_path, confounds_cfg)

        # Write cleaned data back
        _save_bold(bold_path, cleaned, manifest.output_format)

        # Update run record with new n_trs (may change if scrubbing)
        updated_runs.append(RunRecord(
            run_name=run.run_name,
            source_file=run.source_file,
            output_file=run.output_file,
            n_trs=cleaned.shape[0],
            n_voxels=run.n_voxels,
            shape=list(cleaned.shape),
            confounds_file=run.confounds_file,
            qc=run.qc,
        ))

    # Build applied confounds list
    if confounds_cfg.strategy == "custom":
        confounds_list = confounds_cfg.columns or []
    else:
        confounds_list = [confounds_cfg.strategy]

    # Return updated manifest
    return PreprocManifest(
        subject=manifest.subject,
        dataset=manifest.dataset,
        sessions=manifest.sessions,
        runs=updated_runs,
        backend=manifest.backend,
        backend_version=manifest.backend_version,
        parameters=manifest.parameters,
        space=manifest.space,
        resolution=manifest.resolution,
        confounds_applied=confounds_list,
        additional_steps=manifest.additional_steps,
        output_dir=manifest.output_dir,
        output_format=manifest.output_format,
        file_pattern=manifest.file_pattern,
        created=now_iso(),
        pipeline_version=manifest.pipeline_version,
        checksum=None,
    )


def _load_bold(path: Path, fmt: str) -> np.ndarray | None:
    """Load BOLD data as (n_trs, n_voxels)."""
    try:
        if fmt == "nifti":
            import nibabel as nib
            img = nib.load(path)
            data = img.get_fdata()
            if data.ndim == 4:
                # (x, y, z, t) → (t, x*y*z)
                t = data.shape[-1]
                return data.reshape(-1, t).T
            return data
        elif fmt == "hdf5":
            import h5py
            with h5py.File(path, "r") as f:
                return f["data"][:]
        elif fmt == "npz":
            return np.load(path)["data"]
    except Exception:
        logger.warning("Could not load BOLD data from %s", path, exc_info=True)
    return None


def _save_bold(path: Path, data: np.ndarray, fmt: str) -> None:
    """Save cleaned BOLD data back to the same format."""
    try:
        if fmt == "nifti":
            import nibabel as nib
            # Load original to preserve affine/header
            orig = nib.load(path)
            if orig.ndim == 4:
                # (t, voxels) → (x, y, z, t)
                orig_shape = orig.shape[:3]
                vol = data.T.reshape(*orig_shape, -1)
                new_img = nib.Nifti1Image(vol, orig.affine, orig.header)
            else:
                new_img = nib.Nifti1Image(data, orig.affine, orig.header)
            nib.save(new_img, path)
        elif fmt == "hdf5":
            import h5py
            with h5py.File(path, "a") as f:
                if "data" in f:
                    del f["data"]
                f.create_dataset("data", data=data)
        elif fmt == "npz":
            np.savez(path, data=data)
    except Exception:
        logger.warning("Could not save cleaned BOLD to %s", path, exc_info=True)
