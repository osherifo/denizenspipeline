"""The `nipype` backend — registered workflows reachable as a preproc stage.

Registered nipype workflows were only reachable through the PreprocStack API.
Workflow *stages* dispatch on ``preproc.backend`` through the legacy backend
registry, so a workflow YAML could not name one at all. This bridge closes
that, and these tests pin the contract in both directions: what it accepts,
and what it refuses clearly.
"""

from types import SimpleNamespace

import pytest

from fmriflow.preproc.backends import get_backend, list_backends
from fmriflow.preproc.errors import BackendRunError
from fmriflow.preproc.manifest import PreprocConfig


def _config(output_dir="/tmp/out", bids_dir="/tmp/bids", **params):
    """Config helper.

    `output_dir` and `bids_dir` are explicit: an earlier version funnelled
    every kwarg into backend_params, so `_config(output_dir=tmp_path)` quietly
    set a *backend param* named output_dir and left the real one pointing at
    /tmp/out — misleading, and a test-isolation hazard the moment the helper
    is used with .run().
    """
    return PreprocConfig(
        subject="01", backend="nipype", output_dir=str(output_dir),
        bids_dir=str(bids_dir), backend_params=params,
    )


# ── registration ────────────────────────────────────────────────────


def test_nipype_is_a_registered_backend():
    """Without this, `backend: nipype` in a workflow YAML is unresolvable."""
    assert "nipype" in list_backends()
    assert get_backend("nipype").name == "nipype"


# ── refusals, with actionable messages ──────────────────────────────


def test_requires_a_workflow_name(tmp_path):
    errors = get_backend("nipype").validate(_config())

    assert errors
    # The message must list what IS available; "missing parameter" alone
    # leaves the reader to go source-diving for valid values.
    assert "backend_params.workflow" in errors[0]
    assert "identity" in errors[0]


def test_unknown_workflow_names_the_alternatives(tmp_path):
    errors = get_backend("nipype").validate(_config(workflow="does-not-exist"))

    assert "unknown nipype workflow" in errors[0]
    assert "identity" in errors[0]


def test_run_refuses_a_config_the_workflow_rejects(monkeypatch, tmp_path):
    """A workflow's own validate() is authoritative and must block the run."""
    backend = get_backend("nipype")

    class Rejecting:
        name = "rejecting"
        version = "0"

        def validate(self, config):
            return ["nope, bad config"]

        def build(self, config):
            raise AssertionError("build must not be reached")

        def to_manifest(self, config, outputs):
            raise AssertionError("to_manifest must not be reached")

    monkeypatch.setattr(
        "fmriflow.preproc.backends.nipype_bridge._resolve",
        lambda config: (Rejecting(), {}),
    )

    with pytest.raises(BackendRunError, match="nope, bad config"):
        backend.run(_config(output_dir=tmp_path, workflow="rejecting"))


def test_run_refuses_an_unrunnable_build_result(monkeypatch, tmp_path):
    backend = get_backend("nipype")

    class Bogus:
        name = "bogus"
        version = "0"

        def validate(self, config):
            return []

        def build(self, config):
            return "not a workflow"       # neither None nor runnable

        def to_manifest(self, config, outputs):
            raise AssertionError("must not be reached")

    monkeypatch.setattr(
        "fmriflow.preproc.backends.nipype_bridge._resolve",
        lambda config: (Bogus(), {}),
    )

    with pytest.raises(BackendRunError, match="not runnable"):
        backend.run(PreprocConfig(
            subject="01", backend="nipype", output_dir=str(tmp_path),
            backend_params={"workflow": "bogus"},
        ))


# ── the happy paths ─────────────────────────────────────────────────


def test_a_workflow_returning_none_still_produces_a_manifest(tmp_path):
    """`identity` builds nothing; the stage must still complete."""
    backend = get_backend("nipype")

    manifest = backend.run(PreprocConfig(
        subject="01", backend="nipype", output_dir=str(tmp_path),
        backend_params={"workflow": "identity"},
    ))

    assert manifest.subject == "01"
    assert manifest.backend == "nipype"


