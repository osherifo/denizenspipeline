"""Tests for the preset store + preset routes."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from fmriflow.preproc.stack import (
    BootstrapStage,
    PreprocStack,
    TransformStage,
)
from fmriflow.server.services.stack_preset_store import StackPresetStore


# ── Store unit tests ───────────────────────────────────────────────


class TestStackPresetStore:
    def test_save_then_load_round_trip(self, tmp_path):
        store = StackPresetStore(root=tmp_path)
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="passthrough"),
            transforms=[TransformStage(name="smooth", params={"fwhm": 6.0})],
        )
        store.save("my_preset", stack, description="test preset")

        reloaded_stack, desc = store.load("my_preset")
        assert reloaded_stack == stack
        assert desc == "test preset"

    def test_list_presets_returns_summaries(self, tmp_path):
        store = StackPresetStore(root=tmp_path)
        store.save(
            "lab_a",
            PreprocStack(bootstrap=BootstrapStage(kind="fmriprep")),
            "Lab A standard",
        )
        store.save(
            "lab_b",
            PreprocStack(
                bootstrap=BootstrapStage(kind="passthrough"),
                transforms=[TransformStage(name="smooth"), TransformStage(name="mask_apply")],
            ),
            "Lab B post-fmriprep cleanup",
        )

        presets = store.list_presets()
        names = [p.name for p in presets]
        assert "lab_a" in names
        assert "lab_b" in names

        lab_b = next(p for p in presets if p.name == "lab_b")
        assert lab_b.n_transforms == 2
        assert lab_b.bootstrap_kind == "passthrough"
        assert lab_b.description == "Lab B post-fmriprep cleanup"

    def test_delete_removes_file(self, tmp_path):
        store = StackPresetStore(root=tmp_path)
        store.save("tmp", PreprocStack(bootstrap=BootstrapStage(kind="passthrough")))
        assert store.delete("tmp") is True
        assert store.delete("tmp") is False
        with pytest.raises(FileNotFoundError):
            store.load("tmp")

    def test_invalid_slug_rejected(self, tmp_path):
        store = StackPresetStore(root=tmp_path)
        stack = PreprocStack(bootstrap=BootstrapStage(kind="passthrough"))
        # Path-separator-style names rejected to prevent traversal.
        with pytest.raises(ValueError):
            store.save("../escape", stack)
        with pytest.raises(ValueError):
            store.save("with/slash", stack)
        with pytest.raises(ValueError):
            store.save("", stack)
        with pytest.raises(ValueError):
            store.delete("../escape")

    def test_overwrite_existing(self, tmp_path):
        store = StackPresetStore(root=tmp_path)
        store.save("same", PreprocStack(bootstrap=BootstrapStage(kind="fmriprep")))
        store.save("same", PreprocStack(bootstrap=BootstrapStage(kind="passthrough")))
        reloaded, _ = store.load("same")
        assert reloaded.bootstrap.kind == "passthrough"


# ── Route integration ──────────────────────────────────────────────


@pytest.fixture
def app(tmp_path):
    from fmriflow.server.app import create_app

    app = create_app(derivatives_dir=str(tmp_path / "derivatives"))
    # Pin the preset store to a temp directory so tests don't pollute
    # the developer's real ~/.fmriflow/addons/pipelines/.
    app.state.stack_preset_store = StackPresetStore(root=tmp_path / "presets")
    return app


class TestPresetRoutes:
    def test_save_then_list(self, app):
        c = TestClient(app)
        save = c.post(
            "/api/preproc/stack/presets",
            json={
                "name": "my_preset",
                "description": "test",
                "stack": {
                    "bootstrap": {"kind": "passthrough", "params": {}},
                    "transforms": [{"name": "smooth", "params": {"fwhm": 5.0}}],
                },
            },
        )
        assert save.status_code == 200, save.text
        assert save.json()["saved"] is True

        listed = c.get("/api/preproc/stack/presets").json()["presets"]
        assert any(p["name"] == "my_preset" for p in listed)

    def test_load_returns_stack(self, app):
        c = TestClient(app)
        c.post(
            "/api/preproc/stack/presets",
            json={
                "name": "load_me",
                "description": "",
                "stack": {
                    "bootstrap": {"kind": "fmriprep", "params": {}},
                    "transforms": [],
                },
            },
        )
        loaded = c.get("/api/preproc/stack/presets/load_me").json()
        assert loaded["name"] == "load_me"
        assert loaded["stack"]["bootstrap"]["kind"] == "fmriprep"

    def test_load_unknown_404(self, app):
        c = TestClient(app)
        r = c.get("/api/preproc/stack/presets/never")
        assert r.status_code == 404

    def test_delete(self, app):
        c = TestClient(app)
        c.post(
            "/api/preproc/stack/presets",
            json={
                "name": "to_delete",
                "description": "",
                "stack": {"bootstrap": {"kind": "passthrough"}, "transforms": []},
            },
        )
        d = c.delete("/api/preproc/stack/presets/to_delete")
        assert d.status_code == 200
        # Second delete is 404.
        d2 = c.delete("/api/preproc/stack/presets/to_delete")
        assert d2.status_code == 404

    def test_invalid_name_400(self, app):
        c = TestClient(app)
        r = c.post(
            "/api/preproc/stack/presets",
            json={
                "name": "../escape",
                "stack": {"bootstrap": {"kind": "passthrough"}},
            },
        )
        assert r.status_code == 400

    def test_invalid_stack_400(self, app):
        c = TestClient(app)
        r = c.post(
            "/api/preproc/stack/presets",
            json={
                "name": "bad_stack",
                "stack": {"transforms": []},  # missing bootstrap
            },
        )
        assert r.status_code == 400
