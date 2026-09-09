"""fmriprep as a pipeline node.

One ``container_app`` node: bind a BIDS root and a subject, choose a mode
and options, and the node runs fmriprep (docker / apptainer / bare) in its
own process group, streams its log, parses fmriprep's inner nipype
``[Node]`` lines so the recon-all / BOLD DAG shows live under this node,
and finally collects the derivatives into a ``PreprocManifest``.

The parameter schema is grouped (``group`` on each field) so the UI can
render collapsible sections: Mode, Anatomical, Functional, Fieldmaps,
Output, Denoising, Resources.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

from fmriflow.preproc.backends.fmriprep_params import (
    VALID_CIFTI_OUTPUT,
    VALID_CONTAINER_TYPES,
    VALID_IGNORE,
    VALID_MODES,
    VALID_SKULL_STRIP,
    FmriprepParams,
)
from fmriflow.preproc.container import container_prefix, guest_paths, runtime_available
from fmriflow.preproc.node_registry import preproc_node

logger = logging.getLogger(__name__)

_PARAM_FIELDS = {f.name for f in dataclasses.fields(FmriprepParams)}


def fmriprep_params(params: dict[str, Any]) -> FmriprepParams:
    """Node params -> ``FmriprepParams`` (unknown keys are ignored)."""
    return FmriprepParams.from_dict({k: v for k, v in params.items() if k in _PARAM_FIELDS})


@preproc_node("fmriprep", kind="container_app")
class FmriprepNode:
    """Run fmriprep on one subject and collect its derivatives."""

    name = "fmriprep"
    version = "0.2.0"
    description = "fmriprep (docker / apptainer / bare): anatomical + functional preprocessing."
    INNER_NIPYPE_LOG = True
    FINGERPRINT_INPUTS = ["bids_dir"]
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = "nipreps/fmriprep"

    INPUTS = {
        "bids_dir": {"kind": "dir", "required": True, "exists": True, "description": "BIDS root"},
        "subject": {"kind": "str", "required": True, "description": "participant label (no sub-)"},
        "output_dir": {"kind": "dir", "required": False, "description": "derivatives root (default: node dir/derivatives)"},
        "work_dir": {"kind": "dir", "required": False, "description": "fmriprep work dir (default: the node dir)"},
        "fs_subjects_dir": {"kind": "dir", "required": False, "description": "precomputed FreeSurfer subjects dir"},
    }
    OUTPUTS = {
        "derivatives_dir": {"kind": "dir", "description": "fmriprep output root"},
        "bold_preproc": {"kind": "nifti", "description": "preprocessed BOLD runs (list)"},
        "confounds": {"kind": "tsv", "description": "confounds TSVs (list)"},
        "fs_subjects_dir": {"kind": "dir", "description": "FreeSurfer subjects dir written by fmriprep"},
        "report_html": {"kind": "html", "description": "subject-level fmriprep report"},
        "manifest": {"kind": "json", "description": "preproc_manifest.json for this run"},
    }

    PARAM_SCHEMA: dict[str, Any] = {
        # ── Mode ──
        "mode": {"type": "str", "default": "full", "enum": list(VALID_MODES), "group": "Mode",
                 "description": "full | anat_only | func_only | func_precomputed_anat"},
        "container": {"type": "str", "default": "nipreps/fmriprep:24.1.1", "group": "Mode",
                      "description": "Image (docker tag, .sif path, docker:// URI) or empty for a bare install."},
        "container_type": {"type": "str", "default": "docker", "enum": list(VALID_CONTAINER_TYPES), "group": "Mode"},
        "skip_bids_validation": {"type": "bool", "default": False, "group": "Mode"},
        "task_id": {"type": "str", "default": "", "group": "Mode", "description": "Only this task."},
        # ── Anatomical ──
        "skull_strip": {"type": "str", "default": "auto", "enum": list(VALID_SKULL_STRIP), "group": "Anatomical"},
        "skull_strip_template": {"type": "str", "default": "", "group": "Anatomical"},
        "no_submm_recon": {"type": "bool", "default": False, "group": "Anatomical"},
        "fs_subjects_dir": {"type": "str", "default": "", "group": "Anatomical",
                            "description": "Reuse recon-all outputs from here (also an input port)."},
        # ── Functional ──
        "bold2t1w_init": {"type": "str", "default": "", "enum": ["", "register", "header"], "group": "Functional"},
        "bold2t1w_dof": {"type": "int", "default": None, "enum": [6, 9, 12], "group": "Functional"},
        "dummy_scans": {"type": "int", "default": None, "min": 0, "group": "Functional"},
        "ignore": {"type": "list[string]", "default": [], "enum": list(VALID_IGNORE), "group": "Functional"},
        # ── Fieldmaps ──
        "use_syn_sdc": {"type": "bool", "default": False, "group": "Fieldmaps"},
        "force_syn": {"type": "bool", "default": False, "group": "Fieldmaps"},
        "fmap_bspline": {"type": "bool", "default": False, "group": "Fieldmaps"},
        "fmap_no_demean": {"type": "bool", "default": False, "group": "Fieldmaps"},
        # ── Output ──
        "output_spaces": {"type": "list[string]", "default": ["T1w"], "group": "Output",
                          "description": "e.g. T1w, MNI152NLin2009cAsym:res-2, fsaverage5"},
        "cifti_output": {"type": "str", "default": "", "enum": ["", *VALID_CIFTI_OUTPUT], "group": "Output"},
        "me_output_echos": {"type": "bool", "default": False, "group": "Output"},
        # ── Denoising ──
        "use_aroma": {"type": "bool", "default": False, "group": "Denoising"},
        "aroma_melodic_dim": {"type": "int", "default": -200, "group": "Denoising"},
        "return_all_components": {"type": "bool", "default": False, "group": "Denoising"},
        # ── Resources ──
        "nthreads": {"type": "int", "default": None, "min": 1, "group": "Resources"},
        "omp_nthreads": {"type": "int", "default": None, "min": 1, "group": "Resources"},
        "mem_mb": {"type": "int", "default": None, "min": 1024, "group": "Resources"},
        "low_mem": {"type": "bool", "default": False, "group": "Resources"},
        "stop_on_first_crash": {"type": "bool", "default": False, "group": "Resources"},
        "fs_license_file": {"type": "str", "default": "", "group": "Resources",
                            "description": "FreeSurfer license; the full Docker image sets FS_LICENSE itself."},
        "extra_args": {"type": "list[string]", "default": [], "group": "Resources",
                       "description": "Raw extra fmriprep CLI arguments."},
    }

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _clean(params: dict[str, Any]) -> dict[str, Any]:
        """Drop empty-string / None values so FmriprepParams keeps its defaults."""
        return {k: v for k, v in params.items() if v not in ("", None)}

    @staticmethod
    def _dirs(inputs: dict[str, Any], out_dir: Path) -> tuple[str, str]:
        output_dir = str(inputs.get("output_dir") or out_dir / "derivatives")
        # Default the work dir to the node dir itself: fmriprep's inner nipype
        # node paths then map straight onto this node's work tree.
        work_dir = str(inputs.get("work_dir") or out_dir)
        return output_dir, work_dir

    # ── node contract ────────────────────────────────────────────

    def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        p = fmriprep_params(self._clean(params))
        errors = list(p.validate())
        if not inputs.get("bids_dir") or not Path(inputs["bids_dir"]).is_dir():
            errors.append(f"BIDS directory not found: {inputs.get('bids_dir')}")
        if not inputs.get("subject"):
            errors.append("subject is required")
        if not runtime_available(p.container, p.container_type):
            errors.append(
                f"cannot launch container {p.container!r} as {p.container_type}: runtime not available"
            )
        return errors

    def build_command(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> list[str]:
        p = fmriprep_params(self._clean(params))
        if not p.fs_subjects_dir and inputs.get("fs_subjects_dir"):
            p = dataclasses.replace(p, fs_subjects_dir=str(inputs["fs_subjects_dir"]))
        bids_dir = str(inputs["bids_dir"])
        subject = str(inputs["subject"])
        output_dir, work_dir = self._dirs(inputs, out_dir)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        extra_binds: list[tuple[str, str]] = []
        if p.container and p.fs_subjects_dir:
            extra_binds.append((p.fs_subjects_dir, "/fs_subjects"))
            p = dataclasses.replace(p, fs_subjects_dir="/fs_subjects")

        if p.container:
            cmd = container_prefix(
                p.container, p.container_type,
                bids_dir=bids_dir, output_dir=output_dir, work_dir=work_dir,
                extra_binds=extra_binds,
            )
        else:
            cmd = ["fmriprep"]
        g_bids, g_out, g_work = guest_paths(
            "bare" if not p.container else p.container_type,
            bids_dir=bids_dir, output_dir=output_dir, work_dir=work_dir,
        )
        cmd += [g_bids, g_out, "participant", "--participant-label", subject]
        if g_work:
            cmd += ["-w", g_work]
        cmd += p.to_command_args()
        return cmd

    def collect(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> dict[str, Any]:
        manifest = self.to_manifest(inputs, params, out_dir)
        output_dir, _ = self._dirs(inputs, out_dir)
        base = Path(output_dir)
        manifest_path = Path(out_dir) / "preproc_manifest.json"
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))

        outputs: dict[str, Any] = {
            "derivatives_dir": base,
            "bold_preproc": [base / r.output_file for r in manifest.runs],
            "confounds": [base / r.confounds_file for r in manifest.runs if r.confounds_file],
            "manifest": manifest_path,
        }
        fs_dir = base / "sourcedata" / "freesurfer"
        if not fs_dir.is_dir() and inputs.get("fs_subjects_dir"):
            fs_dir = Path(inputs["fs_subjects_dir"])
        if fs_dir.is_dir():
            outputs["fs_subjects_dir"] = fs_dir
        report = base / f"sub-{inputs['subject']}.html"
        if report.exists():
            outputs["report_html"] = report
        return outputs

    def to_manifest(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path):
        """Build the ``PreprocManifest`` from fmriprep's derivatives."""
        from fmriflow.preproc.backends.fmriprep import FmriprepBackend
        from fmriflow.preproc.manifest import PreprocConfig

        output_dir, work_dir = self._dirs(inputs, out_dir)
        p = fmriprep_params(self._clean(params))
        config = PreprocConfig(
            subject=str(inputs["subject"]),
            backend="fmriprep",
            output_dir=output_dir,
            bids_dir=str(inputs.get("bids_dir") or ""),
            work_dir=work_dir,
            task=p.task_id or None,
            backend_params=p.to_dict(),
        )
        return FmriprepBackend().collect(config)
