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
    bold_integrity_metrics,
    brain_volume_metrics,
    compcor_components_metrics,
    confounds_motion_metrics,
    fieldmap_stats_metrics,
    phasediff_delta_te_metrics,
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
        # ── functional outputs, one record per run (glob templates) ──
        # General integrity of the preprocessed BOLD.
        Check(step="bold_nan_inf", artifact="{derivatives_dir}/sub-{subject}/**/func/*_desc-preproc_bold.nii.gz", metrics=bold_integrity_metrics),
        Check(step="bold_spikes", artifact="{derivatives_dir}/sub-{subject}/**/func/*_desc-preproc_bold.nii.gz", metrics=bold_integrity_metrics),
        # Head-motion correction, read from the confounds fmriprep writes.
        Check(step="hmc_framewise_displacement", artifact="{derivatives_dir}/sub-{subject}/**/func/*_desc-confounds_timeseries.tsv", metrics=confounds_motion_metrics),
        Check(step="hmc_rigid_body", artifact="{derivatives_dir}/sub-{subject}/**/func/*_desc-confounds_timeseries.tsv", metrics=confounds_motion_metrics),
        # Fieldmap unwarping: only fires when the dataset has fieldmaps.
        Check(step="sdc_fieldmap_range", artifact="{derivatives_dir}/sub-{subject}/**/fmap/*_desc-preproc_fieldmap.nii.gz", metrics=fieldmap_stats_metrics),
        Check(step="sdc_delta_te", artifact="{bids_dir}/sub-{subject}/**/fmap/*_phasediff.json", metrics=phasediff_delta_te_metrics),
        # The per-run reference volume.
        Check(step="boldref_single_volume", artifact="{derivatives_dir}/sub-{subject}/**/func/*_desc-coreg_boldref.nii.gz", metrics=bold_integrity_metrics),
        Check(step="boldref_integrity", artifact="{derivatives_dir}/sub-{subject}/**/func/*_desc-coreg_boldref.nii.gz", metrics=bold_integrity_metrics),
        # CompCor regressors.
        Check(step="compcor_components_valid", artifact="{derivatives_dir}/sub-{subject}/**/func/*_desc-confounds_timeseries.tsv", metrics=compcor_components_metrics),
        Check(step="compcor_variance_explained", artifact="{derivatives_dir}/sub-{subject}/**/func/*_desc-confounds_timeseries.tsv", metrics=compcor_components_metrics),
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
                            "description": "Reuse recon-all outputs from here (also an input port). The subject is "
                                           "copied into the run's work dir first: fmriprep completes older "
                                           "reconstructions in place, and that must not touch the original."},
        "fs_subject": {"type": "str", "default": "", "group": "Anatomical",
                       "description": "Name of the precomputed subject inside fs_subjects_dir when it is not "
                                      "sub-<label> (e.g. a pycortex-style name)."},
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
        for k in ("container", "container_type", "fs_subject"):
            out.pop(k, None)
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
        staged = self._staged_fs_dir(work_dir)
        if inputs.get("fs_subjects_dir") or params.get("fs_subjects_dir"):
            fs_root = staged if staged.is_dir() else Path(str(params.get("fs_subjects_dir") or inputs["fs_subjects_dir"]))
        else:
            fs_root = Path(output_dir) / "sourcedata" / "freesurfer"
        return {
            "node_dir": str(out_dir),
            "derivatives_dir": output_dir,
            "work_dir": work_dir,
            "bids_dir": str(inputs.get("bids_dir") or ""),
            "subject": subject[4:] if subject.startswith("sub-") else subject,
            "fs_subjects_dir": str(fs_root),
            "fs_subject_dir": str(fs_root / label),
            "sequence": str(params.get("sequence") or ""),
        }

    # Modes that run (or reuse) the anatomical workflow vs. functional-only ones.
    ANAT_MODES = ("full", "anat_only")
    FUNC_MODES = ("full", "func_only", "func_precomputed_anat")
    # The FreeSurfer-chain steps; everything else in CHECKS is functional.
    FS_STEPS = ("orig.mgz", "nu.mgz", "T1.mgz", "brainmask.mgz", "wm.mgz", "lh.white", "rh.white", "lh.thickness", "rh.thickness", "aseg.stats")

    def ui_for_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """A functional-only run has no structural QC of its own: the FreeSurfer
        directory it reads was made by (and is reviewed on) the anatomical run."""
        mode = str(params.get("mode") or "full")
        return {} if mode in self.ANAT_MODES else {"structural_qc": None}

    def checks_for_params(self, params: dict[str, Any], checks: list[Check]) -> list[Check]:
        """Only the checks that this mode can produce: FreeSurfer steps in
        anatomical modes, functional-output steps in functional modes."""
        mode = str(params.get("mode") or "full")
        keep_fs = mode in self.ANAT_MODES
        keep_func = mode in self.FUNC_MODES
        return [c for c in checks if (keep_fs if c.step in self.FS_STEPS else keep_func)]

    # ── node contract ────────────────────────────────────────────

    # ── precomputed FreeSurfer: reuse on a copy ──────────────────

    FS_REQUIRED = ("surf/lh.white", "surf/rh.white", "mri/aseg.mgz", "mri/T1.mgz")

    @staticmethod
    def _label(subject: str) -> str:
        return subject if subject.startswith("sub-") else f"sub-{subject}"

    def _fs_source(self, inputs: dict[str, Any], params: dict[str, Any]) -> tuple[Path | None, Path | None, str | None]:
        """(subjects dir, the precomputed subject's dir, error) for a reuse run."""
        root = str(params.get("fs_subjects_dir") or inputs.get("fs_subjects_dir") or "")
        if not root:
            return None, None, None
        root_p = Path(root)
        if not root_p.is_dir():
            return root_p, None, f"fs_subjects_dir not found: {root}"
        label = self._label(str(inputs.get("subject") or ""))
        name = str(params.get("fs_subject") or "").strip() or label
        cand = root_p / name
        if not cand.is_dir():
            present = sorted(d.name for d in root_p.iterdir() if d.is_dir() and d.name != "fsaverage")
            return root_p, None, (f"no precomputed FreeSurfer subject {name!r} in {root} (found: {', '.join(present) or 'nothing'}); "
                                  f"set fs_subject to the right name — without it fmriprep would silently run recon-all from scratch")
        missing = [f for f in self.FS_REQUIRED if not (cand / f).exists()]
        if missing:
            return root_p, cand, f"precomputed subject {cand} is incomplete: missing {', '.join(missing)}"
        return root_p, cand, None

    @staticmethod
    def _staged_fs_dir(work_dir: str) -> Path:
        return Path(work_dir) / "fs_subjects"

    def _stage_fs(self, inputs: dict[str, Any], params: dict[str, Any], work_dir: str) -> str | None:
        """Copy the precomputed subject into ``<work_dir>/fs_subjects/sub-<label>`` and
        link ``fsaverage`` beside it; return that subjects dir.

        fmriprep "completes" any reconstruction it is handed — older FreeSurfer
        versions get missing volumes, transforms and surface measures written
        into the subject directory — so it must never be pointed at the
        original. The copy is skipped when a complete one is already staged.
        """
        root, src, err = self._fs_source(inputs, params)
        if err or src is None or root is None:
            return None
        staged_root = self._staged_fs_dir(work_dir)
        label = self._label(str(inputs.get("subject") or ""))
        dst = staged_root / label
        staged_root.mkdir(parents=True, exist_ok=True)
        marker = dst / ".fmriflow_staged_from"
        if not (dst.is_dir() and marker.is_file() and marker.read_text().strip() == str(src.resolve())):
            if dst.exists() or dst.is_symlink():
                shutil.rmtree(dst) if dst.is_dir() and not dst.is_symlink() else dst.unlink()
            logger.info("staging precomputed FreeSurfer subject %s -> %s", src, dst)
            shutil.copytree(src, dst, symlinks=True)
            for stale in ("IsRunning.lh+rh", "IsRunning.lh", "IsRunning.rh"):
                (dst / "scripts" / stale).unlink(missing_ok=True)
            marker.write_text(str(src.resolve()))
        fsavg = staged_root / "fsaverage"
        if not fsavg.exists() and (root / "fsaverage").is_dir():
            fsavg.symlink_to((root / "fsaverage").resolve())
        return str(staged_root)

    def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        p = fmriprep_params(self._clean(params))
        # The FreeSurfer subjects dir may arrive on the input port instead of
        # the param; build_command merges it the same way.
        if not p.fs_subjects_dir and inputs.get("fs_subjects_dir"):
            p = dataclasses.replace(p, fs_subjects_dir=str(inputs["fs_subjects_dir"]))
        errors = list(p.validate())
        if p.fs_subjects_dir:
            _, _, err = self._fs_source(inputs, params)
            if err:
                errors.append(err)
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
        if p.fs_subjects_dir:
            staged = self._stage_fs(inputs, params, work_dir)
            if staged:
                p = dataclasses.replace(p, fs_subjects_dir=staged)

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
        if not fs_dir.is_dir():
            _, work_dir = self._dirs(inputs, out_dir)
            staged = self._staged_fs_dir(work_dir)
            if staged.is_dir():
                fs_dir = staged                       # the copy fmriprep actually used
            elif inputs.get("fs_subjects_dir") or params.get("fs_subjects_dir"):
                fs_dir = Path(str(params.get("fs_subjects_dir") or inputs["fs_subjects_dir"]))
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
