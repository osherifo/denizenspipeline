"""Tests for autoflatten integration module."""

import pytest
from pathlib import Path

from fmriflow.preproc.autoflatten import (
    AutoflattenConfig,
    AutoflattenRecord,
    AutoflattenResult,
    detect_existing_flats,
    check_surfaces,
    _resolve_hemispheres,
    _resolve_flat_patches,
    _build_autoflatten_command,
)


# ── Config construction ─────────────────────────────────────────────────


class TestAutoflattenConfig:
    def test_defaults(self, tmp_path):
        cfg = AutoflattenConfig(subjects_dir=str(tmp_path), subject="sub-01")
        assert cfg.hemispheres == "both"
        assert cfg.backend == "pyflatten"
        assert cfg.overwrite is False
        assert cfg.import_to_pycortex is True
        assert cfg.flat_patch_lh is None
        assert cfg.flat_patch_rh is None

    def test_from_dict(self, tmp_path):
        cfg = AutoflattenConfig.from_dict({
            "subjects_dir": str(tmp_path),
            "subject": "sub-01",
            "hemispheres": "lh",
            "backend": "freesurfer",
            "import_to_pycortex": False,
            "unknown_key": "ignored",
        })
        assert cfg.hemispheres == "lh"
        assert cfg.backend == "freesurfer"
        assert cfg.import_to_pycortex is False

    def test_validate_missing_subjects_dir(self):
        cfg = AutoflattenConfig(subjects_dir="/nonexistent", subject="sub-01")
        errors = cfg.validate()
        assert any("Subjects directory not found" in e for e in errors)

    def test_validate_missing_subject(self, tmp_path):
        cfg = AutoflattenConfig(subjects_dir=str(tmp_path), subject="sub-MISSING")
        errors = cfg.validate()
        assert any("Subject directory not found" in e for e in errors)

    def test_validate_ok(self, tmp_path):
        (tmp_path / "sub-01").mkdir()
        cfg = AutoflattenConfig(subjects_dir=str(tmp_path), subject="sub-01")
        errors = cfg.validate()
        assert errors == []

    def test_validate_invalid_hemispheres(self, tmp_path):
        (tmp_path / "sub-01").mkdir()
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            hemispheres="wrong",
        )
        errors = cfg.validate()
        assert any("Invalid hemispheres" in e for e in errors)

    def test_validate_invalid_backend(self, tmp_path):
        (tmp_path / "sub-01").mkdir()
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            backend="bad",
        )
        errors = cfg.validate()
        assert any("Invalid backend" in e for e in errors)

    def test_validate_missing_precomputed_patch(self, tmp_path):
        (tmp_path / "sub-01").mkdir()
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            flat_patch_lh="/nonexistent/lh.flat.patch.3d",
        )
        errors = cfg.validate()
        assert any("LH patch not found" in e for e in errors)


# ── detect_existing_flats ───────────────────────────────────────────────


