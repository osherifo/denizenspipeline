"""Phase 3 — transform registry tests.

Mirrors the workflow-registry tests since the two registries are
deliberately separate. Covers:

- ``@register_transform`` registers a class into the module-level
  registry.
- ``TransformRegistry.discover()`` scans built-in (``identity``
  ships with the codebase), user dropins, pip entry-points.
- Higher-precedence tiers shadow lower ones.
- The shipped ``identity`` transform satisfies the ``Transform``
  Protocol and is discoverable + instantiable + runs without
  side-effects.
- Preflight reuses the Phase 2 helper unchanged (transforms
  expose the same REQUIRED_* class attrs).
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

from fmriflow.preproc.preflight import preflight
from fmriflow.preproc.transform import Transform
from fmriflow.preproc.transform_registry import (
    TransformRegistry,
    register_transform,
)


# ── Built-in identity transform ─────────────────────────────────────


class TestIdentityTransform:
    def test_satisfies_protocol(self):
        from fmriflow.preproc.builtin_transforms.identity import (
            IdentityTransform,
        )

        t = IdentityTransform()
        assert isinstance(t, Transform)

    def test_discovered_by_built_in_scan(self, tmp_path):
        reg = TransformRegistry(user_dir=tmp_path)
        reg.discover()
        assert "identity" in reg.names()

    def test_info_reflects_class_metadata(self, tmp_path):
        reg = TransformRegistry(user_dir=tmp_path)
        reg.discover()
        info = reg.info("identity")
        assert info.name == "identity"
        assert info.version == "0.1.0"
        assert info.source == "built-in"
        assert info.container_bound is False
        assert info.inputs == ["in_file"]
        assert info.outputs == ["out_file"]

    def test_run_is_noop_passthrough(self, tmp_path):
        reg = TransformRegistry(user_dir=tmp_path)
        reg.discover()
        t = reg.get("identity")
        result = t.run(
            inputs={"in_file": Path("/some/input.nii.gz")},
            out_dir=tmp_path,
            params={},
        )
        # Identity passes the input through unchanged.
        assert result == {"out_file": Path("/some/input.nii.gz")}


# ── User-tier discovery ────────────────────────────────────────────


def _write_user_transform(dir_: Path, name: str, version: str = "0.1") -> Path:
    src = textwrap.dedent(f"""
        from fmriflow.preproc.transform_registry import register_transform

        @register_transform({name!r})
        class _UserTransform:
            name = {name!r}
            version = {version!r}
            description = "user-supplied test transform"
            INPUTS = ["in_file"]
            OUTPUTS = ["out_file"]
            PARAM_SCHEMA = {{}}
            REQUIRED_PYTHON = []
            REQUIRED_TOOLS = []
            REQUIRED_ENV = []
            CONTAINER = None

            def run(self, inputs, out_dir, params):
                return {{}}
    """).strip()
    path = dir_ / f"{name}.py"
    path.write_text(src)
    return path


class TestUserDirDiscovery:
    def test_user_transform_picked_up(self, tmp_path):
        _write_user_transform(tmp_path, "lab_tx")
        reg = TransformRegistry(user_dir=tmp_path)
        reg.discover()
        assert "lab_tx" in reg.names()
        info = reg.info("lab_tx")
        assert info.source == "user"

    def test_user_transform_shadows_built_in(self, tmp_path):
        _write_user_transform(tmp_path, "identity", version="9.9")
        reg = TransformRegistry(user_dir=tmp_path)
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
        reg = TransformRegistry(user_dir=tmp_path)
        # Should not raise — the underscore file is skipped.
        reg.discover()


class TestDecoratorBehaviour:
    def test_double_registration_logs_warning(self, caplog):
        @register_transform("dup_tx_test")
        class A:
            name = "dup_tx_test"

        with caplog.at_level(logging.WARNING):
            @register_transform("dup_tx_test")
            class B:
                name = "dup_tx_test"

        assert any("dup_tx_test" in rec.message for rec in caplog.records)

    def test_same_class_reregistration_silent(self, caplog):
        @register_transform("idem_tx_test")
        class A:
            name = "idem_tx_test"

        with caplog.at_level(logging.WARNING):
            register_transform("idem_tx_test")(A)

        assert not any("idem_tx_test" in rec.message for rec in caplog.records)


class TestGetUnknownName:
    def test_keyerror_lists_available(self, tmp_path):
        reg = TransformRegistry(user_dir=tmp_path)
        reg.discover()
        with pytest.raises(KeyError) as exc:
            reg.get("nonexistent_transform")
        assert "nonexistent_transform" in str(exc.value)
        assert "identity" in str(exc.value)


# ── Preflight on transforms (reuses Phase 2 preflight) ─────────────


class TestPreflightAppliesToTransforms:
    def test_identity_preflight_clean(self, tmp_path):
        reg = TransformRegistry(user_dir=tmp_path)
        reg.discover()
        t = reg.get("identity")
        result = preflight(t)
        assert result.ok is True
        assert result.errors == []

    def test_transform_with_missing_tool_blocks(self):
        class _NeedsFakeTool:
            REQUIRED_PYTHON: list[str] = []
            REQUIRED_TOOLS = ["totally_fake_executable_xyz"]
            REQUIRED_ENV: list[str] = []
            CONTAINER = None

        result = preflight(_NeedsFakeTool())
        assert result.ok is False
        assert any("totally_fake_executable_xyz" in e for e in result.errors)


# ── Registries are independent ─────────────────────────────────────


class TestRegistryIndependence:
    def test_workflow_and_transform_registries_dont_share_names(self, tmp_path):
        # The user said keep them separate; this test enforces that.
        # A workflow named "identity" and a transform named "identity"
        # coexist without leaking across registries.
        from fmriflow.preproc.workflow_registry import WorkflowRegistry

        wf_reg = WorkflowRegistry(user_dir=tmp_path)
        wf_reg.discover()
        tx_reg = TransformRegistry(user_dir=tmp_path)
        tx_reg.discover()

        # Both have an 'identity' entry; they're different classes.
        assert "identity" in wf_reg.names()
        assert "identity" in tx_reg.names()
        assert wf_reg.get("identity").__class__ is not tx_reg.get("identity").__class__
