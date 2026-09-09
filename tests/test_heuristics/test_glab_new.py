"""glab_new heuristic: valid BIDS names, nothing usable dropped, nothing invalid emitted."""

from __future__ import annotations

import importlib.util
from collections import namedtuple
from pathlib import Path

import pytest

HEURISTIC = Path(__file__).resolve().parents[2] / "heuristics" / "glab_new.py"

Seq = namedtuple("Seq", "series_id series_description protocol_name image_type dim1 dim2 dim3 dim4 TR TE is_derived is_motion_corrected sequence_name")


def _seq(n, desc, image_type, dim3, dim4, tr=2.0):
    return Seq(f"{n}-{desc}", desc, desc, image_type, 100, 100, dim3, dim4, tr, 0.03, False, False, "epfid2d1")


M = ("ORIGINAL", "PRIMARY", "M", "ND", "MOSAIC")
P = ("ORIGINAL", "PRIMARY", "P", "ND", "MOSAIC")
GM = ("ORIGINAL", "PRIMARY", "M", "ND")
GP = ("ORIGINAL", "PRIMARY", "P", "ND")


@pytest.fixture
def heuristic():
    if not HEURISTIC.is_file():
        pytest.skip("lab heuristics live in the gitignored heuristics/ dir; glab_new.py not present here")
    spec = importlib.util.spec_from_file_location("glab_new", HEURISTIC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _templates(info):
    return {k[0]: v for k, v in info.items()}


def test_story_session(heuristic):
    seqinfo = [
        _seq(1, "localizer", ("ORIGINAL", "PRIMARY", "M", "ND", "NORM"), 3, 1, 0.01),
        _seq(2, "quick-slicepos", GM, 50, 1, 0.4),
        _seq(3, "gre_field_mapping", GM, 60, 1, 0.4),
        _seq(4, "gre_field_mapping", GP, 30, 1, 0.4),
        _seq(5, "alternateithicatom", M, 30, 363),
        _seq(6, "alternateithicatom", P, 30, 363),
        _seq(7, "gre_field_mapping", GM, 60, 1, 0.4),
        _seq(8, "gre_field_mapping", GP, 30, 1, 0.4),
        _seq(9, "wheretheressmoke", M, 30, 310),
        _seq(10, "wheretheressmoke", P, 30, 310),
        _seq(11, "wheretheressmoke", M, 30, 311),
        _seq(12, "wheretheressmoke", P, 30, 311),
        _seq(13, "alternateithicatom_eyetrackercalib", M, 30, 1),
        _seq(14, "3x_val3min", M, 30, 294),
        _seq(99, "Phoenix Document", ("ORIGINAL", "PRIMARY", "OTHER", "CSA REPORT"), 0, 16, -1),
    ]
    t = _templates(heuristic.infotodict(seqinfo))

    # GRE pairs, numbered in order; heudiconv splits _magnitude into magnitude1/2
    assert t["sub-{subject}/{session}/fmap/sub-{subject}_{session}_run-01_magnitude"] == ["3-gre_field_mapping"]
    assert t["sub-{subject}/{session}/fmap/sub-{subject}_{session}_run-01_phasediff"] == ["4-gre_field_mapping"]
    assert t["sub-{subject}/{session}/fmap/sub-{subject}_{session}_run-02_magnitude"] == ["7-gre_field_mapping"]
    # no _epi without dir-, ever
    assert not any(k.endswith("_epi") for k in t)

    # functionals: phase twins skipped, repeat gets run-01/02, single stays plain
    assert t["sub-{subject}/{session}/func/sub-{subject}_{session}_task-alternateithicatom_bold"] == ["5-alternateithicatom"]
    assert t["sub-{subject}/{session}/func/sub-{subject}_{session}_task-wheretheressmoke_run-01_bold"] == ["9-wheretheressmoke"]
    assert t["sub-{subject}/{session}/func/sub-{subject}_{session}_task-wheretheressmoke_run-02_bold"] == ["11-wheretheressmoke"]
    # the one-volume "run" is not a bold file; the unknown 4-D series is kept under a clean label
    assert "13-alternateithicatom_eyetrackercalib" not in sum(t.values(), [])
    assert t["sub-{subject}/{session}/func/sub-{subject}_{session}_task-3xval3min_bold"] == ["14-3x_val3min"]
    # scouts and reports gone
    assert not any(sid.startswith(("1-", "2-", "99-")) for sids in t.values() for sid in sids)
    # every key maps to exactly one series: nothing collapsed
    assert all(len(v) == 1 for v in t.values())


def test_memprage_keeps_the_rms_image_only(heuristic):
    seqinfo = [
        _seq(2, "MEMPRAGE_P3", ("ORIGINAL", "PRIMARY", "M", "ND", "NORM"), 640, 1, 2.53),
        _seq(3, "MEMPRAGE_P3", ("ORIGINAL", "PRIMARY", "OTHER", "ND", "NORM", "MEAN"), 160, 1, 2.53),
    ]
    t = _templates(heuristic.infotodict(seqinfo))
    assert t == {"sub-{subject}/{session}/anat/sub-{subject}_{session}_T1w": ["3-MEMPRAGE_P3"]}


def test_topup_fieldmaps_need_a_direction(heuristic):
    seqinfo = [
        _seq(3, "fmap_ses-01_dir-AP_run-01", GM, 56, 3, 8.0),
        _seq(4, "fmap_ses-01_dir-PA_run-01", GM, 56, 3, 8.0),
        _seq(5, "fmap_nodir", GM, 56, 3, 8.0),
        _seq(6, "func_ses-01_task-train01", M, 56, 300),
        _seq(7, "func_ses-01_task-train01_SBRef", M, 56, 1),
    ]
    t = _templates(heuristic.infotodict(seqinfo))
    assert t["sub-{subject}/{session}/fmap/sub-{subject}_{session}_dir-AP_run-01_epi"] == ["3-fmap_ses-01_dir-AP_run-01"]
    assert t["sub-{subject}/{session}/fmap/sub-{subject}_{session}_dir-PA_run-01_epi"] == ["4-fmap_ses-01_dir-PA_run-01"]
    assert "5-fmap_nodir" not in sum(t.values(), [])
    assert t["sub-{subject}/{session}/func/sub-{subject}_{session}_task-train01_bold"] == ["6-func_ses-01_task-train01"]
    assert t["sub-{subject}/{session}/func/sub-{subject}_{session}_task-train01_sbref"] == ["7-func_ses-01_task-train01_SBRef"]
