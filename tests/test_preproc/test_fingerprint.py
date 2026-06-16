"""Phase 4c — fingerprint computation tests.

Bootstrap fingerprint contract:
- deterministic (same inputs → same hash)
- param order doesn't matter (sorted-JSON)
- changing kind / workflow / version / params / BIDS mtimes each
  independently changes the hash
- missing input dir produces a stable (non-empty) hash

Transform fingerprint contract:
- includes the prior stage's fingerprint, so any upstream change
  cascades
- input file mtime/size changes invalidate
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fmriflow.preproc.fingerprint import (
    bootstrap_fingerprint,
    transform_fingerprint,
)
from fmriflow.preproc.stack import BootstrapStage, TransformStage


class _StubWorkflow:
    name = "identity"
    version = "0.1.0"


def _populate_bids_subject(root: Path, subject: str, files: list[str]) -> Path:
    sub = root / f"sub-{subject}"
    sub.mkdir(parents=True, exist_ok=True)
    for name in files:
        (sub / name).write_bytes(b"x" * 16)
    return root


# ── Bootstrap fingerprint ─────────────────────────────────────────


class TestBootstrapFingerprintDeterminism:
    def test_same_inputs_same_hash(self, tmp_path):
        _populate_bids_subject(tmp_path, "sub01", ["a.nii.gz", "b.nii.gz"])
        stage = BootstrapStage(kind="nipype", workflow="identity", params={"x": 1})
        wf = _StubWorkflow()
        a = bootstrap_fingerprint(stage, wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01")
        b = bootstrap_fingerprint(stage, wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01")
        assert a == b
        assert len(a) == 16

    def test_param_order_doesnt_matter(self, tmp_path):
        _populate_bids_subject(tmp_path, "sub01", ["a.nii.gz"])
        wf = _StubWorkflow()
        a = bootstrap_fingerprint(
            BootstrapStage(kind="nipype", workflow="identity", params={"x": 1, "y": 2}),
            wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )
        b = bootstrap_fingerprint(
            BootstrapStage(kind="nipype", workflow="identity", params={"y": 2, "x": 1}),
            wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )
        assert a == b


class TestBootstrapFingerprintInvalidation:
    def test_changing_kind_changes_hash(self, tmp_path):
        _populate_bids_subject(tmp_path, "sub01", ["a.nii.gz"])
        wf = _StubWorkflow()
        a = bootstrap_fingerprint(
            BootstrapStage(kind="nipype", workflow="identity"),
            wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )
        b = bootstrap_fingerprint(
            BootstrapStage(kind="fmriprep"),
            wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )
        assert a != b

    def test_changing_workflow_changes_hash(self, tmp_path):
        _populate_bids_subject(tmp_path, "sub01", ["a.nii.gz"])
        a = bootstrap_fingerprint(
            BootstrapStage(kind="nipype", workflow="identity"),
            _StubWorkflow(),
            bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )

        class OtherWf:
            name = "other"
            version = "0.1.0"

        b = bootstrap_fingerprint(
            BootstrapStage(kind="nipype", workflow="other"),
            OtherWf(),
            bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )
        assert a != b

    def test_changing_version_changes_hash(self, tmp_path):
        _populate_bids_subject(tmp_path, "sub01", ["a.nii.gz"])
        stage = BootstrapStage(kind="nipype", workflow="identity")
        a = bootstrap_fingerprint(
            stage, _StubWorkflow(),
            bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )

        class OlderVersion:
            name = "identity"
            version = "0.0.1"

        b = bootstrap_fingerprint(
            stage, OlderVersion(),
            bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )
        assert a != b

    def test_changing_params_changes_hash(self, tmp_path):
        _populate_bids_subject(tmp_path, "sub01", ["a.nii.gz"])
        wf = _StubWorkflow()
        a = bootstrap_fingerprint(
            BootstrapStage(kind="nipype", workflow="identity", params={"fwhm": 6}),
            wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )
        b = bootstrap_fingerprint(
            BootstrapStage(kind="nipype", workflow="identity", params={"fwhm": 8}),
            wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01",
        )
        assert a != b

    def test_touching_bids_file_changes_hash(self, tmp_path):
        _populate_bids_subject(tmp_path, "sub01", ["a.nii.gz"])
        stage = BootstrapStage(kind="nipype", workflow="identity")
        wf = _StubWorkflow()
        a = bootstrap_fingerprint(stage, wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01")

        # Bump the file's mtime by a noticeable amount.
        target = tmp_path / "sub-sub01" / "a.nii.gz"
        future = time.time() + 60
        os.utime(target, (future, future))

        b = bootstrap_fingerprint(stage, wf, bids_dir=tmp_path, derivatives_dir=None, subject="sub01")
        assert a != b

    def test_passthrough_keys_off_derivatives_not_bids(self, tmp_path):
        bids = tmp_path / "bids"
        deriv = tmp_path / "deriv"
        _populate_bids_subject(bids, "sub01", ["a.nii.gz"])
        _populate_bids_subject(deriv, "sub01", ["x.nii.gz"])

        stage = BootstrapStage(kind="passthrough")
        wf = _StubWorkflow()
        a = bootstrap_fingerprint(stage, wf, bids_dir=bids, derivatives_dir=deriv, subject="sub01")

        # Touching the BIDS dir should NOT change a passthrough fingerprint.
        future = time.time() + 60
        os.utime(bids / "sub-sub01" / "a.nii.gz", (future, future))
        b = bootstrap_fingerprint(stage, wf, bids_dir=bids, derivatives_dir=deriv, subject="sub01")
        assert a == b

        # But touching the derivatives DOES.
        os.utime(deriv / "sub-sub01" / "x.nii.gz", (future, future))
        c = bootstrap_fingerprint(stage, wf, bids_dir=bids, derivatives_dir=deriv, subject="sub01")
        assert a != c

    def test_missing_input_dir_still_stable_hash(self):
        stage = BootstrapStage(kind="nipype", workflow="identity")
        wf = _StubWorkflow()
        a = bootstrap_fingerprint(stage, wf, bids_dir=None, derivatives_dir=None, subject="sub01")
        b = bootstrap_fingerprint(stage, wf, bids_dir=None, derivatives_dir=None, subject="sub01")
        assert a == b
        assert len(a) == 16


# ── Transform fingerprint ─────────────────────────────────────────


class _StubTransform:
    name = "smooth"
    version = "0.3.1"


class TestTransformFingerprintCascading:
    def test_changing_prior_changes_hash(self):
        stage = TransformStage(name="smooth", params={"fwhm": 6})
        t = _StubTransform()
        a = transform_fingerprint(stage, t, prior_fingerprint="abc12345", inputs={})
        b = transform_fingerprint(stage, t, prior_fingerprint="def67890", inputs={})
        assert a != b

    def test_changing_params_changes_hash(self):
        t = _StubTransform()
        a = transform_fingerprint(
            TransformStage(name="smooth", params={"fwhm": 6}),
            t, prior_fingerprint="abc", inputs={},
        )
        b = transform_fingerprint(
            TransformStage(name="smooth", params={"fwhm": 8}),
            t, prior_fingerprint="abc", inputs={},
        )
        assert a != b

    def test_changing_version_changes_hash(self):
        stage = TransformStage(name="smooth", params={})
        a = transform_fingerprint(stage, _StubTransform(), prior_fingerprint="abc", inputs={})

        class OlderTransform:
            name = "smooth"
            version = "0.1.0"

        b = transform_fingerprint(stage, OlderTransform(), prior_fingerprint="abc", inputs={})
        assert a != b

    def test_input_mtime_invalidates(self, tmp_path):
        infile = tmp_path / "input.nii.gz"
        infile.write_bytes(b"x" * 32)

        stage = TransformStage(name="smooth", params={})
        t = _StubTransform()

        a = transform_fingerprint(
            stage, t, prior_fingerprint="abc", inputs={"in_file": infile},
        )

        future = time.time() + 60
        os.utime(infile, (future, future))

        b = transform_fingerprint(
            stage, t, prior_fingerprint="abc", inputs={"in_file": infile},
        )
        assert a != b

    def test_missing_input_files_still_stable(self):
        # Inputs that don't exist on disk are encoded as "missing" —
        # the hash is stable so cache lookups still work in the
        # identity-bootstrap (empty-runs) edge case.
        stage = TransformStage(name="identity")

        class IdentityTransform:
            name = "identity"
            version = "0.1.0"

        a = transform_fingerprint(
            stage, IdentityTransform(),
            prior_fingerprint="abc",
            inputs={"in_file": "/nowhere/ghost.nii.gz"},
        )
        b = transform_fingerprint(
            stage, IdentityTransform(),
            prior_fingerprint="abc",
            inputs={"in_file": "/nowhere/ghost.nii.gz"},
        )
        assert a == b

    def test_none_input_is_handled(self):
        # _collect_inputs returns {key: None} when manifest has no runs.
        stage = TransformStage(name="identity")

        class IdentityTransform:
            name = "identity"
            version = "0.1.0"

        a = transform_fingerprint(
            stage, IdentityTransform(),
            prior_fingerprint="abc",
            inputs={"in_file": None},
        )
        assert len(a) == 16
