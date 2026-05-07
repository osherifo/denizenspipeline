"""Apply a binary mask to a volume — zero out voxels outside the mask."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.modules._decorators import nipype_node


@nipype_node("mask_apply")
class MaskApplyNode:
    """Multiply ``in_file`` voxels by a binary mask."""

    INPUTS = ["in_file", "mask_file"]
    OUTPUTS = ["out_file"]

    PARAM_SCHEMA: dict[str, Any] = {
        "mask_path": {
            "type": "str",
            "default": "",
            "description": (
                "Optional explicit mask path (used if no mask_file edge is "
                "connected)."
            ),
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

        in_file = Path(inputs["in_file"])
        mask_path = inputs.get("mask_file") or params.get("mask_path") or ""
        if not mask_path:
            raise ValueError(
                "mask_apply: requires either a mask_file edge or mask_path param"
            )
        mask_path = Path(mask_path)

        img = nib.load(str(in_file))
        mask = nib.load(str(mask_path)).get_fdata().astype(bool)
        data = img.get_fdata()
        if data.ndim == 4:
            out = data * mask[..., None]
        else:
            out = data * mask

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{in_file.stem.replace('.nii', '')}_masked.nii.gz"
        nib.Nifti1Image(out, img.affine, img.header).to_filename(str(out_path))
        return {"out_file": out_path}
