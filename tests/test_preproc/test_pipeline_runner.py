"""PipelineRunner: a real nipype run of a small graph, caching, rerun_from, composites, manifest."""

from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
import pytest


nib = pytest.importorskip("nibabel")
nipype = pytest.importorskip("nipype")

from fmriflow.preproc.graph import Pipeline, PipelineEdge, PipelineNode, PipelineRunRequest  # noqa: E402
from fmriflow.preproc.node_registry import NodeRegistry  # noqa: E402
from fmriflow.preproc.pipeline_runner import PipelineRunner  # noqa: E402
from fmriflow.preproc.nodes._parked import PARKED_DIR  # noqa: E402


_FIXTURES = Path(__file__).parent / "fixtures"


def fixture_pipeline(name: str):
    """A test-only pipeline YAML under tests/test_preproc/fixtures/ (formerly a shipped template)."""
    return Pipeline.from_yaml((_FIXTURES / f"{name}.yaml").read_text())


@pytest.fixture(scope="module")
def registry():
    return NodeRegistry(include_parked=True, user_dirs=[PARKED_DIR]).discover()


@pytest.fixture
def derivatives(tmp_path):
    d = tmp_path / "deriv" / "sub-01" / "func"
    d.mkdir(parents=True)
    for r in (1, 2):
        nib.save(nib.Nifti1Image(np.random.rand(3, 3, 3, 4).astype("float32"), np.eye(4)),
                 d / f"sub-01_task-x_run-{r}_desc-preproc_bold.nii.gz")
        (d / f"sub-01_task-x_run-{r}_desc-confounds_timeseries.tsv").write_text(
            "trans_x\ttrans_y\ttrans_z\trot_x\trot_y\trot_z\n" + "\n".join("0.1\t0\t0\t0\t0\t0" for _ in range(4)) + "\n"
        )
    return tmp_path / "deriv"


def _request(tmp_path, derivatives, **kw):
    return PipelineRunRequest(subject="01", output_dir=str(tmp_path / "out"),
                              derivatives_dir=str(derivatives), **kw)


def test_template_runs_caches_and_reruns_from(registry, tmp_path, derivatives):
    pipeline = fixture_pipeline("derivatives_smooth_regress")
    events: list[dict] = []
    runner = PipelineRunner(registry, run_id="r1", event_sink=events.append,
                            events_path=tmp_path / "events.jsonl")
    result = runner.run(pipeline, _request(tmp_path, derivatives))
    assert result.status == "completed", result.errors
    assert {r.node_id: r.status for r in result.node_records} == {"source": "ok", "smooth": "ok", "regress": "ok"}

    kinds = [e["event"] for e in events]
    assert kinds[0] == "started" and kinds[-1] == "completed"
    node_events = [(e["event"], e["node"]) for e in events if e["event"].startswith("node_")]
    wf = events[0]["workflow"]
    assert ("node_start", f"{wf}.smooth") in node_events and ("node_done", f"{wf}.regress") in node_events

    m = result.manifest
    assert len(m.runs) == 2
    assert all("regressed" in r.output_file for r in m.runs)          # bold_from re-pointed the runs
    assert all(r.confounds_file for r in m.runs)                      # confounds_from kept
    assert [s.name for s in m.additional_steps] == ["smooth", "regress_confounds"]
    assert all(s.fingerprint for s in m.additional_steps)
    assert Path(m.output_dir).name == "regress"

    # Second run: every node is a cache hit.
    events.clear()
    result2 = PipelineRunner(registry, run_id="r1", event_sink=events.append).run(pipeline, _request(tmp_path, derivatives))
    assert {r.status for r in result2.node_records} == {"cached"}
    assert all(e.get("cached") for e in events if e["event"] == "node_done")

    # rerun_from smooth with a new fwhm: source cached, smooth + regress re-executed.
    req = _request(tmp_path, derivatives, rerun_from=["smooth"], params_override={"smooth": {"fwhm": 2.0}})
    result3 = PipelineRunner(registry, run_id="r1").run(pipeline, req)
    assert {r.node_id: r.status for r in result3.node_records} == {"source": "cached", "smooth": "ok", "regress": "ok"}


