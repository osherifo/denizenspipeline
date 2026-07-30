"""Tests for reconstructing what a heuristic did with each DICOM series.

The checks are the interesting part. A conversion check that fires on correct
data is worse than no check, because people learn to scroll past it — so
every warning here is asserted both to fire when it should and to stay quiet
when it should not.
"""

import pytest

from fmriflow.convert.decision_table import (
    DecisionTableError,
    build_decision_table,
    has_provenance,
)

SERIES_HEADER = (
    "series_id\tseries_description\tprotocol_name\tsequence_name\t"
    "series_files\tdim1\tdim2\tdim3\tdim4\tTR\tTE\tis_derived\tis_motion_corrected"
)


def _row(sid, desc, n=176, dims=(256, 256, 176, 1), derived="False"):
    return (
        f"{sid}\t{desc}\tprot\tseq\t{n}\t"
        f"{dims[0]}\t{dims[1]}\t{dims[2]}\t{dims[3]}\t3060\t2.56\t{derived}\tFalse"
    )


def _write(tmp_path, rows, mapping, subject="01"):
    info = tmp_path / ".heudiconv" / subject / "info"
    info.mkdir(parents=True)
    (info / "dicominfo.tsv").write_text("\n".join([SERIES_HEADER, *rows]) + "\n")
    # heudiconv writes a repr of the info dict, keyed by (template, outtype, ann).
    entries = ",\n ".join(
        f"({template!r}, ('nii.gz',), None): {sids!r}"
        for template, sids in mapping.items()
    )
    (info / f"{subject}.auto.txt").write_text("{" + entries + "}")
    return tmp_path


# ── the join ────────────────────────────────────────────────────────


def test_maps_claimed_series_and_marks_the_rest_dropped(tmp_path):
    _write(
        tmp_path,
        [_row("1-uni", "UNI", derived="True"), _row("2-inv", "INV1"),
         _row("3-loc", "localizer", n=3)],
        {"sub-{subject}/anat/sub-{subject}_T1w": ["1-uni"]},
    )

    table = build_decision_table(tmp_path, "01")

    assert len(table.series) == 3
    assert table.n_mapped == 1
    assert table.n_dropped == 2
    by_id = {s.series_id: s for s in table.series}
    assert by_id["1-uni"].output_template.endswith("_T1w")
    assert by_id["2-inv"].dropped
    assert by_id["3-loc"].dropped


def test_carries_series_metadata_through(tmp_path):
    _write(tmp_path, [_row("1-uni", "UNI", n=176, derived="True")],
           {"tmpl": ["1-uni"]})

    s = build_decision_table(tmp_path, "01").series[0]

    assert s.description == "UNI"
    assert s.n_files == 176
    assert s.dims == [256, 256, 176, 1]
    assert s.tr == 3060.0
    assert s.is_derived is True


def test_accepts_a_sub_prefixed_subject(tmp_path):
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]})

    assert build_decision_table(tmp_path, "sub-01").n_mapped == 1


def test_falls_back_to_the_edit_file(tmp_path):
    """heudiconv writes .auto.txt; a user may hand-edit .edit.txt."""
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]})
    info = tmp_path / ".heudiconv" / "01" / "info"
    (info / "01.auto.txt").rename(info / "01.edit.txt")

    assert build_decision_table(tmp_path, "01").n_mapped == 1


# ── absent or unreadable provenance ─────────────────────────────────


def test_reports_a_dataset_heudiconv_did_not_produce(tmp_path):
    with pytest.raises(DecisionTableError, match="dicominfo.tsv"):
        build_decision_table(tmp_path, "01")


def test_has_provenance_is_false_without_the_files(tmp_path):
    assert has_provenance(tmp_path, "01") is False
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]})
    assert has_provenance(tmp_path, "01") is True


def test_unparseable_mapping_is_reported(tmp_path):
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]})
    (tmp_path / ".heudiconv" / "01" / "info" / "01.auto.txt").write_text("{not python")

    with pytest.raises(DecisionTableError, match="could not parse"):
        build_decision_table(tmp_path, "01")


# ── the checks ──────────────────────────────────────────────────────


def test_warns_when_one_output_mixes_derived_and_original(tmp_path):
    """The MP2RAGE trap: INV (original) and UNI (derived) collapsed into T1w."""
    _write(
        tmp_path,
        [_row("1-uni", "UNI", derived="True"), _row("2-inv", "INV1", derived="False")],
        {"sub-{subject}/anat/sub-{subject}_T1w": ["1-uni", "2-inv"]},
    )

    warnings = build_decision_table(tmp_path, "01").warnings

    assert any("derived" in w and "original" in w for w in warnings)


def test_repeats_of_one_acquisition_do_not_warn(tmp_path):
    """Four runs of the same protocol is the normal case and must stay quiet.

    An earlier check compared normalised descriptions and fired here, because
    the run index sits mid-string.
    """
    _write(
        tmp_path,
        [_row(f"{i}-uni", f"anat_acq-mp2rage_run-0{i}_UNI", derived="True")
         for i in (1, 2, 3, 4)],
        {"sub-{subject}/anat/sub-{subject}_run-{item:02d}_T1w":
            [f"{i}-uni" for i in (1, 2, 3, 4)]},
    )

    assert build_decision_table(tmp_path, "01").warnings == []


def test_warns_when_one_output_mixes_geometries(tmp_path):
    _write(
        tmp_path,
        [_row("1-a", "A", dims=(256, 256, 176, 1)),
         _row("2-b", "B", dims=(128, 128, 60, 1))],
        {"sub-{subject}/anat/sub-{subject}_T1w": ["1-a", "2-b"]},
    )

    assert any("dimensions" in w for w in build_decision_table(tmp_path, "01").warnings)


def test_warns_about_substantial_dropped_series(tmp_path):
    _write(tmp_path, [_row("1-a", "A"), _row("2-big", "INV2", n=176)],
           {"tmpl": ["1-a"]})

    warnings = build_decision_table(tmp_path, "01").warnings

    assert any("dropped" in w and "INV2" in w for w in warnings)


def test_a_dropped_localizer_does_not_warn(tmp_path):
    """Small series are dropped on purpose constantly; warning on them is noise."""
    _write(tmp_path, [_row("1-a", "A"), _row("2-loc", "localizer", n=3)],
           {"tmpl": ["1-a"]})

    assert build_decision_table(tmp_path, "01").warnings == []


def test_warns_when_nothing_was_mapped(tmp_path):
    _write(tmp_path, [_row("1-a", "A", n=5)], {})

    assert any("matched nothing" in w for w in build_decision_table(tmp_path, "01").warnings)
