"""fmriprep as a pipeline node.

One ``container_app`` node: bind a BIDS root and a subject, choose a mode
and options, and the node runs fmriprep from PATH in its
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
        VALID_IGNORE,
    VALID_MODES,
    VALID_SKULL_STRIP,
    FmriprepParams,
)
from fmriflow.preproc.checkpoints import (
    Check,
    aseg_stats_metrics,
    brain_volume_metrics,
    surface_metrics,
    thickness_metrics,
    volume_intensity_metrics,
    wm_volume_metrics,
)
import shutil
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
    description = "fmriprep (bare, from PATH): anatomical + functional preprocessing."
    INNER_NIPYPE_LOG = True
    # Friendly names for the inner nipype nodes; every other UI capability
    # (report, structural QC, summary, checkpoints) derives from the ports/CHECKS.
    UI = {"label_map": "fmriprep"}
    FINGERPRINT_INPUTS = ["bids_dir"]
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = "nipreps/fmriprep"

    # Live checkpoints over the FreeSurfer chain, evaluated as recon-all writes
    # each file (the MP2RAGE normalisation collapse shows up at nu.mgz, ~20 min in).
    CHECKS = [
        Check(step="orig.mgz", artifact="{fs_subject_dir}/mri/orig.mgz", metrics=volume_intensity_metrics, thumbnail="volume"),
        Check(step="nu.mgz", artifact="{fs_subject_dir}/mri/nu.mgz", metrics=volume_intensity_metrics, thumbnail="volume"),
        Check(step="T1.mgz", artifact="{fs_subject_dir}/mri/T1.mgz", metrics=volume_intensity_metrics, thumbnail="volume"),
        Check(step="brainmask.mgz", artifact="{fs_subject_dir}/mri/brainmask.mgz", metrics=brain_volume_metrics, thumbnail="volume"),
        Check(step="wm.mgz", artifact="{fs_subject_dir}/mri/wm.mgz", metrics=wm_volume_metrics, thumbnail="volume"),
        Check(step="lh.white", artifact="{fs_subject_dir}/surf/lh.white", metrics=surface_metrics),
        Check(step="rh.white", artifact="{fs_subject_dir}/surf/rh.white", metrics=surface_metrics),
        Check(step="lh.thickness", artifact="{fs_subject_dir}/surf/lh.thickness", metrics=thickness_metrics),
        Check(step="rh.thickness", artifact="{fs_subject_dir}/surf/rh.thickness", metrics=thickness_metrics),
        Check(step="aseg.stats", artifact="{fs_subject_dir}/stats/aseg.stats", metrics=aseg_stats_metrics),
    ]

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
        "skip_bids_validation": {"type": "bool", "default": False, "group": "Mode"},
        "task_id": {"type": "str", "default": "", "group": "Mode", "description": "Only this task."},
        "sequence": {"type": "str", "default": "", "enum": ["", "mprage", "mp2rage"], "group": "Mode",
                     "description": "T1w sequence, selects sequence-specific checkpoint norms."},
        # ── Anatomical ──
        "skull_strip": {"type": "str", "default": "auto", "enum": list(VALID_SKULL_STRIP), "group": "Anatomical"},
        "skull_strip_template": {"type": "str", "default": "", "group": "Anatomical"},
        "no_submm_recon": {"type": "bool", "default": False, "group": "Anatomical"},
        "fs_subjects_dir": {"type": "dir", "default": "", "group": "Anatomical",
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
        "fs_license_file": {"type": "file", "default": "", "group": "Resources",
                            "description": "FreeSurfer license; the full Docker image sets FS_LICENSE itself."},
        "extra_args": {"type": "list[string]", "default": [], "group": "Resources",
                       "description": "Raw extra fmriprep CLI arguments."},
    }

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _clean(params: dict[str, Any]) -> dict[str, Any]:
        """Drop empty-string / None values so FmriprepParams keeps its defaults.

        fmriprep always runs bare (from PATH); any ``container`` /
        ``container_type`` left in an older saved pipeline is ignored.
        """
        out = {k: v for k, v in params.items() if v not in ("", None)}
        out.pop("container", None)
        out.pop("container_type", None)
        return out

    @staticmethod
    def _dirs(inputs: dict[str, Any], out_dir: Path) -> tuple[str, str]:
        output_dir = str(inputs.get("output_dir") or out_dir / "derivatives")
        # Default the work dir to the node dir itself: fmriprep's inner nipype
        # node paths then map straight onto this node's work tree.
        work_dir = str(inputs.get("work_dir") or out_dir)
        return output_dir, work_dir

    def checkpoint_context(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> dict[str, Any]:
        """Placeholders for ``CHECKS[].artifact`` templates."""
        output_dir, work_dir = self._dirs(inputs, out_dir)
        subject = str(inputs.get("subject") or "")
        label = subject if subject.startswith("sub-") else f"sub-{subject}"
        fs_root = Path(inputs["fs_subjects_dir"]) if inputs.get("fs_subjects_dir") else Path(output_dir) / "sourcedata" / "freesurfer"
        return {
            "node_dir": str(out_dir),
            "derivatives_dir": output_dir,
            "work_dir": work_dir,
            "subject": subject,
            "fs_subjects_dir": str(fs_root),
            "fs_subject_dir": str(fs_root / label),
            "sequence": str(params.get("sequence") or ""),
        }

    # ── node contract ────────────────────────────────────────────

    def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        p = fmriprep_params(self._clean(params))
        # The FreeSurfer subjects dir may arrive on the input port instead of
        # the param; build_command merges it the same way.
        if not p.fs_subjects_dir and inputs.get("fs_subjects_dir"):
            p = dataclasses.replace(p, fs_subjects_dir=str(inputs["fs_subjects_dir"]))
        errors = list(p.validate())
        if p.fs_subjects_dir and not Path(p.fs_subjects_dir).is_dir():
            errors.append(f"fs_subjects_dir not found: {p.fs_subjects_dir}")
        if not inputs.get("bids_dir") or not Path(inputs["bids_dir"]).is_dir():
            errors.append(f"BIDS directory not found: {inputs.get('bids_dir')}")
        if not inputs.get("subject"):
            errors.append("subject is required")
        if shutil.which("fmriprep") is None:
            errors.append(
                "fmriprep is not on PATH — preprocessing runs bare and needs the full "
                "fMRIflow image (or an environment with fmriprep installed)"
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

        cmd = ["fmriprep", bids_dir, output_dir, "participant", "--participant-label", subject]
        if work_dir:
            cmd += ["-w", work_dir]
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
