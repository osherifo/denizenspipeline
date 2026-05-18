"""Tests for the filesystem-backed RunRegistry / RunStateFile."""

import json

from fmriflow.server.services.run_registry import (
    RunRegistry,
    RunStateFile,
    STATE_FILENAME,
)


def _make_state(run_id: str = "run_test", **overrides) -> RunStateFile:
    defaults = dict(
        run_id=run_id,
        kind="autoflatten",
        backend="autoflatten",
        subject="sub-test",
        status="done",
    )
    defaults.update(overrides)
    return RunStateFile(**defaults)


class TestRunStateFileResultField:
    """The `result` field is what lets finished runs re-render their
    output payload after the live in-memory handle is gone."""

    def test_default_is_none(self):
        s = _make_state()
        assert s.result is None

    def test_round_trip_preserves_result(self, tmp_path):
        registry = RunRegistry(root=tmp_path)
        payload = {
            "result": {
                "subject": "sub-test",
                "source": "autoflatten",
                "hemispheres": ["lh", "rh"],
                "flat_patches": {
                    "lh": "/data/freesurfer/sub-test/surf/lh.autoflatten.flat.patch.3d",
                    "rh": "/data/freesurfer/sub-test/surf/rh.autoflatten.flat.patch.3d",
                },
                "visualizations": {
                    "lh": "/data/freesurfer/sub-test/surf/lh.autoflatten.flat.patch.png",
                    "rh": "/data/freesurfer/sub-test/surf/rh.autoflatten.flat.patch.png",
                },
                "pycortex_surface": "sub-testfs",
                "elapsed_s": 312.7,
            },
            "record": {"backend": "pyflatten"},
        }

        registry.register(_make_state(result=payload))

        reloaded = registry.load("run_test")
        assert reloaded is not None
        assert reloaded.result == payload

    def test_state_file_without_result_key_loads_clean(self, tmp_path):
        """Legacy state files (written before this field existed) must
        still load — the new field defaults to None."""
        registry = RunRegistry(root=tmp_path)
        run_dir = tmp_path / "legacy_run"
        run_dir.mkdir()
        legacy = {
            "run_id": "legacy_run",
            "kind": "autoflatten",
            "backend": "autoflatten",
            "subject": "sub-test",
            "status": "done",
            "pid": 1234,
            "started_at": 1.0,
            "finished_at": 2.0,
            "stdout_log": "",
            "params": {},
            "error": None,
        }
        (run_dir / STATE_FILENAME).write_text(json.dumps(legacy))

        reloaded = registry.load("legacy_run")
        assert reloaded is not None
        assert reloaded.result is None
        assert reloaded.subject == "sub-test"
