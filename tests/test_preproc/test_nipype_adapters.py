"""run() nodes wrapped as nipype interfaces, executed by a real nipype Workflow."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")
nipype = pytest.importorskip("nipype")

from nipype import Node, Workflow  # noqa: E402

from fmriflow.preproc.graph import Pipeline  # noqa: E402
from fmriflow.preproc.manifest import PreprocManifest, RunRecord, now_iso  # noqa: E402
from fmriflow.preproc.nipype_adapters import (  # noqa: E402
    RunNodeInterface,
    build_composite,
    composite_ports,
    make_interface,
)
from fmriflow.preproc.node_registry import NodeRegistry  # noqa: E402
from fmriflow.preproc.nodes._parked import PARKED_DIR  # noqa: E402


@pytest.fixture(scope="module")
def registry():
    return NodeRegistry(include_parked=True, user_dirs=[PARKED_DIR]).discover()


@pytest.fixture
def nifti(tmp_path):
    p = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(np.random.rand(4, 4, 4, 3).astype("float32"), np.eye(4)), p)
    return p


def _wf(tmp_path, name="t"):
    wf = Workflow(name=name, base_dir=str(tmp_path / "work"))
    wf.config["execution"]["crashdump_dir"] = str(tmp_path / "crash")
    return wf


def _run(wf, events):
    return wf.run(
        plugin="Linear",
        plugin_args={"status_callback": lambda node, status: events.append((node.name, status))},
    )


def test_interface_exposes_ports_and_params(registry):
    iface = make_interface(registry.cls("mask_apply"), params={"mask_path": ""})
    assert isinstance(iface, RunNodeInterface)
    assert set(iface.inputs.copyable_trait_names()) >= {"in_file", "mask_file", "params", "node_type"}
    assert "out_file" in iface._outputs().copyable_trait_names()


def test_not_a_run_node_is_rejected():
    class NoRun:
        pass
    with pytest.raises(TypeError):
        make_interface(NoRun)


def test_two_node_chain_runs_and_caches(registry, tmp_path, nifti):
    n1 = Node(make_interface(registry.cls("identity"), in_file=str(nifti)), name="ident")
    n2 = Node(make_interface(registry.cls("smooth"), params={"fwhm": 2.0}), name="smooth")
    wf = _wf(tmp_path)
    wf.connect(n1, "out_file", n2, "in_file")

    events: list = []
    res = _run(wf, events)
    assert [e for e in events if e[1] == "end"] == [("ident", "end"), ("smooth", "end")]
    out = next(n for n in res.nodes() if n.name == "smooth").result.outputs.out_file
    assert Path(out).exists()

    # Same inputs -> nipype cache hit, the work dir is untouched.
    mtime = Path(out).stat().st_mtime
    _run(wf, [])
    assert Path(out).stat().st_mtime == mtime

    # Changed params -> only smooth reruns (its hash changed).
    n2.inputs.params = {"fwhm": 3.0}
    res2 = _run(wf, [])
    out2 = next(n for n in res2.nodes() if n.name == "smooth").result.outputs.out_file
    assert out2 != out or Path(out2).stat().st_mtime > mtime


def test_manifest_source_emits_run_files(registry, tmp_path, nifti):
    conf = tmp_path / "conf.tsv"
    conf.write_text("trans_x\n0\n0\n0\n")
    manifest = PreprocManifest(
        subject="01", dataset="d", sessions=[],
        runs=[RunRecord(run_name="r1", source_file="s", output_file=nifti.name, n_trs=3,
                        shape=[4, 4, 4, 3], confounds_file=conf.name)],
        backend="test", backend_version="0", parameters={}, space="native",
        output_dir=str(tmp_path),
    )
    mpath = tmp_path / "preproc_manifest.json"
    mpath.write_text(json.dumps(manifest.to_dict()))
    iface = make_interface(registry.cls("manifest_source"), params={"run_name": "r1"}, manifest=str(mpath))
    res = iface.run()
    assert res.outputs.bold == str(nifti)
    assert res.outputs.confounds == str(conf)


def test_derivatives_source_globs(registry, tmp_path, nifti):
    d = tmp_path / "deriv" / "sub-01" / "func"
    d.mkdir(parents=True)
    target = d / "sub-01_task-x_desc-preproc_bold.nii.gz"
    target.write_bytes(nifti.read_bytes())
    iface = make_interface(
        registry.cls("derivatives_source"),
        params={"confounds_pattern": ""},
        derivatives_dir=str(tmp_path / "deriv"), subject="01",
    )
    res = iface.run()
    assert res.outputs.bold == [str(target)]


def test_composite_contract(registry):
    """A composite that builds nothing returns None; ports come from inputnode/outputnode."""
    class NoOp:
        def validate(self, config): return []
        def build(self, config): return None
    assert build_composite(NoOp, object()) is None

    from nipype.interfaces.utility import IdentityInterface
    wf = Workflow(name="c")
    inn = Node(IdentityInterface(fields=["a", "b"]), name="inputnode")
    out = Node(IdentityInterface(fields=["z"]), name="outputnode")
    wf.connect(inn, "a", out, "z")
    assert composite_ports(wf) == (["a", "b"], ["z"])
