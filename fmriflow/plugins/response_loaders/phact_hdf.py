"""Reader for PHACT-style HDF response files.

File layout:
    {resp_dir}/subject{subject}_{modality}_fmri_data_{phase}.hdf

Each HDF file contains datasets named by story (e.g. story_01 ... story_10).
Training data is (n_trs, n_voxels); validation data may be
(n_reps, n_trs, n_voxels), in which case repetitions are averaged.

YAML config example:
    response:
      loader: local
      reader: phact_hdf
      path: /data/responses/
      subject: "01"
      modality: reading
      phases: [trn, val]

Required config keys:  subject, modality
Optional config keys:  phases (default: [trn, val]),
                       multirep (default: mean; how to collapse repetitions)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from fmriflow.plugins._decorators import response_reader


@response_reader("phact_hdf")
class PhactHdfReader:
    """Reads PHACT-style HDF response files."""

    name = "phact_hdf"

    PARAM_SCHEMA = {
        "subject": {"type": "string", "required": True, "description": "Subject ID"},
        "modality": {"type": "string", "default": "reading", "description": "Stimulus modality"},
        "phases": {"type": "list[string]", "default": ["trn", "val"], "description": "Data phases to load"},
        "multirep": {"type": "string", "default": "mean", "enum": ["mean", "first"], "description": "How to collapse repetitions"},
    }

    def read(
        self, resp_dir: Path, run_names: list[str] | None, config: dict,
    ) -> dict[str, np.ndarray]:
        import h5py

        subject = config["subject"]
        modality = config.get("modality", "reading")
        phases = config.get("phases", ["trn", "val"])
        multirep = config.get("multirep", "mean")

        responses: dict[str, np.ndarray] = {}

        for phase in phases:
            hdf_path = resp_dir / f"subject{subject}_{modality}_fmri_data_{phase}.hdf"
            if not hdf_path.exists():
                continue

            with h5py.File(hdf_path, "r") as h:
                names_to_load = run_names if run_names is not None else list(h.keys())
                for ds_name in names_to_load:
                    if ds_name not in h:
                        continue
                    arr = h[ds_name][:]

                    # Collapse repetitions for 3-D arrays (n_reps, n_trs, n_voxels)
                    if arr.ndim == 3:
                        if multirep == "mean":
                            arr = arr.mean(axis=0)
                        elif multirep == "first":
                            arr = arr[0]
                        else:
                            arr = arr.mean(axis=0)

                    responses[ds_name] = arr

        return responses

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if "subject" not in config:
            errors.append("phact_hdf reader requires 'subject' in config")
        return errors
