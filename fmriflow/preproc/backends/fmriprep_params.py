"""Structured parameter model for the fmriprep backend.

Replaces the untyped ``backend_params`` dict with a validated dataclass
that knows how to serialize itself to fmriprep CLI arguments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Valid values for constrained fields
VALID_MODES = ("full", "anat_only", "func_only", "func_precomputed_anat")
VALID_SKULL_STRIP = ("auto", "force", "skip")
VALID_BOLD2T1W_INIT = ("register", "header")
VALID_BOLD2T1W_DOF = (6, 9, 12)
VALID_CIFTI_OUTPUT = ("91k", "170k")
VALID_IGNORE = ("fieldmaps", "slicetiming", "sbref")
VALID_CONTAINER_TYPES = ("singularity", "docker", "bare")


@dataclass(frozen=True)
class FmriprepParams:
    """Structured fmriprep parameters.

    Groups fmriprep's CLI flags into logical sections and provides
    validation and CLI argument generation.
    """

    # ── Mode ────────────────────────────────────────────────────────
    mode: str = "full"

    # ── Container ───────────────────────────────────────────────────
    container: str | None = None
    container_type: str = "singularity"

    # ── Anatomical ──────────────────────────────────────────────────
    skull_strip: str = "auto"
    skull_strip_template: str | None = None
    no_submm_recon: bool = False
    fs_subjects_dir: str | None = None

    # ── Functional ──────────────────────────────────────────────────
    bold2t1w_init: str | None = None
    bold2t1w_dof: int | None = None
    dummy_scans: int | None = None
    task_id: str | None = None
    ignore: list[str] = field(default_factory=list)

    # ── Fieldmaps ───────────────────────────────────────────────────
    use_syn_sdc: bool = False
    force_syn: bool = False
    fmap_bspline: bool = False
    fmap_no_demean: bool = False

    # ── Output ──────────────────────────────────────────────────────
    output_spaces: list[str] = field(default_factory=lambda: ["T1w"])
    cifti_output: str | None = None
    me_output_echos: bool = False

    # ── Denoising ───────────────────────────────────────────────────
    use_aroma: bool = False
    aroma_melodic_dim: int = -200
    return_all_components: bool = False
    error_on_aroma_warnings: bool = False

    # ── Resources ───────────────────────────────────────────────────
    nthreads: int | None = None
    omp_nthreads: int | None = None
    mem_mb: int | None = None
    low_mem: bool = False
    stop_on_first_crash: bool = False

    # ── FreeSurfer ──────────────────────────────────────────────────
    fs_license_file: str | None = None

    # ── Escape hatch ────────────────────────────────────────────────
    extra_args: list[str] = field(default_factory=list)

    # ── Validation ──────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return a list of validation errors and warnings.

        Warnings are prefixed with ``"Warning: "``.
        """
        errors: list[str] = []

        # Mode
        if self.mode not in VALID_MODES:
            errors.append(
                f"Invalid mode '{self.mode}'. "
                f"Must be one of: {', '.join(VALID_MODES)}"
            )

        # Container type
        if self.container_type not in VALID_CONTAINER_TYPES:
            errors.append(
                f"Invalid container_type '{self.container_type}'. "
                f"Must be one of: {', '.join(VALID_CONTAINER_TYPES)}"
            )

        # Skull strip
        if self.skull_strip not in VALID_SKULL_STRIP:
            errors.append(
                f"Invalid skull_strip '{self.skull_strip}'. "
                f"Must be one of: {', '.join(VALID_SKULL_STRIP)}"
            )

        # bold2t1w_init
        if self.bold2t1w_init and self.bold2t1w_init not in VALID_BOLD2T1W_INIT:
            errors.append(
                f"Invalid bold2t1w_init '{self.bold2t1w_init}'. "
                f"Must be one of: {', '.join(VALID_BOLD2T1W_INIT)}"
            )

        # bold2t1w_dof
        if self.bold2t1w_dof is not None and self.bold2t1w_dof not in VALID_BOLD2T1W_DOF:
            errors.append(
                f"Invalid bold2t1w_dof {self.bold2t1w_dof}. "
                f"Must be one of: {', '.join(str(d) for d in VALID_BOLD2T1W_DOF)}"
            )

        # dummy_scans
        if self.dummy_scans is not None and self.dummy_scans < 0:
            errors.append(f"dummy_scans must be >= 0, got {self.dummy_scans}")

        # ignore
        for item in self.ignore:
            if item not in VALID_IGNORE:
                errors.append(
                    f"Invalid ignore item '{item}'. "
                    f"Must be one of: {', '.join(VALID_IGNORE)}"
                )

        # cifti_output
        if self.cifti_output and self.cifti_output not in VALID_CIFTI_OUTPUT:
            errors.append(
                f"Invalid cifti_output '{self.cifti_output}'. "
                f"Must be one of: {', '.join(VALID_CIFTI_OUTPUT)}"
            )

        # Cross-option checks
        if self.mode == "func_precomputed_anat" and not self.fs_subjects_dir:
            errors.append(
                "mode 'func_precomputed_anat' requires fs_subjects_dir "
                "pointing to an existing FreeSurfer subjects directory."
            )

        if self.use_aroma:
            has_aroma_space = any(
                s.startswith("MNI152NLin6Asym") for s in self.output_spaces
            )
            if not has_aroma_space:
                errors.append(
                    "ICA-AROMA requires 'MNI152NLin6Asym:res-2' in "
                    "output_spaces. Add it or disable use_aroma."
                )

        # Warnings for irrelevant options
        if self.mode == "anat_only":
            func_set = (
                self.bold2t1w_init is not None
                or self.bold2t1w_dof is not None
                or self.dummy_scans is not None
                or self.use_aroma
                or self.use_syn_sdc
                or self.force_syn
            )
            if func_set:
                errors.append(
                    "Warning: functional options are set but mode is "
                    "'anat_only' — they will be ignored by fmriprep."
                )

        if self.mode == "func_only" and self.no_submm_recon:
            errors.append(
                "Warning: no_submm_recon is set but mode is 'func_only' "
                "(no reconall) — it will be ignored."
            )

        # Resource sanity
        if self.nthreads is not None and self.nthreads < 1:
            errors.append(f"nthreads must be >= 1, got {self.nthreads}")
        if self.omp_nthreads is not None and self.omp_nthreads < 1:
            errors.append(f"omp_nthreads must be >= 1, got {self.omp_nthreads}")
        if self.mem_mb is not None and self.mem_mb < 1:
            errors.append(f"mem_mb must be >= 1, got {self.mem_mb}")

        # FreeSurfer license
        fs_license = self.fs_license_file or os.environ.get("FS_LICENSE")
        if not fs_license and self.mode != "func_only":
            errors.append(
                "FreeSurfer license not found. "
                "Set fs_license_file or the FS_LICENSE env var."
            )

        return errors

    # ── CLI argument generation ─────────────────────────────────────

    def to_command_args(self) -> list[str]:
        """Convert to a list of fmriprep CLI arguments.

        Does not include the positional args (bids_dir, output_dir,
        analysis_level) or --participant-label — those are handled by
        the backend's ``_build_command``.
        """
        args: list[str] = []

        # Mode flags
        if self.mode == "anat_only":
            args.append("--anat-only")
        elif self.mode == "func_only":
            args.append("--fs-no-reconall")
        elif self.mode == "func_precomputed_anat":
            if self.fs_subjects_dir:
                args += ["--fs-subjects-dir", self.fs_subjects_dir]

        # Anatomical
        if self.skull_strip == "force":
            args += ["--skull-strip-t1w", "force"]
        elif self.skull_strip == "skip":
            args += ["--skull-strip-t1w", "skip"]
        # "auto" is fmriprep's default — no flag needed

        if self.skull_strip_template:
            args += ["--skull-strip-template", self.skull_strip_template]

        if self.no_submm_recon:
            args.append("--no-submm-recon")

        # fs_subjects_dir already handled in mode section for
        # func_precomputed_anat; but user may also set it in full mode
        # to reuse existing reconall outputs
        if self.fs_subjects_dir and self.mode != "func_precomputed_anat":
            args += ["--fs-subjects-dir", self.fs_subjects_dir]

        # Functional
        if self.bold2t1w_init:
            args += ["--bold2t1w-init", self.bold2t1w_init]

        if self.bold2t1w_dof is not None:
            args += ["--bold2t1w-dof", str(self.bold2t1w_dof)]

        if self.dummy_scans is not None:
            args += ["--dummy-scans", str(self.dummy_scans)]

        if self.task_id:
            args += ["--task-id", self.task_id]

        for item in self.ignore:
            args += ["--ignore", item]

        # Fieldmaps
        if self.use_syn_sdc:
            args.append("--use-syn-sdc")

        if self.force_syn:
            args.append("--force-syn")

        if self.fmap_bspline:
            args.append("--fmap-bspline")

        if self.fmap_no_demean:
            args.append("--fmap-no-demean")

        # Output
        if self.output_spaces:
            args += ["--output-spaces"] + self.output_spaces

        if self.cifti_output:
            args += ["--cifti-output", self.cifti_output]

        if self.me_output_echos:
            args.append("--me-output-echos")

        # Denoising
        if self.use_aroma:
            args.append("--use-aroma")

        if self.aroma_melodic_dim != -200:
            args += ["--aroma-melodic-dimensionality", str(self.aroma_melodic_dim)]

        if self.return_all_components:
            args.append("--return-all-components")

        if self.error_on_aroma_warnings:
            args.append("--error-on-aroma-warnings")

        # Resources
        if self.nthreads is not None:
            args += ["--nthreads", str(self.nthreads)]

        if self.omp_nthreads is not None:
            args += ["--omp-nthreads", str(self.omp_nthreads)]

        if self.mem_mb is not None:
            args += ["--mem-mb", str(self.mem_mb)]

        if self.low_mem:
            args.append("--low-mem")

        if self.stop_on_first_crash:
            args.append("--stop-on-first-crash")

        # FreeSurfer license
        if self.fs_license_file:
            args += ["--fs-license-file", str(self.fs_license_file)]

        # Escape hatch
        args += self.extra_args

        return args

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dict for manifest recording."""
        from dataclasses import asdict
        return asdict(self)

    # ── Construction ────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FmriprepParams:
        """Parse from a backend_params dict.

        Handles two layouts:

        1. **Nested** (new-style) — option groups as sub-dicts::

            {"mode": "full", "anat": {"skull_strip": "force"}, ...}

        2. **Flat** (old-style / backward compat) — keys at the top level::

            {"output_spaces": ["T1w"], "container": "...", "fs_license_file": "..."}
        """
        # Work on a copy
        d = dict(data)

        # ── Flatten nested groups into top-level keys ───────────
        for group_key in ("anat", "func", "fieldmaps", "output",
                          "denoising", "resources"):
            nested = d.pop(group_key, None)
            if isinstance(nested, dict):
                for k, v in nested.items():
                    # Nested keys take precedence over top-level
                    d.setdefault(k, v)

        # ── Rename output.spaces → output_spaces ────────────────
        if "spaces" in d and "output_spaces" not in d:
            d["output_spaces"] = d.pop("spaces")

        # ── Normalize output_spaces to list ─────────────────────
        spaces = d.get("output_spaces")
        if isinstance(spaces, str):
            d["output_spaces"] = [s.strip() for s in spaces.split(",") if s.strip()]

        # ── Normalize ignore to list ────────────────────────────
        ignore = d.get("ignore")
        if isinstance(ignore, str):
            d["ignore"] = [s.strip() for s in ignore.split(",") if s.strip()]

        # ── Normalize extra_args ────────────────────────────────
        extra = d.get("extra_args")
        if isinstance(extra, str):
            d["extra_args"] = extra.split()

        # ── Map old-style shorthand flags ───────────────────────
        # --anat-only / --fs-no-reconall set via backend_params
        if d.pop("anat_only", False):
            d.setdefault("mode", "anat_only")
        if d.pop("fs_no_reconall", False):
            d.setdefault("mode", "func_only")

        # ── Drop unknown keys to avoid TypeError ────────────────
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_fields}

        return cls(**filtered)
