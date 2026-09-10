"""PreprocOutputs: manifests over HTTP and collect via the node collectors."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

nib = pytest.importorskip("nibabel")

from fmriflow.server.services.preproc_outputs import collect_manifest  # noqa: E402


def test_collect_custom_and_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    out = tmp_path / "deriv"
    (out / "sub-01").mkdir(parents=True)
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 3), dtype="float32"), np.eye(4)), out / "sub-01" / "run1_bold.nii.gz")
    m = collect_manifest({"backend": "custom", "subject": "01", "output_dir": str(out), "backend_params": {"file_pattern": "*_bold.nii.gz"}})
    assert len(m.runs) == 1 and (out / "sub-01" / "preproc_manifest.json").is_file()

    from fmriflow.server.app import create_app
    client = TestClient(create_app(derivatives_dir=str(out)))
    listing = client.get("/api/preproc/manifests").json()["manifests"]
    assert [x["subject"] for x in listing] == ["01"]
    assert client.get("/api/preproc/manifests/01").json()["subject"] == "01"
    assert client.get("/api/preproc/manifests/zz").status_code == 404
    assert client.post("/api/preproc/manifests/01/validate").json()["errors"] is not None
    r = client.post("/api/preproc/collect", json={"backend": "custom", "subject": "01", "output_dir": str(out), "backend_params": {"file_pattern": "*_bold.nii.gz"}})
    assert r.status_code == 200 and r.json()["n_runs"] == 1
    assert client.post("/api/preproc/collect", json={"backend": "nope", "subject": "01", "output_dir": str(out)}).status_code == 400
    assert client.get("/api/preproc/label-map?version=25").status_code in (200, 404)
    # The legacy run surface is gone; pipeline runs own /preproc/runs.
    runs = client.get("/api/preproc/runs").json()["runs"]
    assert isinstance(runs, list) and all("checkpoints" in r for r in runs)