def test_a_real_workflow_is_executed(monkeypatch, tmp_path):
    """Anything runnable gets run — this path used to raise NotImplementedError."""
    backend = get_backend("nipype")
    ran = {}

    class FakeFlow:
        name = "fake"

        def run(self, plugin=None):
            ran["plugin"] = plugin
            return "result"

    class Runs:
        name = "runs"
        version = "1"

        def validate(self, config):
            return []

        def build(self, config):
            return FakeFlow()

        def to_manifest(self, config, outputs):
            ran["outputs"] = outputs
            from fmriflow.preproc.manifest import PreprocManifest, now_iso
            return PreprocManifest(
                subject=config.subject, dataset="t", sessions=[], runs=[],
                backend="nipype", backend_version="1", parameters={},
                space="native", output_dir=config.output_dir, created=now_iso(),
            )

    monkeypatch.setattr(
        "fmriflow.preproc.backends.nipype_bridge._resolve",
        lambda config: (Runs(), {}),
    )

    backend.run(PreprocConfig(
        subject="01", backend="nipype", output_dir=str(tmp_path),
        backend_params={"workflow": "runs"},
    ))

    # Linear: these already run inside a job sized by the caller, so a
    # parallel plugin here would fight it for cores.
    assert ran["plugin"] == "Linear"
    assert "nipype_result" in ran["outputs"]


def test_output_dir_is_created_before_the_workflow_runs(tmp_path):
    out = tmp_path / "not" / "yet" / "there"

    get_backend("nipype").run(PreprocConfig(
        subject="01", backend="nipype", output_dir=str(out),
        backend_params={"workflow": "identity"},
    ))

    assert out.is_dir()


def test_params_reach_the_workflow_without_the_selector(monkeypatch, tmp_path):
    """`workflow` selects; everything else is the workflow's own config."""
    seen = {}

    class Capturing:
        name = "cap"
        version = "1"

        def validate(self, config):
            seen["params"] = dict(config.backend_params)
            return ["stop here"]

        def build(self, config):
            raise AssertionError

        def to_manifest(self, config, outputs):
            raise AssertionError

    import fmriflow.preproc.backends.nipype_bridge as bridge
    monkeypatch.setattr(bridge, "_registry", lambda: SimpleNamespace(
        list=lambda: [SimpleNamespace(name="cap")],
        get=lambda name: Capturing(),
    ))

    get_backend("nipype").validate(_config(workflow="cap", method="soft", beta=100))

    assert seen["params"] == {"method": "soft", "beta": 100}
    assert "workflow" not in seen["params"]


# ── manifest labelling and status ───────────────────────────────────


def test_dataset_is_not_taken_from_the_task_filter(tmp_path):
    """`task` is a BIDS filter; `dataset` is the run-group label.

    Conflating them mislabels manifest.dataset for anything that queries it —
    identity.py carries the same warning.
    """
    from fmriflow.preproc.backends.nipype_bridge import _WorkflowCallConfig

    config = PreprocConfig(
        subject="01", backend="nipype", output_dir=str(tmp_path),
        task="story", backend_params={},
    )

    assert _WorkflowCallConfig(config, {}).dataset == "unknown"
    assert _WorkflowCallConfig(config, {}).task == "story"


def test_dataset_comes_from_backend_params_when_given(tmp_path):
    from fmriflow.preproc.backends.nipype_bridge import _WorkflowCallConfig

    config = PreprocConfig(
        subject="01", backend="nipype", output_dir=str(tmp_path),
        task="story", backend_params={},
    )
    call = _WorkflowCallConfig(config, {"dataset": "reading_en", "method": "soft"})

    assert call.dataset == "reading_en"
    # ...and it is consumed, not passed on as a workflow param.
    assert call.backend_params == {"method": "soft"}


def test_the_callers_params_are_not_mutated(tmp_path):
    from fmriflow.preproc.backends.nipype_bridge import _WorkflowCallConfig

    params = {"dataset": "x", "method": "soft"}
    _WorkflowCallConfig(_config(output_dir=tmp_path), params)

    assert params == {"dataset": "x", "method": "soft"}


def test_status_does_not_call_an_empty_output_dir_completed(tmp_path):
    """run() creates output_dir before executing, so existence proves nothing."""
    backend = get_backend("nipype")
    config = _config(output_dir=tmp_path / "out", workflow="identity")

    assert backend.status(config).status == "pending"

    (tmp_path / "out").mkdir()
    assert backend.status(config).status == "running"

    (tmp_path / "out" / "sub-01_T1w.nii.gz").write_bytes(b"x")
    assert backend.status(config).status == "completed"
