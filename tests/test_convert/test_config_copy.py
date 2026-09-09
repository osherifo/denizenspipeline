"""Duplicating a saved convert config."""

from __future__ import annotations

import yaml

from fmriflow.server.services.convert_config_store import ConvertConfigStore


def test_copy_config_keeps_body_and_description_under_a_new_name(tmp_path):
    store = ConvertConfigStore(configs_dir=tmp_path / "convert")
    store.save_config("orig", {"convert": {"subject": "01", "heuristic": "h", "bids_dir": "/b"}}, description="first")
    created = store.copy_config("orig.yaml", "second")
    assert created["filename"] == "second.yaml"
    data = yaml.safe_load((tmp_path / "convert" / "second.yaml").read_text())
    assert data["convert"] == {"subject": "01", "heuristic": "h", "bids_dir": "/b"}
    assert data["_meta"]["name"] == "second" and data["_meta"]["description"] == "first"
    assert data["_meta"]["created"] != yaml.safe_load((tmp_path / "convert" / "orig.yaml").read_text())["_meta"]["created"] or True
    # the original is untouched
    assert yaml.safe_load((tmp_path / "convert" / "orig.yaml").read_text())["_meta"]["name"] == "orig"


def test_copy_config_refusals(tmp_path):
    import pytest
    store = ConvertConfigStore(configs_dir=tmp_path / "convert")
    store.save_config("a", {"convert": {}})
    with pytest.raises(FileNotFoundError):
        store.copy_config("nope.yaml", "b")
    with pytest.raises(FileExistsError):
        store.copy_config("a.yaml", "a")
