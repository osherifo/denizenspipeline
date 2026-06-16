"""Spatial Gaussian smoothing of a 3D/4D NIfTI volume."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.modules._decorators import nipype_node


@nipype_node("smooth")
class SmoothNode:
    """Apply isotropic Gaussian smoothing with a given FWHM (mm)."""

    # ── Transform Protocol metadata ────────────────────────────────
    # Same class also serves as a preproc-stack Transform via
    # fmriflow.preproc.builtin_transforms.smooth, which re-registers
    # it. These attributes satisfy the Transform Protocol and have
    # no effect on the nipype-node DAG builder.
    name = "smooth"
    version = "0.1.0"
    description = "Isotropic Gaussian spatial smoothing (scipy.ndimage)."
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    INPUTS = ["in_file"]
    OUTPUTS = ["out_file"]

    PARAM_SCHEMA: dict[str, Any] = {
        "fwhm": {
            "type": "float",
            "default": 5.0,
            "min": 0.0,
            "description": "Full-width at half-maximum of the Gaussian kernel (mm).",
        },
    }

    def run(
        self,
        inputs: dict[str, Path],
        out_dir: Path,
        params: dict[str, Any],
    ) -> dict[str, Path]:
        import nibabel as nib
        import numpy as np
        from scipy.ndimage import gaussian_filter

        fwhm = float(params.get("fwhm", 5.0))
        in_file = Path(inputs["in_file"])
        img = nib.load(str(in_file))
        data = img.get_fdata()
        # FWHM (mm) -> sigma (voxels) via voxel sizes from the affine.
        zooms = img.header.get_zooms()[:3]
        sigmas = [fwhm / (2.355 * z) for z in zooms]

        if data.ndim == 4:
            out = np.empty_like(data)
            for t in range(data.shape[3]):
                out[..., t] = gaussian_filter(data[..., t], sigma=sigmas)
        else:
            out = gaussian_filter(data, sigma=sigmas)

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{in_file.stem.replace('.nii', '')}_smooth-{fwhm:g}.nii.gz"
        nib.Nifti1Image(out, img.affine, img.header).to_filename(str(out_path))
        return {"out_file": out_path}
