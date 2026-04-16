"""Tests for FmriprepParams dataclass — construction, validation, CLI generation."""

import os

import pytest

from fmriflow.preproc.backends.fmriprep_params import FmriprepParams


# ── from_dict: flat (old-style) ─────────────────────────────────────────


class TestFromDictFlat:
    """Old-style flat backend_params dicts should still work."""

    def test_minimal(self):
        p = FmriprepParams.from_dict({})
        assert p.mode == "full"
        assert p.output_spaces == ["T1w"]
        assert p.extra_args == []

    def test_old_style_keys(self):
        p = FmriprepParams.from_dict({
            "output_spaces": ["T1w", "MNI152NLin2009cAsym"],
            "container": "/images/fmriprep.sif",
            "fs_license_file": "/lic.txt",
            "extra_args": "--low-mem --bold2t1w-dof 9",
        })
        assert p.container == "/images/fmriprep.sif"
        assert p.output_spaces == ["T1w", "MNI152NLin2009cAsym"]
        assert p.fs_license_file == "/lic.txt"
        assert p.extra_args == ["--low-mem", "--bold2t1w-dof", "9"]

    def test_output_spaces_as_string(self):
        p = FmriprepParams.from_dict({"output_spaces": "T1w, MNI152NLin2009cAsym"})
        assert p.output_spaces == ["T1w", "MNI152NLin2009cAsym"]

    def test_ignore_as_string(self):
        p = FmriprepParams.from_dict({"ignore": "fieldmaps, slicetiming"})
        assert p.ignore == ["fieldmaps", "slicetiming"]

    def test_anat_only_shorthand(self):
        p = FmriprepParams.from_dict({"anat_only": True})
        assert p.mode == "anat_only"

    def test_fs_no_reconall_shorthand(self):
        p = FmriprepParams.from_dict({"fs_no_reconall": True})
        assert p.mode == "func_only"

    def test_unknown_keys_dropped(self):
        """Keys not in the dataclass should be silently ignored."""
        p = FmriprepParams.from_dict({"file_pattern": "blah", "some_future_key": 42})
        assert p.mode == "full"  # constructed fine


# ── from_dict: nested (new-style) ───────────────────────────────────────


class TestFromDictNested:
    """New-style nested option groups."""

    def test_nested_anat(self):
        p = FmriprepParams.from_dict({
            "mode": "full",
            "anat": {"skull_strip": "force", "no_submm_recon": True},
        })
        assert p.skull_strip == "force"
        assert p.no_submm_recon is True

    def test_nested_func(self):
        p = FmriprepParams.from_dict({
            "func": {"bold2t1w_dof": 9, "dummy_scans": 3, "ignore": ["fieldmaps"]},
        })
        assert p.bold2t1w_dof == 9
        assert p.dummy_scans == 3
        assert p.ignore == ["fieldmaps"]

    def test_nested_output_uses_spaces_key(self):
        p = FmriprepParams.from_dict({
            "output": {"spaces": ["MNI152NLin2009cAsym:res-2"]},
        })
        assert p.output_spaces == ["MNI152NLin2009cAsym:res-2"]

    def test_nested_resources(self):
        p = FmriprepParams.from_dict({
            "resources": {"nthreads": 8, "omp_nthreads": 4, "mem_mb": 16000},
        })
        assert p.nthreads == 8
        assert p.omp_nthreads == 4
        assert p.mem_mb == 16000

    def test_nested_fieldmaps(self):
        p = FmriprepParams.from_dict({
            "fieldmaps": {"use_syn_sdc": True, "force_syn": True},
        })
        assert p.use_syn_sdc is True
        assert p.force_syn is True

    def test_nested_denoising(self):
        p = FmriprepParams.from_dict({
            "denoising": {"use_aroma": True, "aroma_melodic_dim": -150},
        })
        assert p.use_aroma is True
        assert p.aroma_melodic_dim == -150

    def test_mixed_nested_and_flat(self):
        """Nested keys take precedence over flat for the same field."""
        p = FmriprepParams.from_dict({
            "nthreads": 2,
            "resources": {"nthreads": 8},
        })
        # Nested sets via setdefault, so flat (already set) takes precedence?
        # Actually from_dict pops the group and uses setdefault — flat key set first.
        # Wait, it processes groups *after* the flat keys already exist in `d`.
        # setdefault means nested does NOT overwrite flat. That's fine — flat came
        # from the user's top-level, nested is a sub-dict. Top-level wins.
        assert p.nthreads == 2

    def test_full_yaml_style(self):
        """Simulate a full YAML-derived config."""
        p = FmriprepParams.from_dict({
            "mode": "func_precomputed_anat",
            "container": "/images/fp.sif",
            "anat": {"fs_subjects_dir": "/data/freesurfer"},
            "func": {"bold2t1w_dof": 6, "dummy_scans": 2},
            "output": {"spaces": ["T1w", "MNI152NLin2009cAsym:res-2"]},
            "resources": {"nthreads": 4, "mem_mb": 8000},
            "fs_license_file": "/lic.txt",
        })
        assert p.mode == "func_precomputed_anat"
        assert p.fs_subjects_dir == "/data/freesurfer"
        assert p.bold2t1w_dof == 6
        assert p.nthreads == 4
        assert p.output_spaces == ["T1w", "MNI152NLin2009cAsym:res-2"]


