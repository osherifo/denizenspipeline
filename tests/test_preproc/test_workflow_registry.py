"""Phase 2 — nipype bootstrap-workflow registry + preflight tests.

Covers:

- ``@register_preproc_workflow`` registers a class into the module-level
  pending table.
- ``WorkflowRegistry.discover()`` scans built-in (``identity`` ships
  with the codebase), user dropins (a temp ``.py`` file), and pip
  entry-points (mocked).
- Higher-precedence tiers shadow lower ones; the shadowed entries
  are tracked so the UI can warn.
- ``preflight()`` detects missing Python packages, missing CLI tools,
  unset env vars, and container-bound workflows.
- The shipped ``identity`` workflow satisfies the ``PreprocWorkflow``
  Protocol and is discoverable + instantiable.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from fmriflow.preproc.preflight import (
    PreflightResult,
    check_env,
    check_python_packages,
    check_tools,
    preflight,
)
from fmriflow.preproc.preproc_workflow import PreprocWorkflow, WorkflowInfo
from fmriflow.preproc.workflow_registry import (
    WorkflowRegistry,
    register_preproc_workflow,
)


# ── Built-in identity workflow ──────────────────────────────────────


class TestIdentityWorkflow:
    def test_satisfies_protocol(self):
        from fmriflow.preproc.backends.nipype_workflows.identity import (
            IdentityWorkflow,
        )

        wf = IdentityWorkflow()
        assert isinstance(wf, PreprocWorkflow)

    def test_discovered_by_built_in_scan(self, tmp_path):
        # Pin user_dir to an empty tmp_path so we don't pull in
        # whatever the developer has under ~/.fmriflow/.
        reg = WorkflowRegistry(user_dir=tmp_path)
        reg.discover()
        assert "identity" in reg.names()

    def test_info_reflects_class_metadata(self, tmp_path):
        reg = WorkflowRegistry(user_dir=tmp_path)
        reg.discover()
        info = reg.info("identity")
        assert info.name == "identity"
        assert info.version == "0.1.0"
        assert info.source == "built-in"
        assert info.container_bound is False
        assert info.required_python == []
        assert info.required_tools == []

    def test_get_instantiates(self, tmp_path):
        reg = WorkflowRegistry(user_dir=tmp_path)
        reg.discover()
        wf = reg.get("identity")
        assert wf.name == "identity"
        # Smoke-test the manifest translation contract.
        manifest = wf.to_manifest(None, {})
        assert manifest.backend == "nipype"
        assert manifest.runs == []


# ── User-tier discovery ────────────────────────────────────────────


def _write_user_workflow(dir_: Path, name: str, version: str = "0.1") -> Path:
    src = textwrap.dedent(f"""
        from fmriflow.preproc.workflow_registry import register_preproc_workflow

        @register_preproc_workflow({name!r})
        class _UserWf:
            name = {name!r}
            version = {version!r}
            description = "user-supplied test workflow"
            PARAM_SCHEMA = {{}}
            REQUIRED_PYTHON = []
            REQUIRED_TOOLS = []
            REQUIRED_ENV = []
            CONTAINER = None

            def validate(self, config):
                return []

            def build(self, config):
                return None

            def to_manifest(self, config, wf_outputs):
                return None
    """).strip()
    path = dir_ / f"{name}.py"
    path.write_text(src)
    return path


class TestUserDirDiscovery:
    def test_user_workflow_picked_up(self, tmp_path):
        _write_user_workflow(tmp_path, "lab_wf")
        reg = WorkflowRegistry(user_dir=tmp_path)
        reg.discover()
        assert "lab_wf" in reg.names()
        info = reg.info("lab_wf")
        assert info.source == "user"

    def test_user_workflow_shadows_built_in(self, tmp_path):
        # Drop a "identity" override into the user dir; the user
        # version must win, and the built-in must be recorded as
        # shadowed.
        _write_user_workflow(tmp_path, "identity", version="9.9")
        reg = WorkflowRegistry(user_dir=tmp_path)
        reg.discover()
        info = reg.info("identity")
        assert info.source == "user"
        assert info.version == "9.9"
        shadowed = reg.shadowed()
        assert any(name == "identity" and src == "built-in" for name, src in shadowed)

    def test_underscore_prefixed_files_skipped(self, tmp_path):
        (tmp_path / "_private.py").write_text(
            "raise RuntimeError('should never run')"
        )
        reg = WorkflowRegistry(user_dir=tmp_path)
        # Should not raise — the underscore file is skipped.
        reg.discover()


class TestDecoratorBehaviour:
    def test_double_registration_logs_warning(self, caplog, tmp_path):
        # Two separate classes with the same name → the second wins
        # (the decorator overwrites), but a warning is logged.
        import logging

        @register_preproc_workflow("dup_test")
        class A:
            name = "dup_test"

        with caplog.at_level(logging.WARNING):
            @register_preproc_workflow("dup_test")
            class B:
                name = "dup_test"

        assert any("dup_test" in rec.message for rec in caplog.records)

    def test_same_class_reregistration_silent(self, caplog):
        # If the *same* class re-registers (e.g. module reload),
        # don't warn.
        import logging

        @register_preproc_workflow("idem_test")
        class A:
            name = "idem_test"

        with caplog.at_level(logging.WARNING):
            register_preproc_workflow("idem_test")(A)

        assert not any("idem_test" in rec.message for rec in caplog.records)


class TestGetUnknownName:
    def test_keyerror_lists_available(self, tmp_path):
        reg = WorkflowRegistry(user_dir=tmp_path)
        reg.discover()
        with pytest.raises(KeyError) as exc:
            reg.get("nonexistent_workflow")
        assert "nonexistent_workflow" in str(exc.value)
        # Available should include 'identity' at minimum.
        assert "identity" in str(exc.value)


# ── Preflight ──────────────────────────────────────────────────────


class TestCheckPythonPackages:
    def test_missing_package_reported(self):
        errors = check_python_packages(["definitely_not_a_real_package_xyz123"])
        assert len(errors) == 1
        assert "definitely_not_a_real_package_xyz123" in errors[0]
        assert "pip install" in errors[0]

    def test_present_package_clean(self):
        # pytest itself is installed if we're running these tests.
        errors = check_python_packages(["pytest"])
        assert errors == []

    def test_version_mismatch_reported(self):
        # pytest is installed; ask for an impossibly high version.
        errors = check_python_packages(["pytest>=9999.0"])
        assert len(errors) == 1
        assert "pytest" in errors[0]
        # Should mention the version mismatch, not just absence.
        assert "version" in errors[0].lower() or "spec" in errors[0].lower()


class TestCheckTools:
    def test_missing_tool_reported(self):
        errors = check_tools(["definitely_not_a_real_executable_xyz"])
        assert len(errors) == 1
        assert "definitely_not_a_real_executable_xyz" in errors[0]

    def test_present_tool_clean(self):
        # Every Linux box has ls.
        errors = check_tools(["ls"])
        assert errors == []


class TestCheckEnv:
    def test_unset_var_reported(self):
        # Pick a var that's exceedingly unlikely to be set.
        errors = check_env(["FMRIFLOW_PHASE2_TEST_UNSET_VAR"])
        assert len(errors) == 1
        assert "FMRIFLOW_PHASE2_TEST_UNSET_VAR" in errors[0]

    def test_set_var_with_existing_path_clean(self):
        # /tmp exists on every box we run on.
        with patch.dict(os.environ, {"FMRIFLOW_TEST_PATH_VAR": "/tmp"}):
            errors = check_env(["FMRIFLOW_TEST_PATH_VAR"])
            assert errors == []

    def test_set_var_with_missing_path_reported(self):
        with patch.dict(
            os.environ,
            {"FMRIFLOW_TEST_PATH_VAR": "/this/path/definitely/does/not/exist/xyz"},
        ):
            errors = check_env(["FMRIFLOW_TEST_PATH_VAR"])
            assert len(errors) == 1
            assert "non-existent" in errors[0]

    def test_set_var_with_non_path_value_clean(self):
        with patch.dict(os.environ, {"FMRIFLOW_TEST_NON_PATH": "hello"}):
            errors = check_env(["FMRIFLOW_TEST_NON_PATH"])
            assert errors == []


class TestPreflightAggregation:
    def test_all_clean_ok_true(self):
        class _Wf:
            REQUIRED_PYTHON = ["pytest"]
            REQUIRED_TOOLS = ["ls"]
            REQUIRED_ENV: list[str] = []
            CONTAINER = None

        result = preflight(_Wf())
        assert result.ok is True
        assert result.errors == []
        assert result.warnings == []

    def test_any_failure_ok_false(self):
        class _Wf:
            REQUIRED_PYTHON = ["totally_fake_pkg_xyz"]
            REQUIRED_TOOLS = ["totally_fake_tool_xyz"]
            REQUIRED_ENV = ["FMRIFLOW_NOT_SET_XYZ"]
            CONTAINER = None

        result = preflight(_Wf())
        assert result.ok is False
        # One error per missing requirement.
        assert len(result.errors) == 3

    def test_container_bound_emits_warning(self):
        class _Wf:
            REQUIRED_PYTHON: list[str] = []
            REQUIRED_TOOLS: list[str] = []
            REQUIRED_ENV: list[str] = []
            CONTAINER = "ghcr.io/lab/wf:1.2"

        result = preflight(_Wf())
        assert result.ok is True
        assert len(result.warnings) == 1
        assert "ghcr.io/lab/wf:1.2" in result.warnings[0]

    def test_missing_attributes_treated_as_empty(self):
        class _BareWf:
            pass

        result = preflight(_BareWf())
        assert result.ok is True
        assert result.errors == []
