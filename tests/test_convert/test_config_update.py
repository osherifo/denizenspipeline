"""Editing a saved convert config in place."""

from __future__ import annotations

import pytest
import yaml

from fmriflow.server.services.convert_config_store import ConvertConfigStore


def test_update_rewrites_body_and_keeps_meta(tmp_path):
    store = ConvertConfigStore(configs_dir=tmp_path / "convert")
    store.save_config("a", {"convert": {"subject": "01", "heuristic": "h", "bids_dir": "/b"}}, description="d")
    created = yaml.safe_load((tmp_path / "convert" / "a.yaml").read_text())["_meta"]["created"]

    # edit without a _meta block: the file's meta survives
    store.update_config("a.yaml", "convert:\n  subject: '02'\n  heuristic: h2\n  bids_dir: /b\n")
    data = yaml.safe_load((tmp_path / "convert" / "a.yaml").read_text())
    assert data["convert"]["subject"] == "02" and data["convert"]["heuristic"] == "h2"
    assert data["_meta"]["name"] == "a" and data["_meta"]["created"] == created and data["_meta"]["description"] == "d"
    assert store.get_config("a.yaml")["config"]["convert"]["subject"] == "02"


def test_update_refusals(tmp_path):
    store = ConvertConfigStore(configs_dir=tmp_path / "convert")
    store.save_config("a", {"convert": {}})
    with pytest.raises(ValueError):
        store.update_config("a.yaml", "convert: [unterminated")
    with pytest.raises(ValueError):
        store.update_config("a.yaml", "- not a mapping\n")
    with pytest.raises(FileNotFoundError):
        store.update_config("nope.yaml", "convert: {}\n")
