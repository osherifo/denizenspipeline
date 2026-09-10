"""Regress confounds — OLS-regress nuisance signals out of a BOLD timeseries.

Reads a BIDS-derivatives style confounds TSV (one column per
nuisance regressor, one row per TR) and the BOLD NIfTI. Selects
the user-specified columns, fits a per-voxel linear model, writes
the residual NIfTI.

Purpose-built for the post-bootstrap regression step that
typically follows fmriprep — common confounds: 6 motion params,
their first temporal derivatives, framewise displacement, a few
cosine drift terms, aCompCor components.

Numpy-only — no sklearn dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.preproc.node_registry import preproc_node


# Six standard rigid-body motion parameters that fmriprep emits.
DEFAULT_COLUMNS = [
    "trans_x", "trans_y", "trans_z",
    "rot_x", "rot_y", "rot_z",
]


@preproc_node("regress_confounds")
class RegressConfoundsTransform:
    """Regress nuisance signals out of a BOLD timeseries via OLS.

    The intercept is always included implicitly (the confounds
    matrix gets a constant column prepended). If ``demean`` is True
    the voxel timeseries are zero-meaned before regression, which
    matches the standard fMRI convention.
    """

    name = "regress_confounds"
    version = "0.1.0"
    description = (
        "Regress nuisance confounds (motion, cosine drift, aCompCor, ...) "
        "out of the BOLD timeseries via per-voxel OLS. Reads a "
        "BIDS-derivatives TSV; writes a residual NIfTI."
    )

    INPUTS = {
        "in_file": {"kind": "nifti", "required": True, "description": "4D BOLD"},
        "confounds_file": {"kind": "tsv", "required": False,
                           "description": "confounds TSV (or set the confounds_path param)"},
    }
    OUTPUTS = {"out_file": {"kind": "nifti", "description": "residual BOLD"}}

    PARAM_SCHEMA: dict[str, Any] = {
        "confounds_path": {
            "type": "str",
            "default": "",
            "description": (
                "Path to the confounds TSV (BIDS-derivatives style); "
                "used when no confounds_file input is connected."
            ),
        },
        "columns": {
            "type": "list[str]",
            "default": DEFAULT_COLUMNS,
            "description": (
                "Column names to regress out. Defaults to the 6 "
                "rigid-body motion parameters."
            ),
        },
        "demean": {
            "type": "bool",
            "default": True,
            "description": (
                "Zero-mean each voxel before regression (standard "
                "fMRI convention)."
            ),
        },
    }

    REQUIRED_PYTHON: list[str] = []   # numpy + nibabel are project-level deps
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def run(
        self,
        inputs: dict[str, Any],
        out_dir: Path,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        import csv
        import nibabel as nib
        import numpy as np

        in_file = Path(inputs["in_file"])
        confounds_path = inputs.get("confounds_file") or params.get("confounds_path") or ""
        if not confounds_path:
            raise ValueError(
                "regress_confounds: connect a confounds_file input or set 'confounds_path'."
            )
        confounds_path = Path(confounds_path)
        if not confounds_path.is_file():
            raise FileNotFoundError(f"Confounds TSV not found: {confounds_path}")

        columns = list(params.get("columns") or DEFAULT_COLUMNS)
        demean = bool(params.get("demean", True))

        # Load BOLD.
        img = nib.load(str(in_file))
        data = img.get_fdata()
        if data.ndim != 4:
            raise ValueError(
                f"regress_confounds expects a 4D BOLD volume; got shape "
                f"{data.shape}"
            )
        n_trs = data.shape[3]

        # Load + select confounds.
        confounds_matrix = _load_confounds(confounds_path, columns, n_trs)

        # Build the design matrix: intercept + selected confounds.
        design = np.column_stack([np.ones(n_trs), confounds_matrix])  # (n_trs, n_regressors + 1)

        # Reshape to (n_trs, n_voxels) for matrix solve.
        spatial_shape = data.shape[:3]
        voxels = data.reshape(-1, n_trs).T  # (n_trs, n_voxels)

        if demean:
            voxels = voxels - voxels.mean(axis=0, keepdims=True)

        # OLS: betas = (X^T X)^-1 X^T y, then residuals = y - X betas.
        # np.linalg.lstsq handles this in a numerically-stable way.
        betas, *_ = np.linalg.lstsq(design, voxels, rcond=None)
        residuals = voxels - design @ betas

        # Back to (X, Y, Z, T).
        residuals_4d = residuals.T.reshape(*spatial_shape, n_trs)

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = (
            out_dir / f"{in_file.stem.replace('.nii', '')}_desc-regressed_bold.nii.gz"
        )
        nib.Nifti1Image(residuals_4d, img.affine, img.header).to_filename(str(out_path))
        return {"out_file": out_path}


def _load_confounds(
    path: Path,
    columns: list[str],
    expected_rows: int,
) -> "np.ndarray":   # noqa: F821 — numpy imported lazily in caller
    """Load specified columns from a TSV; return ``(n_rows, n_cols)``.

    Missing values (``n/a`` per BIDS convention) become 0.0 — the
    fmriprep convention is that early-volume confounds may be n/a
    (e.g. framewise-displacement at TR 0). Replacing with 0 is the
    standard handling.
    """
    import csv
    import numpy as np

    with open(path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        header = reader.fieldnames or []
        missing = [c for c in columns if c not in header]
        if missing:
            raise KeyError(
                f"Confounds TSV is missing columns: {missing}. "
                f"Available: {header}"
            )

        rows: list[list[float]] = []
        for row in reader:
            values: list[float] = []
            for col in columns:
                raw = row[col].strip()
                if raw in ("", "n/a", "nan", "NaN"):
                    values.append(0.0)
                else:
                    values.append(float(raw))
            rows.append(values)

    if len(rows) != expected_rows:
        raise ValueError(
            f"Confounds TSV has {len(rows)} rows but BOLD has "
            f"{expected_rows} TRs — they must match."
        )
    return np.asarray(rows, dtype=float)
