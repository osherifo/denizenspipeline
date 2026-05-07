"""Round-trip StructuralQCReview through StructuralQCStore."""

from __future__ import annotations

import pytest

from fmriflow.qc.structural_review import StructuralQCReview
from fmriflow.server.services.structural_qc_store import StructuralQCStore


def test_save_and_get_roundtrip(tmp_path):
    store = StructuralQCStore(tmp_path)
    review = StructuralQCReview(
        dataset="ds-foo",
        subject="sub01",
        status="approved",
        reviewer="omar",
        notes="surfaces look good",
    )
    store.save(review)

    got = store.get("ds-foo", "sub01")
    assert got is not None
    assert got.status == "approved"
    assert got.reviewer == "omar"
    assert got.notes == "surfaces look good"
    # save() refreshes timestamp
    assert got.timestamp


def test_get_missing_returns_none(tmp_path):
    store = StructuralQCStore(tmp_path)
    assert store.get("ds-foo", "sub01") is None


def test_list_for_dataset(tmp_path):
    store = StructuralQCStore(tmp_path)
    store.save(StructuralQCReview(dataset="ds", subject="sub01", status="approved"))
    store.save(StructuralQCReview(dataset="ds", subject="sub02", status="needs_edits"))
    store.save(StructuralQCReview(dataset="other", subject="sub01", status="approved"))

    rows = store.list_for_dataset("ds")
    assert {(r.subject, r.status) for r in rows} == {
        ("sub01", "approved"),
        ("sub02", "needs_edits"),
    }


def test_unsafe_dataset_name_rejected(tmp_path):
    store = StructuralQCStore(tmp_path)
    with pytest.raises(ValueError):
        store.save(
            StructuralQCReview(dataset="../etc", subject="sub01", status="approved")
        )


def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        StructuralQCReview(dataset="ds", subject="sub01", status="bogus")
