"""PreprocResponseLoader — loads fMRI responses from a PreprocManifest.

This is how the analysis pipeline consumes preprocessing outputs: through
the existing ResponseLoader plugin interface.  No changes to the orchestrator.

Config usage:

    response:
      loader: preproc
      manifest: /data/derivatives/fmriprep/sub-AN/preproc_manifest.json
      mask_type: thick
      confounds:          # optional — apply confound regression at load time
        strategy: motion_24
        high_pass: 0.01
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.plugins._decorators import response_loader
from fmriflow.plugins.response_loaders.local import (
    LocalResponseLoader,
    _NO_MASK,
)

logger = logging.getLogger(__name__)


@response_loader("preproc")
class PreprocResponseLoader:
    """Loads responses from a preprocessing manifest.

    Reads the PreprocManifest, validates it against the analysis config,
    and loads the preprocessed arrays.  Optionally applies confound
    regression at load time.
    """

    name = "preproc"

    PARAM_SCHEMA = {
        "manifest": {
            "type": "path",
            "required": True,
            "description": "Path to preproc_manifest.json",
        },
        "mask_type": {
            "type": "string",
            "default": "thick",
            "description": "Pycortex cortical mask type",
        },
        "confounds": {
            "type": "dict",
            "description": "Confound regression config (strategy, high_pass, etc.)",
        },
        "run_map": {
            "type": "dict",
            "description": "Remap manifest run names to pipeline run names",
        },
    }

    def load(self, config: dict) -> ResponseData:
        from fmriflow.preproc.manifest import PreprocManifest, ConfoundsConfig
        from fmriflow.preproc.validation import validate_manifest

        resp_cfg = config.get("response", {})
        sub_cfg = config.get("subject_config", {})

        manifest_path = Path(resp_cfg["manifest"])
        manifest = PreprocManifest.from_json(manifest_path)

        # Validate manifest against analysis config
        errors = validate_manifest(manifest, config)
        warnings = [e for e in errors if e.startswith("Warning:")]
        hard_errors = [e for e in errors if not e.startswith("Warning:")]

        if hard_errors:
            raise RuntimeError(
                "Preprocessing manifest validation failed:\n  "
                + "\n  ".join(hard_errors)
            )
        for w in warnings:
            logger.warning(w)

        # Load confound config
        confounds_dict = resp_cfg.get("confounds")
        confounds_cfg = ConfoundsConfig(**confounds_dict) if confounds_dict else None

        # Load arrays
        output_dir = Path(manifest.output_dir)
        responses: dict[str, np.ndarray] = {}

        for run in manifest.runs:
            output_path = output_dir / run.output_file
            arr = self._load_array(output_path, manifest.output_format)

            if arr is None:
                logger.error("Could not load %s", output_path)
                continue

            # Optional confound regression at load time
            if confounds_cfg and run.confounds_file:
                from fmriflow.preproc.confounds import regress_confounds
                confounds_path = output_dir / run.confounds_file
                arr = regress_confounds(arr, confounds_path, confounds_cfg)

            responses[run.run_name] = arr
            logger.info(
                "Loaded %s: shape=%s (%d TRs)",
                run.run_name, arr.shape, arr.shape[0],
            )

        # Apply run_map
        run_map = resp_cfg.get("run_map", {})
        if run_map:
            responses = {run_map.get(k, k): v for k, v in responses.items()}

        surface = sub_cfg.get("surface", "unknown")
        transform = sub_cfg.get("transform", "unknown")

        # Apply cortical mask if volumetric
        is_volumetric = any(arr.ndim > 2 for arr in responses.values())

        if is_volumetric:
            responses, mask = LocalResponseLoader._apply_mask(
                responses,
                surface,
                transform,
                resp_cfg.get("mask_type", "thick"),
            )
        else:
            if responses:
                logger.info(
                    "Response data is 2-D (pre-masked), skipping cortical mask"
                )
            mask = _NO_MASK

        return ResponseData(
            responses=responses,
            mask=mask,
            surface=surface,
            transform=transform,
            metadata={
                "preproc_backend": manifest.backend,
                "preproc_version": manifest.backend_version,
                "preproc_space": manifest.space,
                "confounds_applied": manifest.confounds_applied,
                "manifest_path": str(manifest_path),
            },
        )

    def _load_array(
        self, path: Path, fmt: str,
    ) -> np.ndarray | None:
        """Load a preprocessed array as (n_trs, n_voxels)."""
        try:
            if fmt == "nifti":
                import nibabel as nib
                img = nib.load(path)
                data = img.get_fdata()
                if data.ndim == 4:
                    # (x, y, z, t) → keep as 4D for masking
                    return data
                return data
            elif fmt == "hdf5":
                import h5py
                with h5py.File(path, "r") as f:
                    return f["data"][:]
            elif fmt == "npz":
                return np.load(path)["data"]
        except Exception:
            logger.error("Failed to load %s", path, exc_info=True)
        return None

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        resp_cfg = config.get("response", {})

        if "manifest" not in resp_cfg:
            errors.append(
                "preproc loader requires response.manifest "
                "(path to preproc_manifest.json)"
            )
        else:
            manifest_path = Path(resp_cfg["manifest"])
            if not manifest_path.exists():
                errors.append(f"Manifest not found: {manifest_path}")
            else:
                try:
                    from fmriflow.preproc.manifest import PreprocManifest
                    from fmriflow.preproc.validation import validate_manifest
                    manifest = PreprocManifest.from_json(manifest_path)
                    errors.extend(validate_manifest(manifest, config))
                except Exception as e:
                    errors.append(f"Cannot read manifest: {e}")

        return errors