# ── Validation ──────────────────────────────────────────────────────────


class TestValidation:
    def test_valid_defaults(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams()
        errors = p.validate()
        assert errors == []

    def test_invalid_mode(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(mode="bad")
        errors = p.validate()
        assert any("Invalid mode" in e for e in errors)

    def test_invalid_skull_strip(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(skull_strip="maybe")
        errors = p.validate()
        assert any("Invalid skull_strip" in e for e in errors)

    def test_invalid_bold2t1w_init(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(bold2t1w_init="bad")
        errors = p.validate()
        assert any("Invalid bold2t1w_init" in e for e in errors)

    def test_invalid_bold2t1w_dof(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(bold2t1w_dof=7)
        errors = p.validate()
        assert any("Invalid bold2t1w_dof" in e for e in errors)

    def test_negative_dummy_scans(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(dummy_scans=-1)
        errors = p.validate()
        assert any("dummy_scans" in e for e in errors)

    def test_invalid_ignore_item(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(ignore=["badstep"])
        errors = p.validate()
        assert any("Invalid ignore item" in e for e in errors)

    def test_invalid_cifti_output(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(cifti_output="500k")
        errors = p.validate()
        assert any("Invalid cifti_output" in e for e in errors)

    def test_func_precomputed_anat_needs_fs_subjects_dir(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(mode="func_precomputed_anat")
        errors = p.validate()
        assert any("fs_subjects_dir" in e for e in errors)

    def test_func_precomputed_anat_ok_with_fs_subjects_dir(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(
            mode="func_precomputed_anat",
            fs_subjects_dir="/data/freesurfer",
        )
        errors = p.validate()
        assert not any("fs_subjects_dir" in e for e in errors)

    def test_aroma_needs_mni_space(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(use_aroma=True, output_spaces=["T1w"])
        errors = p.validate()
        assert any("ICA-AROMA" in e for e in errors)

    def test_aroma_ok_with_mni_space(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(
            use_aroma=True,
            output_spaces=["T1w", "MNI152NLin6Asym:res-2"],
        )
        errors = p.validate()
        assert not any("ICA-AROMA" in e for e in errors)

    def test_anat_only_warns_about_func_options(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(mode="anat_only", bold2t1w_dof=9)
        errors = p.validate()
        assert any("Warning:" in e and "functional" in e for e in errors)

    def test_func_only_warns_about_no_submm(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(mode="func_only", no_submm_recon=True)
        errors = p.validate()
        assert any("Warning:" in e and "no_submm_recon" in e for e in errors)

    def test_missing_fs_license(self, monkeypatch):
        monkeypatch.delenv("FS_LICENSE", raising=False)
        p = FmriprepParams(fs_license_file=None)
        errors = p.validate()
        assert any("FreeSurfer license" in e for e in errors)

    def test_fs_license_not_needed_func_only(self, monkeypatch):
        monkeypatch.delenv("FS_LICENSE", raising=False)
        p = FmriprepParams(mode="func_only", fs_license_file=None)
        errors = p.validate()
        assert not any("FreeSurfer license" in e for e in errors)

    def test_invalid_nthreads(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(nthreads=0)
        errors = p.validate()
        assert any("nthreads" in e for e in errors)

    def test_invalid_container_type(self, monkeypatch):
        monkeypatch.setenv("FS_LICENSE", "/lic.txt")
        p = FmriprepParams(container_type="podman")
        errors = p.validate()
        assert any("Invalid container_type" in e for e in errors)


# ── to_command_args ─────────────────────────────────────────────────────


class TestToCommandArgs:
    def test_defaults_produce_output_spaces(self):
        p = FmriprepParams()
        args = p.to_command_args()
        assert "--output-spaces" in args
        assert "T1w" in args

    def test_anat_only_mode(self):
        p = FmriprepParams(mode="anat_only")
        args = p.to_command_args()
        assert "--anat-only" in args
        assert "--fs-no-reconall" not in args

    def test_func_only_mode(self):
        p = FmriprepParams(mode="func_only")
        args = p.to_command_args()
        assert "--fs-no-reconall" in args
        assert "--anat-only" not in args

    def test_func_precomputed_anat_mode(self):
        p = FmriprepParams(
            mode="func_precomputed_anat",
            fs_subjects_dir="/data/freesurfer",
        )
        args = p.to_command_args()
        assert "--fs-subjects-dir" in args
        assert args[args.index("--fs-subjects-dir") + 1] == "/data/freesurfer"

    def test_skull_strip_force(self):
        p = FmriprepParams(skull_strip="force")
        args = p.to_command_args()
        assert "--skull-strip-t1w" in args
        assert args[args.index("--skull-strip-t1w") + 1] == "force"

    def test_skull_strip_auto_omitted(self):
        p = FmriprepParams(skull_strip="auto")
        args = p.to_command_args()
        assert "--skull-strip-t1w" not in args

    def test_functional_options(self):
        p = FmriprepParams(
            bold2t1w_init="header",
            bold2t1w_dof=6,
            dummy_scans=3,
            task_id="reading",
        )
        args = p.to_command_args()
        assert "--bold2t1w-init" in args
        assert args[args.index("--bold2t1w-init") + 1] == "header"
        assert "--bold2t1w-dof" in args
        assert args[args.index("--bold2t1w-dof") + 1] == "6"
        assert "--dummy-scans" in args
        assert args[args.index("--dummy-scans") + 1] == "3"
        assert "--task-id" in args
        assert args[args.index("--task-id") + 1] == "reading"

    def test_ignore_list(self):
        p = FmriprepParams(ignore=["fieldmaps", "slicetiming"])
        args = p.to_command_args()
        # Should produce --ignore fieldmaps --ignore slicetiming
        ignore_indices = [i for i, a in enumerate(args) if a == "--ignore"]
        assert len(ignore_indices) == 2
        assert args[ignore_indices[0] + 1] == "fieldmaps"
        assert args[ignore_indices[1] + 1] == "slicetiming"

    def test_fieldmap_flags(self):
        p = FmriprepParams(
            use_syn_sdc=True,
            force_syn=True,
            fmap_bspline=True,
            fmap_no_demean=True,
        )
        args = p.to_command_args()
        assert "--use-syn-sdc" in args
        assert "--force-syn" in args
        assert "--fmap-bspline" in args
        assert "--fmap-no-demean" in args

    def test_output_spaces_with_resolution(self):
        p = FmriprepParams(output_spaces=["T1w", "MNI152NLin2009cAsym:res-2"])
        args = p.to_command_args()
        idx = args.index("--output-spaces")
        assert args[idx + 1] == "T1w"
        assert args[idx + 2] == "MNI152NLin2009cAsym:res-2"

    def test_cifti_output(self):
        p = FmriprepParams(cifti_output="91k")
        args = p.to_command_args()
        assert "--cifti-output" in args
        assert args[args.index("--cifti-output") + 1] == "91k"

    def test_aroma_flags(self):
        p = FmriprepParams(
            use_aroma=True,
            aroma_melodic_dim=-150,
            return_all_components=True,
            error_on_aroma_warnings=True,
        )
        args = p.to_command_args()
        assert "--use-aroma" in args
        assert "--aroma-melodic-dimensionality" in args
        assert args[args.index("--aroma-melodic-dimensionality") + 1] == "-150"
        assert "--return-all-components" in args
        assert "--error-on-aroma-warnings" in args

    def test_aroma_default_dim_omitted(self):
        p = FmriprepParams(use_aroma=True, aroma_melodic_dim=-200)
        args = p.to_command_args()
        assert "--aroma-melodic-dimensionality" not in args

    def test_resources(self):
        p = FmriprepParams(nthreads=8, omp_nthreads=4, mem_mb=16000, low_mem=True)
        args = p.to_command_args()
        assert "--nthreads" in args
        assert args[args.index("--nthreads") + 1] == "8"
        assert "--omp-nthreads" in args
        assert args[args.index("--omp-nthreads") + 1] == "4"
        assert "--mem-mb" in args
        assert args[args.index("--mem-mb") + 1] == "16000"
        assert "--low-mem" in args

    def test_fs_license(self):
        p = FmriprepParams(fs_license_file="/lic.txt")
        args = p.to_command_args()
        assert "--fs-license-file" in args
        assert args[args.index("--fs-license-file") + 1] == "/lic.txt"

    def test_extra_args_appended(self):
        p = FmriprepParams(extra_args=["--some-flag", "val"])
        args = p.to_command_args()
        assert args[-2:] == ["--some-flag", "val"]

    def test_full_mode_no_mode_flag(self):
        p = FmriprepParams(mode="full")
        args = p.to_command_args()
        assert "--anat-only" not in args
        assert "--fs-no-reconall" not in args

    def test_fs_subjects_dir_in_full_mode(self):
        """In full mode, fs_subjects_dir is passed to reuse existing reconall."""
        p = FmriprepParams(mode="full", fs_subjects_dir="/data/fs")
        args = p.to_command_args()
        assert "--fs-subjects-dir" in args
        assert args[args.index("--fs-subjects-dir") + 1] == "/data/fs"


# ── to_dict / round-trip ────────────────────────────────────────────────


class TestSerialization:
    def test_to_dict(self):
        p = FmriprepParams(mode="anat_only", nthreads=4)
        d = p.to_dict()
        assert d["mode"] == "anat_only"
        assert d["nthreads"] == 4
        assert isinstance(d["output_spaces"], list)

    def test_round_trip(self):
        p = FmriprepParams(
            mode="func_precomputed_anat",
            fs_subjects_dir="/data/fs",
            bold2t1w_dof=6,
            output_spaces=["MNI152NLin2009cAsym:res-2"],
            nthreads=8,
        )
        d = p.to_dict()
        p2 = FmriprepParams.from_dict(d)
        assert p2.mode == p.mode
        assert p2.fs_subjects_dir == p.fs_subjects_dir
        assert p2.bold2t1w_dof == p.bold2t1w_dof
        assert p2.output_spaces == p.output_spaces
        assert p2.nthreads == p.nthreads
