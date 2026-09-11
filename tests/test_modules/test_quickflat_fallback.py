"""Flatmap rendering without inkscape."""

from __future__ import annotations

import sys
import types

import pytest

from fmriflow.modules.reporters._quickflat import quickflat_png


def _fake_cortex(monkeypatch, error: Exception | None):
    calls = []

    def make_png(path, data, **kwargs):
        calls.append(kwargs)
        if error is not None and kwargs.get("with_rois", True):
            raise error

    cortex = types.ModuleType("cortex")
    cortex.quickflat = types.SimpleNamespace(make_png=make_png)
    monkeypatch.setitem(sys.modules, "cortex", cortex)
    return calls


def test_retries_without_rois_when_inkscape_is_missing(monkeypatch, tmp_path):
    calls = _fake_cortex(monkeypatch, RuntimeError("Inkscape doesn't seem to be installed on this system."))
    quickflat_png(tmp_path / "map.png", object(), with_curvature=True, dpi=100)
    assert len(calls) == 2
    assert calls[1] == {"with_curvature": True, "dpi": 100, "with_rois": False, "with_labels": False}


def test_renders_once_when_inkscape_is_available(monkeypatch, tmp_path):
    calls = _fake_cortex(monkeypatch, None)
    quickflat_png(tmp_path / "map.png", object(), dpi=100)
    assert calls == [{"dpi": 100}]


def test_other_errors_propagate(monkeypatch, tmp_path):
    _fake_cortex(monkeypatch, ValueError("bad volume"))
    with pytest.raises(ValueError, match="bad volume"):
        quickflat_png(tmp_path / "map.png", object())
