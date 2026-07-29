"""Tests for declaring fmriflow's own files in .bidsignore.

The convert manifest is written to the dataset root, which the BIDS
spec has no slot for. Left undeclared, a strict validator exits
non-zero — and fmriprep runs that validator itself before it will
start, so an undeclared manifest blocks the whole downstream pipeline.
"""

from fmriflow.convert.runner import MANIFEST_FILENAME, ensure_bidsignore


def test_creates_the_file_when_absent(tmp_path):
    ensure_bidsignore(tmp_path)

    bidsignore = tmp_path / ".bidsignore"
    assert bidsignore.read_text().splitlines() == [MANIFEST_FILENAME]


def test_appends_without_clobbering_existing_entries(tmp_path):
    bidsignore = tmp_path / ".bidsignore"
    bidsignore.write_text(".duecredit.p\n")

    ensure_bidsignore(tmp_path)

    assert bidsignore.read_text().splitlines() == [".duecredit.p", MANIFEST_FILENAME]


def test_handles_a_file_with_no_trailing_newline(tmp_path):
    """heudiconv writes .bidsignore without a trailing newline.

    A naive append produces `.duecredit.pconvert_manifest.json` — one
    corrupt line that declares neither file.
    """
    bidsignore = tmp_path / ".bidsignore"
    bidsignore.write_text(".duecredit.p")  # no newline

    ensure_bidsignore(tmp_path)

    lines = bidsignore.read_text().splitlines()
    assert lines == [".duecredit.p", MANIFEST_FILENAME]
    assert bidsignore.read_text().endswith("\n")


def test_is_idempotent(tmp_path):
    ensure_bidsignore(tmp_path)
    first = (tmp_path / ".bidsignore").read_text()

    ensure_bidsignore(tmp_path)
    ensure_bidsignore(tmp_path)

    assert (tmp_path / ".bidsignore").read_text() == first
