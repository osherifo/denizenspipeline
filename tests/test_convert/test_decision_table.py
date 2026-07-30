"""Tests for reconstructing what a heuristic did with each DICOM series.

The checks are the interesting part. A conversion check that fires on correct
data is worse than no check, because people learn to scroll past it — so
every warning here is asserted both to fire when it should and to stay quiet
when it should not.
"""

import pytest

from fmriflow.convert.decision_table import (
    DecisionTableError,
    list_units,
    bids_key,
    build_coverage,
    build_decision_table,
    build_flow,
    has_provenance,
    resolve_template,
)

SERIES_HEADER = (
    "series_id\tseries_description\tprotocol_name\tsequence_name\t"
    "series_files\tdim1\tdim2\tdim3\tdim4\tTR\tTE\tis_derived\t"
    "is_motion_corrected\timage_type"
)

IMAGE_TYPE = "('ORIGINAL', 'PRIMARY', 'M')"


def _row(sid, desc, n=176, dims=(256, 256, 176, 1), derived="False",
         image_type=IMAGE_TYPE):
    return (
        f"{sid}\t{desc}\tprot\tseq\t{n}\t"
        f"{dims[0]}\t{dims[1]}\t{dims[2]}\t{dims[3]}\t3060\t2.56\t{derived}\t"
        f"False\t{image_type}"
    )


def _write(tmp_path, rows, mapping, subject="01", session=None):
    base = tmp_path / ".heudiconv" / subject
    info = (base / session / "info") if session else (base / "info")
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
    assert by_id["1-uni"].rules[0].endswith("_T1w")
    assert by_id["1-uni"].status == "ok"
    assert by_id["2-inv"].dropped
    assert by_id["3-loc"].dropped


def test_carries_series_metadata_through(tmp_path):
    """The audit row must carry what a rule discriminates on."""
    _write(tmp_path, [_row("1-uni", "UNI", n=176, derived="True")],
           {"tmpl": ["1-uni"]})

    s = build_decision_table(tmp_path, "01").series[0]

    assert s.description == "UNI"
    assert s.n_files == 176
    assert s.dims == [256, 256, 176, 1]
    assert s.tr == 3060.0
    assert s.te == 2.56
    assert s.is_derived is True
    assert s.image_type == ["ORIGINAL", "PRIMARY", "M"]


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


# ── fan-out: one series, several outputs ────────────────────────────


def test_a_series_claimed_by_several_rules_fans_out(tmp_path):
    """A GRE fieldmap produces magnitude1, magnitude2 and phasediff.

    Keeping one template per series would silently drop two of the three,
    which is exactly the case the audit table exists to make visible.
    """
    _write(
        tmp_path,
        [_row("7-fmap", "gre_field_map", n=72)],
        {
            "sub-{subject}/fmap/sub-{subject}_magnitude1": ["7-fmap"],
            "sub-{subject}/fmap/sub-{subject}_magnitude2": ["7-fmap"],
            "sub-{subject}/fmap/sub-{subject}_phasediff": ["7-fmap"],
        },
    )

    s = build_decision_table(tmp_path, "01").series[0]

    assert len(s.rules) == 3
    assert len(s.outputs) == 3
    assert s.status == "fan-out ×3"
    assert not s.dropped


def test_rows_are_ordered_by_series_number(tmp_path):
    """Scanner order, which is the order a protocol is read in."""
    _write(
        tmp_path,
        [_row("12-c", "C"), _row("4-a", "A"), _row("7-b", "B")],
        {"tmpl": ["4-a"]},
    )

    numbers = [s.series_number for s in build_decision_table(tmp_path, "01").series]

    assert numbers == [4, 7, 12]


# ── template resolution ─────────────────────────────────────────────


def test_resolves_templates_into_real_bids_paths(tmp_path):
    assert resolve_template(
        "sub-{subject}/anat/sub-{subject}_run-{item:02d}_T1w", "01", 3,
    ) == "sub-01/anat/sub-01_run-03_T1w"
    assert resolve_template("sub-{subject}/anat/sub-{subject}_{item}_T1w", "sub-05", 1) \
        == "sub-05/anat/sub-05_1_T1w"


def test_item_indexes_from_one_within_each_rule(tmp_path):
    """heudiconv numbers {item} by position in a template's series list."""
    _write(
        tmp_path,
        [_row("1-a", "A"), _row("2-b", "B")],
        {"sub-{subject}/anat/sub-{subject}_run-{item:02d}_T1w": ["1-a", "2-b"]},
    )

    outs = [s.outputs[0] for s in build_decision_table(tmp_path, "01").series]

    assert outs == ["sub-01/anat/sub-01_run-01_T1w", "sub-01/anat/sub-01_run-02_T1w"]


# ── coverage matrix ─────────────────────────────────────────────────


def test_bids_key_folds_runs_but_keeps_distinct_images(tmp_path):
    """Four runs of one thing is one column; inv-1 and inv-2 are two."""
    assert bids_key("sub-01/anat/sub-01_run-01_T1w") == \
           bids_key("sub-01/anat/sub-01_run-04_T1w")
    assert bids_key("sub-01/anat/sub-01_inv-1_MP2RAGE") != \
           bids_key("sub-01/anat/sub-01_inv-2_MP2RAGE")


