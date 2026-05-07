"""PreprocManager discovers manifests recorded by the run registry,
even when they live outside the configured derivatives root."""

from __future__ import annotations

from pathlib import Path

from fmriflow.preproc.manifest import PreprocManifest, RunRecord
from fmriflow.server.services.preproc_manager import PreprocManager
from fmriflow.server.services.run_registry import RunRegistry, RunStateFile


def _write_manifest(out_dir: Path, subject: str, dataset: str = "ds-test") -> Path:
    sub_dir = out_dir / f"sub-{subject}"
    sub_dir.mkdir(parents=True)
    manifest = PreprocManifest(
        subject=subject,
        dataset=dataset,
        sessions=[],
        runs=[RunRecord(
            run_name="r1",
            source_file="src.nii.gz",
            output_file="bold.nii.gz",
            n_trs=1,
            shape=[1, 1, 1, 1],
        )],
        backend="fmriprep",
        backend_version="25.1.3",
        parameters={},
        space="MNI",
        output_dir=str(out_dir),
    )
    p = sub_dir / "preproc_manifest.json"
    manifest.save(p)
    return p


def test_finds_manifests_under_derivatives_dir(tmp_path):
    derivatives = tmp_path / "derivatives"
    derivatives.mkdir()
    _write_manifest(derivatives / "fmriprep", "01")
    registry = RunRegistry(root=tmp_path / "runs")
    mgr = PreprocManager(derivatives, registry=registry)
    summaries = mgr.scan_manifests()
    subjects = [s["subject"] for s in summaries]
    assert "01" in subjects


def test_finds_manifests_via_registry_outside_derivatives_dir(tmp_path):
    """Manifest at /<elsewhere>/sub-AN/preproc_manifest.json should be
    discovered as long as a completed preproc run on the registry
    points its output_dir at <elsewhere>."""
    elsewhere = tmp_path / "testing" / "study" / "derivatives" / "fmriprep"
    elsewhere.mkdir(parents=True)
    manifest_path = _write_manifest(elsewhere, "AN")

    registry = RunRegistry(root=tmp_path / "runs")
    state = RunStateFile(
        run_id="preproc_AN_xyz",
        kind="preproc",
        backend="fmriprep",
        subject="AN",
        status="done",
        params={"output_dir": str(elsewhere)},
        manifest_path=str(manifest_path),
    )
    registry.register(state)
    registry.update(state)

    derivatives = tmp_path / "configured-derivatives"  # empty — manifest isn't under here
    derivatives.mkdir()
    mgr = PreprocManager(derivatives, registry=registry)
    summaries = mgr.scan_manifests()
    paths = [s["path"] for s in summaries]
    assert str(manifest_path.resolve()) in paths
    assert summaries[0]["subject"] == "AN"


def test_dedups_when_manifest_appears_in_both_sources(tmp_path):
    derivatives = tmp_path / "derivatives"
    derivatives.mkdir()
    fmri_out = derivatives / "fmriprep"
    manifest_path = _write_manifest(fmri_out, "01")

    registry = RunRegistry(root=tmp_path / "runs")
    state = RunStateFile(
        run_id="preproc_01_xyz",
        kind="preproc",
        backend="fmriprep",
        subject="01",
        status="done",
        params={"output_dir": str(fmri_out)},
        manifest_path=str(manifest_path),
    )
    registry.register(state)
    registry.update(state)

    mgr = PreprocManager(derivatives, registry=registry)
    summaries = mgr.scan_manifests()
    assert len([s for s in summaries if s["subject"] == "01"]) == 1


def test_skips_runs_that_are_not_done(tmp_path):
    elsewhere = tmp_path / "testing"
    elsewhere.mkdir()
    manifest_path = _write_manifest(elsewhere, "02")
    registry = RunRegistry(root=tmp_path / "runs")
    state = RunStateFile(
        run_id="r1", kind="preproc", backend="fmriprep", subject="02",
        status="running",  # still in flight — manifest path may be stale
        params={"output_dir": str(elsewhere)},
        manifest_path=str(manifest_path),
    )
    registry.register(state)
    registry.update(state)

    derivatives = tmp_path / "configured-derivatives"
    derivatives.mkdir()
    mgr = PreprocManager(derivatives, registry=registry)
    summaries = mgr.scan_manifests()
    assert summaries == []


def test_falls_back_to_output_dir_when_manifest_path_missing(tmp_path):
    """A run state lacking ``manifest_path`` still finds the manifest
    by deriving ``{output_dir}/sub-{subject}/preproc_manifest.json``."""
    elsewhere = tmp_path / "testing"
    elsewhere.mkdir()
    _write_manifest(elsewhere, "03")

    registry = RunRegistry(root=tmp_path / "runs")
    state = RunStateFile(
        run_id="r3", kind="preproc", backend="fmriprep", subject="03",
        status="done",
        params={"output_dir": str(elsewhere)},
        manifest_path=None,  # not set
    )
    registry.register(state)
    registry.update(state)

    derivatives = tmp_path / "configured-derivatives"
    derivatives.mkdir()
    mgr = PreprocManager(derivatives, registry=registry)
    summaries = mgr.scan_manifests()
    assert len(summaries) == 1
    assert summaries[0]["subject"] == "03"
