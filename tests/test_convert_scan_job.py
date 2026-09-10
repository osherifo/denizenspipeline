"""DICOM scans run on a thread, report progress, and can be cancelled."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from fmriflow.convert import dicom_utils


def _tree(tmp_path, n_files=120):
    root = tmp_path / "dicoms"
    for i in range(n_files):
        d = root / f"series{i % 3}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"img{i:04d}.dcm").write_bytes(b"\0" * 128 + b"DICM")
    return root


def test_iter_dicoms_streams_and_stops(tmp_path):
    root = _tree(tmp_path)
    seen = []
    with pytest.raises(dicom_utils.ScanCancelled):
        for p in dicom_utils._iter_dicoms(root, should_stop=lambda: len(seen) >= 5):
            seen.append(p)
    assert len(seen) == 5


def test_scan_job_completes_with_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    from fmriflow.server.app import create_app
    client = TestClient(create_app())
    root = _tree(tmp_path)
    job = client.post("/api/convert/scan", json={"source_dir": str(root)}).json()
    assert job["status"] == "running" and job["scan_id"].startswith("scan_")
    for _ in range(100):
        job = client.get(f"/api/convert/scan/{job['scan_id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert job["progress"]["files_seen"] == 120
    assert "series" in job["result"]
    assert client.get("/api/convert/scan/nope").status_code == 404
    assert client.post("/api/convert/scan", json={"source_dir": str(tmp_path / "missing")}).status_code == 400


def test_scan_job_can_be_cancelled(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    root = _tree(tmp_path, n_files=30)
    gate = threading.Event()

    real_iter = dicom_utils._iter_dicoms

    def slow_iter(r, *, should_stop=None):
        for p in real_iter(r, should_stop=should_stop):
            gate.wait(timeout=0.2)     # each file takes a while unless the gate opens
            yield p

    monkeypatch.setattr(dicom_utils, "_iter_dicoms", slow_iter)
    from fmriflow.server.app import create_app
    client = TestClient(create_app())
    job = client.post("/api/convert/scan", json={"source_dir": str(root)}).json()
    time.sleep(0.3)
    assert client.post(f"/api/convert/scan/{job['scan_id']}/cancel").json()["cancelled"] is True
    for _ in range(60):
        job = client.get(f"/api/convert/scan/{job['scan_id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "cancelled"
    assert job["progress"]["files_seen"] < 30
    assert client.post(f"/api/convert/scan/{job['scan_id']}/cancel").json()["cancelled"] is False