def test_coverage_counts_outputs_per_subject_and_key(tmp_path):
    for sub, rows, mapping in (
        ("01", [_row("1-a", "A"), _row("2-b", "B")],
         {"sub-{subject}/anat/sub-{subject}_run-{item:02d}_T1w": ["1-a", "2-b"]}),
        ("02", [_row("1-a", "A")],
         {"sub-{subject}/anat/sub-{subject}_run-{item:02d}_T1w": ["1-a"]}),
    ):
        _write(tmp_path, rows, mapping, subject=sub)

    cov = build_coverage(tmp_path)

    assert cov["subjects"] == ["sub-01", "sub-02"]
    assert cov["keys"] == ["anat/T1w"]
    assert cov["matrix"][0]["cells"] == [2]
    assert cov["matrix"][1]["cells"] == [1]


def test_coverage_distinguishes_a_missing_subject_from_a_dead_rule(tmp_path):
    """The two failure modes the matrix exists to tell apart.

    sub-02 is missing T2w that sub-01 has — a data incident, one empty cell.
    `sbref` is declared by both heuristics and produced by neither — a code
    bug, an empty column.
    """
    _write(tmp_path, [_row("1-a", "A"), _row("2-t2", "T2")],
           {"sub-{subject}/anat/sub-{subject}_T1w": ["1-a"],
            "sub-{subject}/anat/sub-{subject}_T2w": ["2-t2"],
            "sub-{subject}/func/sub-{subject}_sbref": []},
           subject="01")
    _write(tmp_path, [_row("1-a", "A")],
           {"sub-{subject}/anat/sub-{subject}_T1w": ["1-a"],
            "sub-{subject}/anat/sub-{subject}_T2w": [],
            "sub-{subject}/func/sub-{subject}_sbref": []},
           subject="02")

    cov = build_coverage(tmp_path)
    col = {k: i for i, k in enumerate(cov["keys"])}
    cells = {r["subject"]: r["cells"] for r in cov["matrix"]}

    # data incident: present for one subject, absent for the other
    assert cells["sub-01"][col["anat/T2w"]] == 1
    assert cells["sub-02"][col["anat/T2w"]] == 0
    assert "anat/T2w" not in cov["never_matched"]

    # code bug: declared everywhere, produced nowhere
    assert "func/sbref" in cov["never_matched"]
    assert all(r["cells"][col["func/sbref"]] == 0 for r in cov["matrix"])


def test_coverage_is_empty_without_provenance(tmp_path):
    cov = build_coverage(tmp_path)
    assert cov["subjects"] == [] and cov["matrix"] == []


# ── flow ────────────────────────────────────────────────────────────


def test_flow_aggregates_and_surfaces_dropped(tmp_path):
    _write(tmp_path, [_row("1-a", "A"), _row("2-drop", "localizer", n=3)],
           {"sub-{subject}/anat/sub-{subject}_T1w": ["1-a"]})

    flow = build_flow(tmp_path)

    assert flow["n_series"] == 2
    assert flow["n_dropped"] == 1
    pairs = {(l["source"], l["target"]): l["value"] for l in flow["links"]}
    assert pairs[("prot", "anat")] == 1
    assert any(t == "— dropped —" for (_, t) in pairs)


# ── sessions ────────────────────────────────────────────────────────


def test_finds_provenance_under_a_session(tmp_path):
    """heudiconv writes .heudiconv/<sub>/ses-<ses>/info for sessioned runs.

    Looking only at the sessionless path made every sessioned study report
    "no provenance" — a silent miss, which is worse than an error.
    """
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]}, session="ses-02")

    assert has_provenance(tmp_path, "01", "ses-02")
    assert build_decision_table(tmp_path, "01", "ses-02").n_mapped == 1


def test_session_is_found_without_being_named(tmp_path):
    """A single-session study should work without the caller knowing the label."""
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]}, session="ses-02")

    assert build_decision_table(tmp_path, "01").n_mapped == 1


def test_session_accepts_a_bare_label(tmp_path):
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]}, session="ses-02")

    assert build_decision_table(tmp_path, "01", "02").n_mapped == 1


def test_sessionless_wins_when_both_exist(tmp_path):
    _write(tmp_path, [_row("1-a", "A"), _row("2-b", "B")],
           {"tmpl": ["1-a", "2-b"]})
    _write(tmp_path, [_row("9-z", "Z")], {"tmpl": ["9-z"]}, session="ses-02")

    assert len(build_decision_table(tmp_path, "01").series) == 2


def test_units_list_every_session_separately(tmp_path):
    """A subject missing a whole session is a gap the matrix should show."""
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]}, subject="01", session="ses-01")
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]}, subject="01", session="ses-02")
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]}, subject="02", session="ses-01")

    assert list_units(tmp_path) == [
        ("01", "ses-01"), ("01", "ses-02"), ("02", "ses-01"),
    ]

    cov = build_coverage(tmp_path)
    assert cov["subjects"] == ["sub-01/ses-01", "sub-01/ses-02", "sub-02/ses-01"]


# ── subject normalisation ───────────────────────────────────────────


def test_subject_is_returned_as_a_bare_label(tmp_path):
    """Callers may pass '01' or 'sub-01'; echoing the raw string back makes a
    UI rendering 'sub-{subject}' produce 'sub-sub-01'."""
    _write(tmp_path, [_row("1-a", "A")], {"tmpl": ["1-a"]})

    assert build_decision_table(tmp_path, "01").subject == "01"
    assert build_decision_table(tmp_path, "sub-01").subject == "01"
    assert build_decision_table(tmp_path, "sub-01").to_dict()["subject"] == "01"
