"""Phase 4b — real passthrough workflow tests.

Exercises ``PassthroughWorkflow.to_manifest`` against a synthetic
BIDS-derivatives tree on disk. Three flavours of input:

- A multi-run derivatives layout with realistic filenames →
  manifest has one RunRecord per file, run_name pulled from the
  ``run-XX`` token.
- An empty derivatives dir → empty-runs manifest + warning logged
  (downstream stages can reject; passthrough itself doesn't).
- Custom glob pattern → only matching files end up in the manifest.

Validation tests live separately because they exercise the *refuse
to build* path that's important enough to enforce in a focused test.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fmriflow.preproc.backends.nipype_workflows.passthrough import (
    PassthroughWorkflow,
    _run_name_from_filename,
)


class _StubConfig:
    """Minimal duck-typed _WorkflowCallConfig."""

    def __init__(self, **kwargs):
        defaults = {
            "subject": "sub01",
            "output_dir": "/tmp/out",
            "bids_dir": None,
            "derivatives_dir": None,
            "sessions": [],
            "task": None,
            "dataset": "study1",
            "backend_params": {},
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


def _make_derivatives(root: Path, subject: str, filenames: list[str]) -> Path:
    """Create a fake BIDS-derivatives layout with empty NIfTIs."""
    sub_dir = root / f"sub-{subject}"
    sub_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (sub_dir / name).write_bytes(b"")
    return root


# ── Validate ───────────────────────────────────────────────────────


class TestValidate:
    def test_no_derivatives_dir_is_error(self):
        wf = PassthroughWorkflow()
        config = _StubConfig(derivatives_dir=None)
        errors = wf.validate(config)
        assert len(errors) == 1
        assert "derivatives_dir" in errors[0]

    def test_non_existent_derivatives_dir_is_error(self, tmp_path):
        wf = PassthroughWorkflow()
        config = _StubConfig(derivatives_dir=str(tmp_path / "ghost"))
        errors = wf.validate(config)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_missing_subject_is_error(self, tmp_path):
        wf = PassthroughWorkflow()
        config = _StubConfig(subject="", derivatives_dir=str(tmp_path))
        errors = wf.validate(config)
        assert any("subject" in e for e in errors)

    def test_valid_derivatives_dir_clean(self, tmp_path):
        _make_derivatives(tmp_path, "sub01", [])
        wf = PassthroughWorkflow()
        config = _StubConfig(derivatives_dir=str(tmp_path))
        assert wf.validate(config) == []


# ── Scanning ───────────────────────────────────────────────────────


class TestToManifestScans:
    def test_multi_run_layout(self, tmp_path):
        _make_derivatives(
            tmp_path, "sub01",
            [
                "sub-sub01_task-story_run-01_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz",
                "sub-sub01_task-story_run-02_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz",
                "sub-sub01_task-story_run-03_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz",
                # Non-matching files should be ignored.
                "sub-sub01_task-story_run-01_desc-confounds_timeseries.tsv",
                "sub-sub01_task-story_run-01_desc-brain_mask.nii.gz",
            ],
        )

        wf = PassthroughWorkflow()
        config = _StubConfig(derivatives_dir=str(tmp_path))
        manifest = wf.to_manifest(config, {})

        assert manifest.backend == "passthrough"
        assert manifest.backend_version == "0.1.0"
        assert len(manifest.runs) == 3
        run_names = [r.run_name for r in manifest.runs]
        assert run_names == ["run-01", "run-02", "run-03"]

    def test_empty_derivatives_emits_warning(self, tmp_path, caplog):
        _make_derivatives(tmp_path, "sub01", [])
        wf = PassthroughWorkflow()
        config = _StubConfig(derivatives_dir=str(tmp_path))

        with caplog.at_level(logging.WARNING):
            manifest = wf.to_manifest(config, {})

        assert manifest.runs == []
        assert any("no files matching" in rec.message for rec in caplog.records)

    def test_custom_glob_pattern(self, tmp_path):
        _make_derivatives(
            tmp_path, "sub01",
            [
                "sub-sub01_run-01_space-T1w_desc-preproc_bold.nii.gz",
                "sub-sub01_run-01_space-MNI_desc-preproc_bold.nii.gz",
            ],
        )

        wf = PassthroughWorkflow()
        config = _StubConfig(
            derivatives_dir=str(tmp_path),
            backend_params={"file_pattern": "*space-T1w*_desc-preproc_bold.nii.gz"},
        )
        manifest = wf.to_manifest(config, {})

        # Only the T1w-space file matched.
        assert len(manifest.runs) == 1
        assert "space-T1w" in manifest.runs[0].output_file

    def test_falls_back_to_root_when_no_subject_subdir(self, tmp_path):
        # If derivatives_dir/sub-<subject>/ doesn't exist, scan the
        # whole derivatives_dir (some non-BIDS layouts have files
        # directly at the root).
        (tmp_path / "any_file_desc-preproc_bold.nii.gz").write_bytes(b"")
        wf = PassthroughWorkflow()
        config = _StubConfig(derivatives_dir=str(tmp_path))
        manifest = wf.to_manifest(config, {})
        assert len(manifest.runs) == 1


# ── run_name extraction ────────────────────────────────────────────


class TestRunNameFromFilename:
    def test_pulls_run_xx_token(self):
        assert _run_name_from_filename(
            Path("sub-sub01_task-x_run-02_desc-preproc_bold.nii.gz")
        ) == "run-02"

    def test_falls_back_to_stem(self):
        assert _run_name_from_filename(
            Path("some_arbitrary_filename.nii.gz")
        ) == "some_arbitrary_filename"
