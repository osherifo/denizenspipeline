"""Phase 4b — backend-wrapper workflow tests.

Each of the three wrappers (fmriprep / custom / bids_app) is a thin
adapter from the workflow Protocol to the legacy PreprocBackend
Protocol. The wrappers don't run real preprocessing in these tests;
we monkey-patch the wrapped backend to confirm the dispatch works:

- ``validate`` translates the runner's ``_WorkflowCallConfig`` into
  a legacy ``PreprocConfig`` with the right backend name and
  forwards to the backend's ``validate``.
- ``build`` returns a ``_BackendBuildSentinel`` carrying the backend
  instance + the translated config.
- ``to_manifest`` returns the manifest the runner threaded back via
  ``outputs["manifest"]``.

The end-to-end runner integration (sentinel → backend.run() →
manifest) is exercised via the runner-side test in test_stack_runner.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fmriflow.preproc.backends.nipype_workflows.backend_adapters import (
    BidsAppWorkflow,
    CustomShellWorkflow,
    FmriprepWorkflow,
    _BackendBuildSentinel,
    _to_preproc_config,
)
from fmriflow.preproc.manifest import PreprocConfig, PreprocManifest, now_iso


class _StubConfig:
    """Minimal duck-typed _WorkflowCallConfig for unit tests."""

    def __init__(self, **kwargs):
        defaults = {
            "subject": "sub01",
            "output_dir": "/tmp/out",
            "bids_dir": "/tmp/bids",
            "derivatives_dir": None,
            "sessions": ["ses01"],
            "task": "story",
            "dataset": "study1",
            "backend_params": {"output_spaces": "MNI152NLin2009cAsym"},
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


# ── _to_preproc_config translation ────────────────────────────────


class TestToPreprocConfig:
    def test_full_translation(self):
        config = _StubConfig()
        pc = _to_preproc_config(config, "fmriprep")
        assert isinstance(pc, PreprocConfig)
        assert pc.subject == "sub01"
        assert pc.backend == "fmriprep"
        assert pc.output_dir == "/tmp/out"
        assert pc.bids_dir == "/tmp/bids"
        assert pc.sessions == ["ses01"]
        assert pc.task == "story"
        assert pc.backend_params == {"output_spaces": "MNI152NLin2009cAsym"}

    def test_empty_bids_dir_becomes_none(self):
        config = _StubConfig(bids_dir=None)
        pc = _to_preproc_config(config, "custom")
        assert pc.bids_dir is None

    def test_backend_name_is_used_in_translation(self):
        config = _StubConfig()
        pc = _to_preproc_config(config, "bids_app")
        assert pc.backend == "bids_app"


# ── FmriprepWorkflow ──────────────────────────────────────────────


class TestFmriprepWorkflow:
    def test_validate_delegates_to_backend(self):
        config = _StubConfig()
        wf = FmriprepWorkflow()

        with patch(
            "fmriflow.preproc.backends.nipype_workflows.backend_adapters.get_backend"
        ) as get:
            backend = get.return_value
            backend.validate.return_value = ["error one", "error two"]
            errors = wf.validate(config)

        get.assert_called_once_with("fmriprep")
        backend.validate.assert_called_once()
        # The validate arg must be a PreprocConfig.
        (called_with,), _ = backend.validate.call_args
        assert isinstance(called_with, PreprocConfig)
        assert called_with.backend == "fmriprep"
        assert errors == ["error one", "error two"]

    def test_build_returns_sentinel_with_correct_backend(self):
        config = _StubConfig()
        wf = FmriprepWorkflow()

        with patch(
            "fmriflow.preproc.backends.nipype_workflows.backend_adapters.get_backend"
        ) as get:
            backend = get.return_value
            sentinel = wf.build(config)

        get.assert_called_once_with("fmriprep")
        assert isinstance(sentinel, _BackendBuildSentinel)
        assert sentinel.backend is backend
        assert sentinel.preproc_config.backend == "fmriprep"
        assert sentinel.preproc_config.subject == "sub01"

    def test_to_manifest_returns_runner_threaded_manifest(self):
        config = _StubConfig()
        wf = FmriprepWorkflow()
        m = PreprocManifest(
            subject="sub01",
            dataset="study1",
            sessions=[],
            runs=[],
            backend="fmriprep",
            backend_version="23.2.1",
            parameters={},
            space="MNI152NLin2009cAsym",
            created=now_iso(),
        )
        result = wf.to_manifest(config, {"manifest": m})
        assert result is m

    def test_to_manifest_missing_manifest_raises(self):
        wf = FmriprepWorkflow()
        with pytest.raises(RuntimeError) as exc:
            wf.to_manifest(_StubConfig(), {})
        assert "manifest" in str(exc.value)


# ── CustomShellWorkflow ───────────────────────────────────────────


class TestCustomShellWorkflow:
    def test_build_returns_sentinel_with_custom_backend(self):
        wf = CustomShellWorkflow()
        with patch(
            "fmriflow.preproc.backends.nipype_workflows.backend_adapters.get_backend"
        ) as get:
            sentinel = wf.build(_StubConfig(backend_params={"command": "echo hi"}))
        get.assert_called_once_with("custom")
        assert sentinel.preproc_config.backend == "custom"
        assert sentinel.preproc_config.backend_params == {"command": "echo hi"}


# ── BidsAppWorkflow ───────────────────────────────────────────────


class TestBidsAppWorkflow:
    def test_build_returns_sentinel_with_bids_app_backend(self):
        wf = BidsAppWorkflow()
        with patch(
            "fmriflow.preproc.backends.nipype_workflows.backend_adapters.get_backend"
        ) as get:
            sentinel = wf.build(
                _StubConfig(backend_params={"container": "mriqc:latest"})
            )
        get.assert_called_once_with("bids_app")
        assert sentinel.preproc_config.backend == "bids_app"
        assert sentinel.preproc_config.backend_params == {"container": "mriqc:latest"}


# ── Registration as built-ins ─────────────────────────────────────


class TestWrappersAreDiscoverable:
    def test_all_three_wrappers_in_registry(self, tmp_path):
        from fmriflow.preproc.workflow_registry import WorkflowRegistry

        reg = WorkflowRegistry(user_dir=tmp_path)
        reg.discover()
        names = reg.names()
        assert "fmriprep" in names
        assert "custom" in names
        assert "bids_app" in names

        # All source-tagged as built-in.
        for name in ("fmriprep", "custom", "bids_app"):
            info = reg.info(name)
            assert info.source == "built-in"
