"""container_app nodes: command parity with the old backends, and real execution
through ContainerAppInterface."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

nipype = pytest.importorskip("nipype")

from fmriflow.preproc.backends.fmriprep import FmriprepBackend  # noqa: E402
from fmriflow.preproc.backends.fmriprep_params import FmriprepParams  # noqa: E402
from fmriflow.preproc.manifest import PreprocConfig  # noqa: E402
from fmriflow.preproc.nipype_adapters import make_container_interface  # noqa: E402
from fmriflow.preproc.node_registry import NodeRegistry, preproc_node  # noqa: E402
from fmriflow.preproc.nodes.bids_app import BidsAppNode  # noqa: E402
from fmriflow.preproc.nodes.custom_shell import CustomShellNode  # noqa: E402
from fmriflow.preproc.nodes.fmriprep import FmriprepNode  # noqa: E402


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    for d in ("bids", "out", "work"):
        (tmp_path / d).mkdir()
    (tmp_path / "bids" / "sub-01").mkdir()
    return {"bids_dir": str(tmp_path / "bids"), "subject": "01",
            "output_dir": str(tmp_path / "out"), "work_dir": str(tmp_path / "work")}


@pytest.mark.parametrize("mode", ["full", "anat_only", "func_only"])
def test_fmriprep_command_matches_old_backend_bare(dirs, tmp_path, mode):
    params = {"mode": mode, "output_spaces": ["T1w", "MNI152NLin2009cAsym:res-2"], "nthreads": 4}
    new = FmriprepNode().build_command(dirs, params, tmp_path)
    cfg = PreprocConfig(subject="01", backend="fmriprep", output_dir=dirs["output_dir"],
                        bids_dir=dirs["bids_dir"], work_dir=dirs["work_dir"],
                        backend_params={**params, "container_type": "bare"})
    old = FmriprepBackend()._build_command(cfg, FmriprepParams.from_dict(cfg.backend_params))
    assert new == old
    assert new[0] == "fmriprep" and new[1] == dirs["bids_dir"]


def test_fmriprep_precomputed_anat_passes_subjects_dir_through(dirs, tmp_path):
    cmd = FmriprepNode().build_command({**dirs, "fs_subjects_dir": "/host/fs"},
                                       {"mode": "func_precomputed_anat"}, tmp_path)
    assert cmd[cmd.index("--fs-subjects-dir") + 1] == "/host/fs"


def test_fmriprep_ignores_container_params_from_older_pipelines(dirs, tmp_path):
    """A pipeline saved when container/container_type existed still builds a bare command."""
    cmd = FmriprepNode().build_command(dirs, {"mode": "anat_only", "container": "nipreps/fmriprep:24.1.1",
                                              "container_type": "docker"}, tmp_path)
    assert cmd[0] == "fmriprep" and "docker" not in cmd


def test_fmriprep_validate_reports_missing_bids_and_binary(tmp_path, monkeypatch):
    import fmriflow.preproc.nodes.fmriprep as fp
    monkeypatch.setattr(fp.shutil, "which", lambda name: None)
    errors = FmriprepNode().validate({"bids_dir": str(tmp_path / "nope"), "subject": "01"}, {})
    assert any("BIDS directory not found" in e for e in errors)
    assert any("fmriprep is not on PATH" in e for e in errors)


def test_fmriprep_schema_is_grouped():
    groups = {f.get("group") for f in FmriprepNode.PARAM_SCHEMA.values()}
    assert {"Mode", "Anatomical", "Functional", "Fieldmaps", "Output", "Denoising", "Resources"} <= groups


def test_bids_app_command_runs_the_executable_bare(dirs, tmp_path):
    cmd = BidsAppNode().build_command(dirs, {"command": "/usr/bin/myapp", "extra_args": ["--foo"]}, tmp_path)
    assert cmd[:3] == ["/usr/bin/myapp", dirs["bids_dir"], dirs["output_dir"]]
    assert cmd[3:8] == ["participant", "--participant-label", "01", "-w", dirs["work_dir"]]
    assert cmd[-1] == "--foo"
    # the pre-bare-only spelling still resolves
    assert BidsAppNode().build_command(dirs, {"container": "/usr/bin/myapp"}, tmp_path)[0] == "/usr/bin/myapp"
    errs = BidsAppNode().validate(dirs, {"command": "/no/such/app"})
    assert any("command not found" in e for e in errs)


def test_custom_shell_render_and_validate(tmp_path):
    node = CustomShellNode()
    inputs = {"subject": "01", "input_dir": "/in", "output_dir": str(tmp_path / "o")}
    cmd = node.render(inputs, {"command": "tool {input_dir} {output_dir} --sub {subject}"}, tmp_path)
    assert cmd == f"tool /in {tmp_path / 'o'} --sub 01"
    assert node.validate(inputs, {"command": "x {bogus}"})
    assert node.validate(inputs, {"command": ""})


def test_custom_shell_runs_through_the_interface(tmp_path):
    out = tmp_path / "o"
    iface = make_container_interface(
        CustomShellNode,
        params={"command": "mkdir -p {output_dir} && cp %s {output_dir}/sub-{subject}_bold.nii.gz"
                % _tiny_nifti(tmp_path), "file_pattern": "*.nii.gz"},
        subject="01", output_dir=str(out),
    )
    (tmp_path / "node").mkdir()
    res = iface.run(cwd=str(tmp_path / "node"))
    assert res.outputs.files == [str(out / "sub-01_bold.nii.gz")]
    assert Path(res.outputs.manifest).exists()
    assert (tmp_path / "node" / "stdout.log").exists()


def test_failed_command_raises_with_log_tail(tmp_path):
    iface = make_container_interface(CustomShellNode, params={"command": "echo boom; exit 7"})
    (tmp_path / "node").mkdir()
    with pytest.raises(RuntimeError, match="code 7"):
        iface.run(cwd=str(tmp_path / "node"))


def test_inner_nipype_log_is_parsed_under_the_node_path(tmp_path):
    @preproc_node("_fake_fmriprep", kind="container_app")
    class FakeApp:
        INNER_NIPYPE_LOG = True
        INPUTS: list[str] = []
        OUTPUTS = ["done"]

        def build_command(self, inputs, params, out_dir):
            return (
                "printf '%s\\n' "
                "'260101-10:00:00,000 nipype.workflow INFO:' "
                "'\t [Node] Setting-up \"fmriprep_wf.anat.recon\" in \"/w\".' "
                "'260101-10:00:01,000 nipype.workflow INFO:' "
                "'\t [Node] Finished \"fmriprep_wf.anat.recon\", elapsed time 1s.'"
            )

        def collect(self, inputs, params, out_dir):
            return {"done": "yes"}

    events = tmp_path / "events.jsonl"
    iface = make_container_interface(FakeApp, events_path=str(events), node_path="run1.fp")
    (tmp_path / "node").mkdir()
    iface.run(cwd=str(tmp_path / "node"))
    import json
    evs = [json.loads(l) for l in events.read_text().splitlines()]
    kinds = [(e["event"], e["node"]) for e in evs]
    assert ("node_start", "run1.fp.fmriprep_wf.anat.recon") in kinds
    assert ("node_done", "run1.fp.fmriprep_wf.anat.recon") in kinds
    assert all(e["inner"] for e in evs)


def _tiny_nifti(tmp_path: Path) -> Path:
    import nibabel as nib
    import numpy as np
    p = tmp_path / "tiny.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 2), dtype="float32"), np.eye(4)), p)
    return p


def test_registry_lists_the_three_container_apps():
    reg = NodeRegistry(user_dirs=[]).discover()
    assert {"fmriprep", "bids_app", "custom_shell"} <= set(reg.names())
    assert all(reg.kind(n) == "container_app" for n in ("fmriprep", "bids_app", "custom_shell"))


def test_fmriprep_validate_accepts_fs_subjects_dir_on_the_input_port(tmp_path):
    """func_precomputed_anat takes the FreeSurfer dir from the port when the param is empty."""
    from fmriflow.preproc.nodes.fmriprep import FmriprepNode
    bids = tmp_path / "bids"; bids.mkdir()
    fs = tmp_path / "fs"; fs.mkdir()
    params = {"mode": "func_precomputed_anat"}
    errs = FmriprepNode().validate({"bids_dir": str(bids), "subject": "01", "fs_subjects_dir": str(fs)}, params)
    assert not any("requires fs_subjects_dir" in e for e in errs), errs
    errs = FmriprepNode().validate({"bids_dir": str(bids), "subject": "01", "fs_subjects_dir": str(tmp_path / "missing")}, params)
    assert any("fs_subjects_dir not found" in e for e in errs), errs
