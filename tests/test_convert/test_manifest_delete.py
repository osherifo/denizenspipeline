"""DELETE /api/convert/manifests/{subject} removes the manifest file only."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _manifest(subject, bids_dir):
    return {
        "subject": subject, "dataset": "d", "sessions": [], "runs": [{
            "run_name": "", "task": "", "session": "", "source_series": "",
            "output_file": f"sub-{subject}/anat/sub-{subject}_T1w.nii.gz", "sidecar_file": "",
            "n_volumes": 1, "datatype": "anat", "suffix": "T1w", "entities": {"sub": subject},
        }], "heudiconv_version": "1.0", "heuristic": None, "parameters": {}, "source_dir": "",
        "scanner": None, "bids_dir": str(bids_dir), "created": "2026-01-01T00:00:00Z",
    }


def test_delete_removes_only_the_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    bids = tmp_path / "bids"
    (bids / "sub-01" / "anat").mkdir(parents=True)
    nii = bids / "sub-01" / "anat" / "sub-01_T1w.nii.gz"
    nii.write_bytes(b"x")
    mf = bids / "convert_manifest.json"
    mf.write_text(json.dumps(_manifest("01", bids)))

    from fmriflow.server.app import create_app
    c = TestClient(create_app(derivatives_dir=str(tmp_path / "derivatives")))
    assert [m["subject"] for m in c.get("/api/convert/manifests").json()["manifests"]] == ["01"]

    r = c.delete("/api/convert/manifests/01")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True and r.json()["path"] == str(mf)
    assert not mf.exists()
    assert nii.exists(), "BIDS outputs must survive a manifest delete"
    assert c.get("/api/convert/manifests").json()["manifests"] == []
    assert c.delete("/api/convert/manifests/01").status_code == 404
