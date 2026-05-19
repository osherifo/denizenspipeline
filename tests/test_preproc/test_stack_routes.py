"""Phase 5 — FastAPI route integration tests for the stack endpoints.

Goes through the public HTTP surface:

- ``GET /api/preproc/backends/workflows`` lists every registered
  workflow with source + version + requirements.
- ``GET .../workflows/{name}/preflight`` returns ``ok=True`` for
  the no-requirement built-ins, ``ok=False`` with descriptive
  errors when a workflow has missing tools.
- ``POST /api/preproc/stack/run`` launches a detached run; the
  response carries the new ``run_id``.
- The route polls finish in milliseconds for the identity stack;
  the test waits up to 30s before failing.
- ``GET .../status/{run_id}`` returns the final manifest payload.
- ``GET .../manifest/{run_id}`` returns the on-disk manifest.

The tests **actually spawn subprocesses** (no mocking) — the
identity workflow + identity transform finish in <1s so a
poll-and-wait pattern is acceptable. This is also the most honest
test of the integration since it exercises the same code path
production will.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fmriflow.server.services.run_registry import RunRegistry
from fmriflow.server.services.stack_manager import StackManager


@pytest.fixture
def app(tmp_path):
    """A FastAPI app with the stack manager pinned to a tmp registry,
    so test runs don't pollute the developer's real ``~/.fmriflow/runs/``."""
    from fmriflow.server.app import create_app

    app = create_app(derivatives_dir=str(tmp_path / "derivatives"))

    # Override stack_manager so it writes runs under tmp_path.
    test_registry = RunRegistry(root=tmp_path / "runs")
    app.state.stack_manager = StackManager(run_registry=test_registry)

    # Stash so individual tests can poke at it.
    app.state._test_registry_root = tmp_path / "runs"
    app.state._test_output_root = tmp_path / "out"
    return app


def _poll_until_done(client, run_id, timeout_s: float = 30.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(f"/api/preproc/stack/{run_id}/status")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("done", "failed", "lost"):
            return body
        time.sleep(0.1)
    raise TimeoutError(f"Run {run_id} never completed within {timeout_s}s")


# ── Backend listings ──────────────────────────────────────────────


class TestWorkflowListing:
    def test_lists_built_in_workflows(self, app):
        c = TestClient(app)
        r = c.get("/api/preproc/backends/workflows")
        assert r.status_code == 200
        names = [w["name"] for w in r.json()["workflows"]]
        # Identity placeholder + the three wrappers + passthrough.
        for expected in ("identity", "fmriprep", "custom", "bids_app", "passthrough"):
            assert expected in names, f"missing workflow: {expected}"

    def test_workflow_info_carries_source_and_version(self, app):
        c = TestClient(app)
        workflows = c.get("/api/preproc/backends/workflows").json()["workflows"]
        identity = next(w for w in workflows if w["name"] == "identity")
        assert identity["source"] == "built-in"
        assert identity["version"] == "0.1.0"
        assert identity["container_bound"] is False
        assert identity["required_python"] == []

    def test_workflow_preflight_clean(self, app):
        c = TestClient(app)
        r = c.get("/api/preproc/backends/workflows/identity/preflight")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["errors"] == []

    def test_workflow_preflight_unknown_404(self, app):
        c = TestClient(app)
        r = c.get("/api/preproc/backends/workflows/ghost/preflight")
        assert r.status_code == 404


class TestTransformListing:
    def test_lists_built_in_transforms(self, app):
        c = TestClient(app)
        names = [t["name"] for t in c.get("/api/preproc/backends/transforms").json()["transforms"]]
        assert "identity" in names

    def test_transform_preflight_clean(self, app):
        c = TestClient(app)
        r = c.get("/api/preproc/backends/transforms/identity/preflight")
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ── Stack-run lifecycle ───────────────────────────────────────────


class TestStackRunLifecycle:
    def test_launch_returns_run_id(self, app):
        c = TestClient(app)
        r = c.post(
            "/api/preproc/stack/run",
            json={
                "stack": {
                    "bootstrap": {"kind": "nipype", "workflow": "identity"},
                    "transforms": [{"name": "identity"}],
                },
                "subject": "sub01",
                "output_dir": str(app.state._test_output_root),
                "sessions": ["ses01"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["run_id"].startswith("stack_")
        assert body["status"] == "running"

    def test_run_completes_and_status_reports_done(self, app):
        c = TestClient(app)
        run_id = c.post(
            "/api/preproc/stack/run",
            json={
                "stack": {
                    "bootstrap": {"kind": "nipype", "workflow": "identity"},
                    "transforms": [{"name": "identity"}],
                },
                "subject": "sub01",
                "output_dir": str(app.state._test_output_root),
            },
        ).json()["run_id"]

        final = _poll_until_done(c, run_id)
        assert final["status"] == "done", final
        assert final["result"]["n_stages"] == 2
        assert final["result"]["bootstrap_fingerprint"]
        assert len(final["result"]["stage_manifests"]) == 2

    def test_manifest_endpoint_returns_json(self, app):
        c = TestClient(app)
        run_id = c.post(
            "/api/preproc/stack/run",
            json={
                "stack": {
                    "bootstrap": {"kind": "nipype", "workflow": "identity"},
                    "transforms": [],
                },
                "subject": "sub01",
                "output_dir": str(app.state._test_output_root),
            },
        ).json()["run_id"]

        _poll_until_done(c, run_id)

        m = c.get(f"/api/preproc/stack/{run_id}/manifest")
        assert m.status_code == 200
        manifest = m.json()
        assert manifest["subject"] == "sub01"
        assert manifest["backend"] == "nipype"

    def test_manifest_409_when_run_unfinished(self, app, tmp_path):
        # Simulate an in-flight (or interrupted) run by registering
        # state manually, no spawn. Without a live pid the manager
        # reports the run as ``lost``, but either way the manifest
        # endpoint should return 409 because no manifest is on disk.
        from fmriflow.server.services.run_registry import RunStateFile
        registry = app.state.stack_manager.registry
        registry.register(RunStateFile(
            run_id="stack_pending",
            kind="stack",
            backend="nipype",
            subject="sub01",
            status="running",
        ))
        c = TestClient(app)
        r = c.get("/api/preproc/stack/stack_pending/manifest")
        assert r.status_code == 409
        # Status should be something non-"done"; exact value depends on
        # whether the reconciler considers it running or lost.
        assert "status:" in r.json()["detail"]

    def test_unknown_run_404(self, app):
        c = TestClient(app)
        assert c.get("/api/preproc/stack/never_existed/status").status_code == 404
        assert c.get("/api/preproc/stack/never_existed/manifest").status_code == 404

    def test_invalid_stack_returns_400(self, app):
        c = TestClient(app)
        r = c.post(
            "/api/preproc/stack/run",
            json={
                "stack": {"transforms": []},  # missing bootstrap
                "subject": "sub01",
                "output_dir": str(app.state._test_output_root),
            },
        )
        assert r.status_code == 400

    def test_missing_subject_returns_400(self, app):
        c = TestClient(app)
        r = c.post(
            "/api/preproc/stack/run",
            json={
                "stack": {
                    "bootstrap": {"kind": "nipype", "workflow": "identity"},
                    "transforms": [],
                },
                "subject": "",
                "output_dir": str(app.state._test_output_root),
            },
        )
        assert r.status_code == 400

    def test_list_runs_includes_launched(self, app):
        c = TestClient(app)
        run_id = c.post(
            "/api/preproc/stack/run",
            json={
                "stack": {
                    "bootstrap": {"kind": "nipype", "workflow": "identity"},
                    "transforms": [],
                },
                "subject": "sub01",
                "output_dir": str(app.state._test_output_root),
            },
        ).json()["run_id"]

        # Don't even wait — the run might still be running.
        runs = c.get("/api/preproc/stack/runs").json()["runs"]
        ids = [r["run_id"] for r in runs]
        assert run_id in ids
