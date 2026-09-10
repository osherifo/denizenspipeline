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


def test_update_with_meta_round_tripped_pins_name_and_created(tmp_path):
    """The editor loads the whole saved file — _meta included — into the
    editable text, so an edit anywhere resubmits _meta too (not dropped).
    name/created must stay pinned to what is already on disk regardless;
    other _meta fields (description) follow the submitted edit."""
    store = ConvertConfigStore(configs_dir=tmp_path / "convert")
    store.save_config("a", {"convert": {"subject": "01"}}, description="original")
    on_disk = yaml.safe_load((tmp_path / "convert" / "a.yaml").read_text())
    created = on_disk["_meta"]["created"]

    # Exactly what the browser's CodeEditor round-trips: the full file,
    # _meta included, with name/created tampered (by hand or by accident)
    # and description genuinely edited.
    tampered = yaml.safe_dump({
        "convert": {"subject": "02"},
        "_meta": {"name": "not-a", "created": "2000-01-01T00:00:00+00:00", "description": "edited"},
    }, sort_keys=False)
    store.update_config("a.yaml", tampered)

    data = yaml.safe_load((tmp_path / "convert" / "a.yaml").read_text())
    assert data["convert"]["subject"] == "02"                    # the real edit went through
    assert data["_meta"]["name"] == "a"                          # identity pinned, not "not-a"
    assert data["_meta"]["created"] == created                   # provenance pinned, not rewritten
    assert data["_meta"]["description"] == "edited"              # other fields still editable

    # The listing must show the real name too, not the one the editor sent.
    summary = store.list_configs()
    assert next(c for c in summary if c["filename"] == "a.yaml")["name"] == "a"


def test_update_refusals(tmp_path):
    store = ConvertConfigStore(configs_dir=tmp_path / "convert")
    store.save_config("a", {"convert": {}})
    with pytest.raises(ValueError):
        store.update_config("a.yaml", "convert: [unterminated")
    with pytest.raises(ValueError):
        store.update_config("a.yaml", "- not a mapping\n")
    with pytest.raises(FileNotFoundError):
        store.update_config("nope.yaml", "convert: {}\n")