class TestDetectExistingFlats:
    def test_no_surf_dir(self, tmp_path):
        (tmp_path / "sub-01").mkdir()
        result = detect_existing_flats(str(tmp_path), "sub-01")
        assert result == {}

    def test_no_patches(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        result = detect_existing_flats(str(tmp_path), "sub-01")
        assert result == {}

    def test_autoflatten_patches(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        (surf / "lh.autoflatten.flat.patch.3d").touch()
        (surf / "rh.autoflatten.flat.patch.3d").touch()
        result = detect_existing_flats(str(tmp_path), "sub-01")
        assert "lh" in result
        assert "rh" in result
        assert result["lh"].name == "lh.autoflatten.flat.patch.3d"

    def test_manual_patches(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        (surf / "lh.full.flat.patch.3d").touch()
        (surf / "rh.full.flat.patch.3d").touch()
        result = detect_existing_flats(str(tmp_path), "sub-01")
        assert "lh" in result
        assert result["lh"].name == "lh.full.flat.patch.3d"

    def test_freesurfer_patches(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        (surf / "lh.flat.patch.3d").touch()
        result = detect_existing_flats(str(tmp_path), "sub-01")
        assert "lh" in result
        assert "rh" not in result

    def test_autoflatten_takes_priority(self, tmp_path):
        """If multiple naming patterns exist, autoflatten pattern wins."""
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        (surf / "lh.autoflatten.flat.patch.3d").touch()
        (surf / "lh.full.flat.patch.3d").touch()
        result = detect_existing_flats(str(tmp_path), "sub-01")
        assert result["lh"].name == "lh.autoflatten.flat.patch.3d"


# ── check_surfaces ──────────────────────────────────────────────────────


class TestCheckSurfaces:
    def test_no_surfaces(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        result = check_surfaces(str(tmp_path), "sub-01")
        assert all(v is False for v in result.values())

    def test_some_surfaces(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        (surf / "lh.inflated").touch()
        (surf / "rh.inflated").touch()
        (surf / "lh.white").touch()
        result = check_surfaces(str(tmp_path), "sub-01")
        assert result["lh.inflated"] is True
        assert result["rh.inflated"] is True
        assert result["lh.white"] is True
        assert result["rh.white"] is False


# ── _resolve_hemispheres ────────────────────────────────────────────────


class TestResolveHemispheres:
    def test_both(self):
        assert _resolve_hemispheres("both") == ["lh", "rh"]

    def test_lh(self):
        assert _resolve_hemispheres("lh") == ["lh"]

    def test_rh(self):
        assert _resolve_hemispheres("rh") == ["rh"]


# ── _resolve_flat_patches ───────────────────────────────────────────────


class TestResolveFlatPatches:
    def test_explicit_precomputed(self, tmp_path):
        patch = tmp_path / "lh.flat.patch.3d"
        patch.touch()
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            flat_patch_lh=str(patch),
        )
        patches, source = _resolve_flat_patches(cfg, ["lh"])
        assert source == "import_only"
        assert "lh" in patches

    def test_existing_patches_no_overwrite(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        (surf / "lh.autoflatten.flat.patch.3d").touch()
        (surf / "rh.autoflatten.flat.patch.3d").touch()

        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            overwrite=False,
        )
        patches, source = _resolve_flat_patches(cfg, ["lh", "rh"])
        assert source == "precomputed"
        assert "lh" in patches
        assert "rh" in patches

    def test_existing_patches_with_overwrite(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        (surf / "lh.autoflatten.flat.patch.3d").touch()
        (surf / "rh.autoflatten.flat.patch.3d").touch()

        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            overwrite=True,
        )
        patches, source = _resolve_flat_patches(cfg, ["lh", "rh"])
        assert source == "autoflatten"
        assert patches == {}

    def test_no_existing_patches(self, tmp_path):
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)

        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
        )
        patches, source = _resolve_flat_patches(cfg, ["lh", "rh"])
        assert source == "autoflatten"
        assert patches == {}

    def test_partial_patches_triggers_autoflatten(self, tmp_path):
        """If only lh exists but both are requested, run autoflatten."""
        surf = tmp_path / "sub-01" / "surf"
        surf.mkdir(parents=True)
        (surf / "lh.autoflatten.flat.patch.3d").touch()

        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
        )
        patches, source = _resolve_flat_patches(cfg, ["lh", "rh"])
        assert source == "autoflatten"


# ── _build_autoflatten_command ──────────────────────────────────────────


class TestBuildCommand:
    def test_defaults(self, tmp_path):
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
        )
        cmd = _build_autoflatten_command(cfg)
        assert cmd[0] == "autoflatten"
        assert str(tmp_path / "sub-01") in cmd
        assert "--parallel" in cmd
        # Default backend is pyflatten — should NOT have --backend flag
        assert "--backend" not in cmd

    def test_freesurfer_backend(self, tmp_path):
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            backend="freesurfer",
        )
        cmd = _build_autoflatten_command(cfg)
        assert "--backend" in cmd
        assert cmd[cmd.index("--backend") + 1] == "freesurfer"

    def test_lh_only(self, tmp_path):
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            hemispheres="lh",
        )
        cmd = _build_autoflatten_command(cfg)
        assert "--hemispheres" in cmd
        assert cmd[cmd.index("--hemispheres") + 1] == "lh"

    def test_overwrite(self, tmp_path):
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            overwrite=True,
        )
        cmd = _build_autoflatten_command(cfg)
        assert "--overwrite" in cmd

    def test_template_file(self, tmp_path):
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            template_file="/path/to/template.json",
        )
        cmd = _build_autoflatten_command(cfg)
        assert "--template-file" in cmd
        assert cmd[cmd.index("--template-file") + 1] == "/path/to/template.json"

    def test_output_dir(self, tmp_path):
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            output_dir="/output",
        )
        cmd = _build_autoflatten_command(cfg)
        assert "--output-dir" in cmd
        assert cmd[cmd.index("--output-dir") + 1] == "/output"


# ── AutoflattenRecord ───────────────────────────────────────────────────


