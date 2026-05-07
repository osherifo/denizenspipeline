"""StructuralQCStore.list_all walks every dataset under root."""

from __future__ import annotations

from fmriflow.qc.structural_review import StructuralQCReview
from fmriflow.server.services.structural_qc_store import StructuralQCStore


def test_list_all_returns_reviews_across_datasets(tmp_path):
    store = StructuralQCStore(tmp_path)
    store.save(StructuralQCReview(dataset="ds-a", subject="sub01", status="approved"))
    store.save(StructuralQCReview(dataset="ds-a", subject="sub02", status="needs_edits"))
    store.save(StructuralQCReview(dataset="ds-b", subject="sub01", status="rejected"))

    rows = store.list_all()
    keyed = {(r.dataset, r.subject): r.status for r in rows}
    assert keyed == {
        ("ds-a", "sub01"): "approved",
        ("ds-a", "sub02"): "needs_edits",
        ("ds-b", "sub01"): "rejected",
    }


def test_list_all_empty_when_no_root(tmp_path):
    store = StructuralQCStore(tmp_path / "missing")
    assert store.list_all() == []


def test_list_all_skips_unsafe_dataset_dirs(tmp_path):
    """Stray directories that aren't valid dataset names are ignored."""
    store = StructuralQCStore(tmp_path)
    store.save(StructuralQCReview(dataset="ds-a", subject="sub01", status="approved"))
    # Create a directory that wouldn't pass the safe-name regex.
    (tmp_path / ".hidden").mkdir()
    rows = store.list_all()
    assert len(rows) == 1
    assert rows[0].dataset == "ds-a"
