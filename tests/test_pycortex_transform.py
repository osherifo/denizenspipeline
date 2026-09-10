"""Unit tests for the pycortex-transform step (no pycortex/FSL required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fmriflow.preproc.pycortex_transform import (
    PycortexTransformConfig,
    DEFAULT_XFMNAME,
    VALID_METHODS,
)


def test_default_xfmname_is_fmriflow():
    cfg = PycortexTransformConfig(cx_subject="sub01fs", reference=__file__)
    assert cfg.xfmname == "fmriflow"
    assert DEFAULT_XFMNAME == "fmriflow"


def test_validate_ok_with_existing_reference(tmp_path: Path):
    ref = tmp_path / "ref.nii.gz"
    ref.write_bytes(b"\x00")
    cfg = PycortexTransformConfig(cx_subject="sub01fs", reference=str(ref))
    assert cfg.validate() == []


def test_validate_missing_reference():
    cfg = PycortexTransformConfig(cx_subject="sub01fs", reference="/no/such/file.nii.gz")
    errs = cfg.validate()
    assert any("Reference volume not found" in e for e in errs)


def test_validate_bad_method(tmp_path: Path):
    ref = tmp_path / "ref.nii.gz"
    ref.write_bytes(b"\x00")
    cfg = PycortexTransformConfig(cx_subject="sub01fs", reference=str(ref), method="bogus")
    assert any("Invalid method" in e for e in cfg.validate())
    assert set(VALID_METHODS) == {"automatic", "automatic_fsl", "manual"}


def test_validate_missing_subject(tmp_path: Path):
    ref = tmp_path / "ref.nii.gz"
    ref.write_bytes(b"\x00")
    cfg = PycortexTransformConfig(cx_subject="", reference=str(ref))
    assert any("cx_subject is required" in e for e in cfg.validate())


def test_from_dict_filters_unknown_keys(tmp_path: Path):
    ref = tmp_path / "ref.nii.gz"
    ref.write_bytes(b"\x00")
    cfg = PycortexTransformConfig.from_dict(
        {"cx_subject": "sub01fs", "reference": str(ref), "junk": 1, "method": "manual"}
    )
    assert cfg.cx_subject == "sub01fs"
    assert cfg.method == "manual"


def test_native_flatmap_reporter_registered():
    from fmriflow.modules import _decorators

    # importing the module registers it via @reporter("native_flatmap")
    import fmriflow.modules.reporters.native_flatmap  # noqa: F401

    assert "native_flatmap" in _decorators._reporters