class TestAutoflattenRecord:
    def test_to_dict(self):
        record = AutoflattenRecord(
            source="autoflatten",
            backend="pyflatten",
            hemispheres=["lh", "rh"],
            flat_patches={"lh": "surf/lh.flat.patch.3d"},
            visualizations={},
            pycortex_surface="sub01fs",
            template="default",
            created="2026-04-13T00:00:00Z",
        )
        d = record.to_dict()
        assert d["source"] == "autoflatten"
        assert d["backend"] == "pyflatten"
        assert d["pycortex_surface"] == "sub01fs"

    def test_from_dict(self):
        data = {
            "source": "precomputed",
            "backend": None,
            "hemispheres": ["lh", "rh"],
            "flat_patches": {"lh": "a", "rh": "b"},
            "visualizations": {},
            "pycortex_surface": None,
            "template": "default",
            "created": "2026-04-13T00:00:00Z",
        }
        record = AutoflattenRecord.from_dict(data)
        assert record.source == "precomputed"
        assert record.backend is None

    def test_from_result(self, tmp_path):
        result = AutoflattenResult(
            subject="sub-01",
            hemispheres=["lh", "rh"],
            flat_patches={"lh": "/a/lh.flat", "rh": "/a/rh.flat"},
            visualizations={"lh": "/a/lh.png"},
            pycortex_surface="sub01fs",
            source="autoflatten",
            elapsed_s=42.0,
        )
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            backend="pyflatten",
        )
        record = AutoflattenRecord.from_result(result, cfg)
        assert record.source == "autoflatten"
        assert record.backend == "pyflatten"
        assert record.pycortex_surface == "sub01fs"
        assert record.template == "default"

    def test_from_result_import_only(self, tmp_path):
        result = AutoflattenResult(
            subject="sub-01",
            hemispheres=["lh", "rh"],
            flat_patches={},
            visualizations={},
            pycortex_surface="sub01fs",
            source="import_only",
            elapsed_s=1.0,
        )
        cfg = AutoflattenConfig(
            subjects_dir=str(tmp_path), subject="sub-01",
            flat_patch_lh="/a/lh.flat",
        )
        record = AutoflattenRecord.from_result(result, cfg)
        assert record.source == "import_only"
        assert record.backend is None


# ── Manifest integration ────────────────────────────────────────────────


class TestManifestIntegration:
    def test_manifest_autoflatten_field_default(self):
        from fmriflow.preproc.manifest import PreprocManifest
        m = PreprocManifest(
            subject="sub-01", dataset="test", sessions=[], runs=[],
            backend="fmriprep", backend_version="24.0", parameters={},
            space="T1w",
        )
        assert m.autoflatten is None

    def test_manifest_autoflatten_field_set(self):
        from fmriflow.preproc.manifest import PreprocManifest
        af_data = {
            "source": "autoflatten", "backend": "pyflatten",
            "hemispheres": ["lh", "rh"],
            "flat_patches": {"lh": "a", "rh": "b"},
            "visualizations": {},
            "pycortex_surface": "sub01fs",
            "template": "default", "created": "2026-04-13",
        }
        m = PreprocManifest(
            subject="sub-01", dataset="test", sessions=[], runs=[],
            backend="fmriprep", backend_version="24.0", parameters={},
            space="T1w", autoflatten=af_data,
        )
        assert m.autoflatten["source"] == "autoflatten"

    def test_manifest_round_trip_with_autoflatten(self, tmp_path):
        from fmriflow.preproc.manifest import PreprocManifest
        af_data = {
            "source": "precomputed", "backend": None,
            "hemispheres": ["lh", "rh"],
            "flat_patches": {"lh": "a", "rh": "b"},
            "visualizations": {},
            "pycortex_surface": None,
            "template": "default", "created": "2026-04-13",
        }
        m = PreprocManifest(
            subject="sub-01", dataset="test", sessions=[], runs=[],
            backend="fmriprep", backend_version="24.0", parameters={},
            space="T1w", autoflatten=af_data,
        )
        path = tmp_path / "manifest.json"
        m.save(path)
        m2 = PreprocManifest.from_json(path)
        assert m2.autoflatten["source"] == "precomputed"
        assert m2.autoflatten["pycortex_surface"] is None

    def test_preproc_config_post_steps(self):
        from fmriflow.preproc.manifest import PreprocConfig
        cfg = PreprocConfig.from_dict({
            "subject": "sub-01",
            "backend": "fmriprep",
            "output_dir": "/out",
            "post_steps": {
                "autoflatten": {
                    "enabled": True,
                    "backend": "pyflatten",
                    "import_to_pycortex": True,
                },
            },
        })
        assert cfg.post_steps is not None
        assert cfg.post_steps["autoflatten"]["enabled"] is True
