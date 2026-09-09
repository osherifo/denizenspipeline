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
    monkeypatch.setenv("FMRIFLOW_SINGULARITY_BIN", "/bin/true")
    return {"bids_dir": str(tmp_path / "bids"), "subject": "01",
            "output_dir": str(tmp_path / "out"), "work_dir": str(tmp_path / "work")}


@pytest.mark.parametrize("ctype,container", [
    ("docker", "nipreps/fmriprep:24.1.1"),
    ("apptainer", "/img/fp.sif"),
    ("bare", ""),
])
@pytest.mark.parametrize("mode", ["full", "anat_only", "func_only"])
def test_fmriprep_command_matches_old_backend(dirs, tmp_path, ctype, container, mode):
    params = {"mode": mode, "container": container, "container_type": ctype,
              "output_spaces": ["T1w", "MNI152NLin2009cAsym:res-2"], "nthreads": 4}
    new = FmriprepNode().build_command(dirs, params, tmp_path)
    cfg = PreprocConfig(subject="01", backend="fmriprep", output_dir=dirs["output_dir"],
                        bids_dir=dirs["bids_dir"], work_dir=dirs["work_dir"],
                        backend_params={k: v for k, v in params.items() if v not in ("", None)})
    old = FmriprepBackend()._build_command(cfg, FmriprepParams.from_dict(cfg.backend_params))
    assert new == old


def test_fmriprep_precomputed_anat_binds_subjects_dir_into_container(dirs, tmp_path):
    """The old backend passed a host path into the container; the node binds it."""
    params = {"mode": "func_precomputed_anat", "container": "nipreps/fmriprep:24.1.1",
              "container_type": "docker"}
    cmd = FmriprepNode().build_command({**dirs, "fs_subjects_dir": "/host/fs"}, params, tmp_path)
    assert "-v" in cmd and "/host/fs:/fs_subjects" in cmd
    assert cmd[cmd.index("--fs-subjects-dir") + 1] == "/fs_subjects"


def test_fmriprep_validate_reports_missing_bids_and_runtime(tmp_path):
    errors = FmriprepNode().validate({"bids_dir": str(tmp_path / "nope"), "subject": "01"},
                                     {"container": "/no/such.sif", "container_type": "apptainer"})
    assert any("BIDS directory not found" in e for e in errors)


def test_fmriprep_schema_is_grouped():
    groups = {f.get("group") for f in FmriprepNode.PARAM_SCHEMA.values()}
    assert {"Mode", "Anatomical", "Functional", "Fieldmaps", "Output", "Denoising", "Resources"} <= groups


def test_bids_app_commands(dirs, tmp_path):
    docker = BidsAppNode().build_command(dirs, {"container": "img:1", "container_type": "docker",
                                                "extra_args": ["--foo"]}, tmp_path)
    assert docker[:3] == ["docker", "run", "--rm"]
    assert docker[-6:] == ["/data", "/out", "participant", "--participant-label", "01", "--foo"]
    bare = BidsAppNode().build_command(dirs, {"container": "/usr/bin/myapp", "container_type": "bare"}, tmp_path)
    assert bare[:2] == ["/usr/bin/myapp", dirs["bids_dir"]]


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
