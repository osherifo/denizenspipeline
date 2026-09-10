"""Reference minimal nipype preprocessing: MCFLIRT -> BET -> FLIRT (BBR) -> ANTs SyN.

A ``composite`` node whose ``build()`` returns a real nipype ``Workflow``.
It exists as the copyable example of a hand-written nipype pipeline
inside the graph: motion-correct the BOLD, skull-strip the T1w, register
BOLD to T1w with boundary-based registration, and warp the T1w to MNI
with ANTs SyN. Needs FSL and ANTs on the host (or in the image).

Ports follow the composite convention: fields of ``inputnode`` are the
input ports, fields of ``outputnode`` the output ports.
"""

from __future__ import annotations

from typing import Any

from fmriflow.preproc.node_registry import preproc_node


@preproc_node("reference_fsl_ants", kind="composite")
class ReferenceFslAntsWorkflow:
    """MCFLIRT + BET + FLIRT BBR + ANTs SyN, as one nipype sub-workflow."""

    name = "reference_fsl_ants"
    version = "0.1.0"
    description = "Reference nipype pipeline: MCFLIRT, BET, FLIRT (BBR) to T1w, ANTs SyN to MNI."
    REQUIRED_PYTHON: list[str] = ["nipype>=1.8"]
    REQUIRED_TOOLS: list[str] = ["mcflirt", "bet", "flirt", "antsRegistration"]
    REQUIRED_ENV: list[str] = ["FSLDIR"]
    CONTAINER: str | None = None

    INPUTS = {
        "bold": {"kind": "nifti", "required": True, "description": "raw BOLD run"},
        "t1w": {"kind": "nifti", "required": True, "description": "raw T1w"},
        "mni_template": {"kind": "nifti", "required": False, "description": "MNI template (default: FSL MNI152 2mm)"},
    }
    OUTPUTS = {
        "bold_mc": {"kind": "nifti", "description": "motion-corrected BOLD"},
        "motion_params": {"kind": "file", "description": "MCFLIRT .par"},
        "t1w_brain": {"kind": "nifti", "description": "skull-stripped T1w"},
        "brain_mask": {"kind": "nifti", "description": "T1w brain mask"},
        "bold2t1w_mat": {"kind": "file", "description": "FLIRT BBR matrix"},
        "t1w2mni_warp": {"kind": "file", "description": "ANTs composite transform (T1w -> MNI)"},
        "t1w_mni": {"kind": "nifti", "description": "T1w warped to MNI"},
    }
    PARAM_SCHEMA: dict[str, Any] = {
        "bet_frac": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "description": "BET fractional intensity."},
        "mc_ref": {"type": "str", "default": "mean", "enum": ["mean", "first", "middle"], "description": "MCFLIRT reference."},
        "bbr_dof": {"type": "int", "default": 6, "enum": [6, 9, 12]},
        "syn_quick": {"type": "bool", "default": True, "description": "Fewer SyN iterations (faster, coarser)."},
    }

    def validate(self, config: Any) -> list[str]:
        return []

    def build(self, config: Any) -> Any:
        import os

        from nipype import Node, Workflow
        from nipype.interfaces import ants, fsl
        from nipype.interfaces.utility import IdentityInterface

        params = dict(getattr(config, "params", {}) or {})
        bet_frac = float(params.get("bet_frac", 0.5))
        mc_ref = str(params.get("mc_ref", "mean"))
        bbr_dof = int(params.get("bbr_dof", 6))
        quick = bool(params.get("syn_quick", True))

        wf = Workflow(name="reference_fsl_ants")
        inputnode = Node(IdentityInterface(fields=["bold", "t1w", "mni_template"]), name="inputnode")
        outputnode = Node(
            IdentityInterface(fields=list(self.OUTPUTS)), name="outputnode",
        )
        fsldir = os.environ.get("FSLDIR", "")
        default_mni = os.path.join(fsldir, "data", "standard", "MNI152_T1_2mm_brain.nii.gz") if fsldir else ""
        if default_mni:
            inputnode.inputs.mni_template = default_mni

        mcflirt = Node(fsl.MCFLIRT(save_plots=True, output_type="NIFTI_GZ"), name="mcflirt")
        if mc_ref == "mean":
            mcflirt.inputs.mean_vol = True
        elif mc_ref == "first":
            mcflirt.inputs.ref_vol = 0
        meanbold = Node(fsl.MeanImage(output_type="NIFTI_GZ"), name="mean_bold")
        bet = Node(fsl.BET(frac=bet_frac, mask=True, output_type="NIFTI_GZ"), name="bet")
        fast = Node(fsl.FAST(no_pve=True, segments=True, output_type="NIFTI_GZ"), name="fast")
        wm_mask = Node(fsl.ImageMaths(op_string="-thr 0.5 -bin", output_type="NIFTI_GZ"), name="wm_mask")
        flirt_init = Node(fsl.FLIRT(dof=bbr_dof, output_type="NIFTI_GZ"), name="flirt_init")
        flirt_bbr = Node(fsl.FLIRT(cost="bbr", dof=bbr_dof, output_type="NIFTI_GZ"), name="flirt_bbr")
        bbr_schedule = os.path.join(fsldir, "etc", "flirtsch", "bbr.sch") if fsldir else ""
        if bbr_schedule and os.path.exists(bbr_schedule):
            flirt_bbr.inputs.schedule = bbr_schedule
        syn = Node(ants.Registration(
            transforms=["Rigid", "Affine", "SyN"],
            transform_parameters=[(0.1,), (0.1,), (0.1, 3.0, 0.0)],
            number_of_iterations=[[100, 50], [100, 50], [50, 20]] if quick else [[1000, 500, 250, 100]] * 2 + [[100, 70, 50, 20]],
            metric=["MI", "MI", "CC"],
            metric_weight=[1.0, 1.0, 1.0],
            radius_or_number_of_bins=[32, 32, 4],
            sampling_strategy=["Regular", "Regular", None],
            sampling_percentage=[0.25, 0.25, None],
            convergence_threshold=[1e-6] * 3,
            convergence_window_size=[10] * 3,
            smoothing_sigmas=[[2, 1], [2, 1], [1, 0]] if quick else [[3, 2, 1, 0]] * 3,
            shrink_factors=[[4, 2], [4, 2], [2, 1]] if quick else [[8, 4, 2, 1]] * 3,
            use_histogram_matching=[True] * 3,
            write_composite_transform=True,
            output_warped_image=True,
        ), name="ants_syn")

        wf.connect([
            (inputnode, mcflirt, [("bold", "in_file")]),
            (mcflirt, meanbold, [("out_file", "in_file")]),
            (inputnode, bet, [("t1w", "in_file")]),
            (bet, fast, [("out_file", "in_files")]),
            (fast, wm_mask, [(("tissue_class_files", lambda x: x[-1]), "in_file")]),
            (meanbold, flirt_init, [("out_file", "in_file")]),
            (bet, flirt_init, [("out_file", "reference")]),
            (meanbold, flirt_bbr, [("out_file", "in_file")]),
            (inputnode, flirt_bbr, [("t1w", "reference")]),
            (wm_mask, flirt_bbr, [("out_file", "wm_seg")]),
            (flirt_init, flirt_bbr, [("out_matrix_file", "in_matrix_file")]),
            (bet, syn, [("out_file", "moving_image")]),
            (inputnode, syn, [("mni_template", "fixed_image")]),
            (mcflirt, outputnode, [("out_file", "bold_mc"), ("par_file", "motion_params")]),
            (bet, outputnode, [("out_file", "t1w_brain"), ("mask_file", "brain_mask")]),
            (flirt_bbr, outputnode, [("out_matrix_file", "bold2t1w_mat")]),
            (syn, outputnode, [("composite_transform", "t1w2mni_warp"), ("warped_image", "t1w_mni")]),
        ])
        return wf

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]):
        """Composite ports feed downstream nodes; the manifest is built by the runner."""
        return None