def test_use_cache_false_reruns_everything(registry, tmp_path, derivatives):
    pipeline = fixture_pipeline("derivatives_smooth_regress")
    PipelineRunner(registry, run_id="r2").run(pipeline, _request(tmp_path, derivatives))
    result = PipelineRunner(registry, run_id="r2").run(pipeline, _request(tmp_path, derivatives, use_cache=False))
    assert {r.status for r in result.node_records} == {"ok"}


def test_validation_errors_short_circuit(registry, tmp_path):
    pipeline = Pipeline(name="bad", nodes=[PipelineNode(id="a", type="nope")])
    result = PipelineRunner(registry).run(pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path)))
    assert result.status == "failed" and any("unknown node type" in e for e in result.errors)


def test_failed_node_is_reported(registry, tmp_path):
    pipeline = Pipeline(
        name="fails",
        nodes=[PipelineNode(id="sel", type="select", literal_inputs={"inlist": []})],
        manifest={},
    )
    events: list[dict] = []
    result = PipelineRunner(registry, run_id="r3", event_sink=events.append).run(
        pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path / "o")))
    assert result.status == "failed"
    assert next(r for r in result.node_records if r.node_id == "sel").status == "failed"
    assert "node_fail" in [e["event"] for e in events] and any(e.get("leaf") == "sel" for e in events if e["event"] == "node_fail")
    assert events[-1]["event"] == "failed"


def test_composite_node_is_embedded_and_wired(registry, tmp_path):
    """A user composite built from nipype utility nodes runs inside the pipeline graph."""
    nodes_dir = tmp_path / "nodes"
    nodes_dir.mkdir()
    (nodes_dir / "passthru.py").write_text(textwrap.dedent('''
        from fmriflow.preproc.node_registry import preproc_node

        @preproc_node("passthru_wf", kind="composite")
        class Passthru:
            INPUTS = ["a"]; OUTPUTS = ["b"]
            PARAM_SCHEMA = {}
            def validate(self, config): return []
            def build(self, config):
                from nipype import Node, Workflow
                from nipype.interfaces.utility import IdentityInterface, Function
                wf = Workflow(name="passthru")
                i = Node(IdentityInterface(fields=["a"]), name="inputnode")
                def _ident(x):
                    return x
                f = Node(Function(input_names=["x"], output_names=["y"], function=_ident), name="ident")
                o = Node(IdentityInterface(fields=["b"]), name="outputnode")
                wf.connect(i, "a", f, "x"); wf.connect(f, "y", o, "b")
                return wf
            def to_manifest(self, config, outputs): return None
    '''))
    reg = NodeRegistry(include_parked=True, user_dirs=[PARKED_DIR, nodes_dir]).discover()
    src = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 2), dtype="float32"), np.eye(4)), src)
    pipeline = Pipeline(
        name="comp",
        nodes=[
            PipelineNode(id="ident", type="identity", literal_inputs={"in_file": str(src)}),
            PipelineNode(id="wf", type="passthru_wf", kind="composite"),
            PipelineNode(id="sm", type="smooth", params={"fwhm": 1.0}),
        ],
        edges=[
            PipelineEdge(id="e1", source="ident", target="wf", source_handle="out_file", target_handle="a"),
            PipelineEdge(id="e2", source="wf", target="sm", source_handle="b", target_handle="in_file"),
        ],
        manifest={"backend_node": "wf", "bold_from": "sm.out_file"},
    )
    result = PipelineRunner(reg, run_id="r4").run(pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path / "o")))
    assert result.status == "completed", result.errors
    rec = {r.node_id: r for r in result.node_records}
    assert rec["wf"].status == "ok" and rec["wf"].outputs.get("b", "").endswith("in.nii.gz")
    assert rec["sm"].status == "ok"
    assert len(result.manifest.runs) == 1 and "smooth" in result.manifest.runs[0].output_file


def test_iter_on_composite_is_rejected(registry, tmp_path):
    pipeline = fixture_pipeline("reference_nipype")
    pipeline.node("ref").iter = {"handle": "bold"}
    errors = PipelineRunner(registry).validate(pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path), bids_dir=str(tmp_path)))
    assert any("iter is not supported on composite" in e for e in errors)
