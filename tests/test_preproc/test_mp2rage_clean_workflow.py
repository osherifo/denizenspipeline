"""Tests for the mp2rage_background_clean nipype bootstrap workflow.

The failure this workflow prevents is silent — an unmasked UNI reaching
recon-all produces a flat T1.mgz and bad surfaces with a zero exit code.
So the load-bearing tests here are the ones asserting it REFUSES to run
rather than the ones asserting it runs.
"""

from types import SimpleNamespace

import nibabel as nb
import numpy as np
import pytest

from fmriflow.preproc.backends.nipype_workflows.mp2rage_clean import (
    MP2RAGEBackgroundClean,
    _clean_one,
    _pair_up,
)
from fmriflow.preproc.workflow_registry import WorkflowRegistry


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    nb.save(nb.Nifti1Image(data.astype(np.float32), np.eye(4)), path)


@pytest.fixture
def bids(tmp_path):
    """A 2-run MP2RAGE dataset: bright-ish brain, mid-grey background."""
    anat = tmp_path / "src" / "sub-01" / "anat"
    rng = np.random.default_rng(0)
    for run in (1, 2):
        # UNI: background ~1900 noise, brain ~3800 (the real profile).
        uni = rng.normal(1900, 120, (12, 12, 12))
        uni[3:9, 3:9, 3:9] = rng.normal(3800, 80, (6, 6, 6))
        # INV2: background near 0, brain bright.
        inv2 = rng.normal(5, 2, (12, 12, 12)).clip(0)
        inv2[3:9, 3:9, 3:9] = rng.normal(600, 40, (6, 6, 6))
        stem = f"sub-01_acq-mp2rage_run-0{run}"
        _write(anat / f"{stem}_T1w.nii.gz", uni)
        _write(anat / f"{stem}_inv-2_MP2RAGE.nii.gz", inv2)
    (tmp_path / "src" / "dataset_description.json").write_text('{"Name":"t","BIDSVersion":"1.8.0"}')
    return tmp_path


def _config(bids, tmp_path, **params):
    return SimpleNamespace(
        subject="01",
        bids_dir=str(bids / "src"),
        output_dir=str(tmp_path / "out"),
        sessions=[],
        task=None,
        dataset="test",
        backend_params=params,
    )


# ── registration ────────────────────────────────────────────────────


def test_workflow_is_registered():
    reg = WorkflowRegistry()
    reg.discover()
    assert "mp2rage_background_clean" in [w.name for w in reg.list()]


# ── validation: the load-bearing half ───────────────────────────────


def test_refuses_when_inv2_is_missing(bids, tmp_path):
    """Without INV2 there is nothing to clean with — must not pass through."""
    for p in (bids / "src" / "sub-01" / "anat").glob("*inv-2*"):
        p.unlink()

    errors = MP2RAGEBackgroundClean().validate(_config(bids, tmp_path))

    assert errors, "missing INV2 must be an error, not a silent pass-through"
    assert "inv-2" in " ".join(errors)
    assert "EMIT_INVERSIONS" in " ".join(errors)


def test_refuses_a_partial_pairing(bids, tmp_path):
    """One run missing its INV2 is still a refusal — not 'clean what we can'."""
    next(iter((bids / "src" / "sub-01" / "anat").glob("*run-02_inv-2*"))).unlink()

    errors = MP2RAGEBackgroundClean().validate(_config(bids, tmp_path))

    assert any("1 of 2" in e for e in errors)


def test_rejects_bad_params(bids, tmp_path):
    wf = MP2RAGEBackgroundClean()
    assert any("method" in e for e in wf.validate(_config(bids, tmp_path, method="nope")))
    assert any("beta" in e for e in wf.validate(_config(bids, tmp_path, beta=0)))


def test_accepts_a_well_formed_dataset(bids, tmp_path):
    assert MP2RAGEBackgroundClean().validate(_config(bids, tmp_path)) == []


def test_pairs_runs_by_stem(bids, tmp_path):
    triples = _pair_up(str(bids / "src"), "01", str(tmp_path / "out"))
    assert len(triples) == 2
    for uni, inv2, out in triples:
        # Each UNI must be matched with its OWN run's inversion.
        assert uni.split("run-")[1][:2] == inv2.split("run-")[1][:2]
        assert out.endswith("_T1w.nii.gz")


# ── the actual operation ────────────────────────────────────────────


@pytest.mark.parametrize("method", ["soft", "mask"])
def test_cleaning_lifts_the_brain_to_background_ratio(bids, tmp_path, method):
    """The point is SEPARATION, not preserving absolute intensity.

    `soft` scales tissue by INV2/(INV2+beta) — about 0.86 at beta=100 for
    typical INV2 brain values — so brain intensity drops somewhat. That is
    harmless: FreeSurfer normalises intensity anyway, and what it needs is
    a near-zero background. `mask` leaves tissue untouched instead.
    """
    anat = bids / "src" / "sub-01" / "anat"
    uni_p = anat / "sub-01_acq-mp2rage_run-01_T1w.nii.gz"
    inv2_p = anat / "sub-01_acq-mp2rage_run-01_inv-2_MP2RAGE.nii.gz"
    out_p = tmp_path / "out.nii.gz"

    _clean_one(str(uni_p), str(inv2_p), str(out_p), method, 100.0, 1, False)

    before = nb.load(uni_p).get_fdata()
    after = nb.load(out_p).get_fdata()
    bg = (slice(0, 2), slice(0, 2), slice(0, 2))
    brain = (slice(4, 8), slice(4, 8), slice(4, 8))

    # Background driven far down.
    assert np.median(after[bg]) < 0.1 * np.median(before[bg])
    # Brain still clearly tissue-valued (soft attenuates ~15%, mask 0%).
    assert np.median(after[brain]) > 0.8 * np.median(before[brain])

    # The measure that actually predicts whether FreeSurfer will cope:
    # raw MP2RAGE sits around 2x, which is what breaks normalisation.
    ratio_before = np.median(before[brain]) / np.median(before[bg])
    ratio_after = np.median(after[brain]) / max(np.median(after[bg]), 1e-6)
    assert ratio_before < 5
    assert ratio_after > 10 * ratio_before


def test_unknown_method_raises(bids, tmp_path):
    anat = bids / "src" / "sub-01" / "anat"
    with pytest.raises(ValueError, match="unknown method"):
        _clean_one(
            str(anat / "sub-01_acq-mp2rage_run-01_T1w.nii.gz"),
            str(anat / "sub-01_acq-mp2rage_run-01_inv-2_MP2RAGE.nii.gz"),
            str(tmp_path / "x.nii.gz"), "bogus", 100.0, 1, False,
        )


def test_shape_mismatch_raises(bids, tmp_path):
    anat = bids / "src" / "sub-01" / "anat"
    bad = tmp_path / "bad_inv2.nii.gz"
    _write(bad, np.ones((6, 6, 6)))
    with pytest.raises(ValueError, match="shape"):
        _clean_one(
            str(anat / "sub-01_acq-mp2rage_run-01_T1w.nii.gz"),
            str(bad), str(tmp_path / "x.nii.gz"), "soft", 100.0, 1, False,
        )


# ── manifest ────────────────────────────────────────────────────────


def test_manifest_reports_what_was_written(bids, tmp_path):
    wf = MP2RAGEBackgroundClean()
    config = _config(bids, tmp_path)
    for uni, inv2, out in _pair_up(config.bids_dir, "01", config.output_dir):
        _clean_one(uni, inv2, out, "soft", 100.0, 2, False)

    manifest = wf.to_manifest(config, {})

    assert manifest.backend == "nipype"
    assert manifest.parameters["n_cleaned"] == 2
    assert manifest.parameters["method"] == "soft"
    assert manifest.additional_steps == ["mp2rage_background_clean:soft"]
    # Anatomical stage — no BOLD runs by design.
    assert manifest.runs == []
    # Dataset-level files must be carried over or the output is not valid BIDS.
    assert (tmp_path / "out" / "dataset_description.json").is_file()


def test_output_root_stays_valid_bids(bids, tmp_path):
    """output_dir IS a BIDS root here, so nothing unexpected may land in it.

    fmriprep runs bids-validator itself and aborts on a non-zero exit, so a
    stray manifest or nipype work tree blocks the whole downstream pipeline.
    """
    wf = MP2RAGEBackgroundClean()
    config = _config(bids, tmp_path)
    for uni, inv2, out in _pair_up(config.bids_dir, "01", config.output_dir):
        _clean_one(uni, inv2, out, "soft", 100.0, 2, False)
    wf.to_manifest(config, {})

    declared = (tmp_path / "out" / ".bidsignore").read_text().split()
    # The manager writes this AFTER to_manifest, so it must be pre-declared.
    assert "preproc_manifest.json" in declared
    assert ".nipype_work/" in declared


def test_nipype_work_dir_is_outside_the_bids_root(bids, tmp_path):
    pytest.importorskip("nipype")
    config = _config(bids, tmp_path)
    MP2RAGEBackgroundClean().build(config)

    out = tmp_path / "out"
    assert not (out / ".nipype_work").exists(), (
        "nipype working tree must not live inside the BIDS output root"
    )
    assert (out.parent / ".nipype_work").is_dir()


def test_bidsignore_survives_a_missing_trailing_newline(bids, tmp_path):
    from fmriflow.preproc.backends.nipype_workflows.mp2rage_clean import (
        _declare_in_bidsignore,
    )
    root = tmp_path / "root"
    root.mkdir()
    (root / ".bidsignore").write_text(".duecredit.p")  # no newline

    _declare_in_bidsignore(root, ("preproc_manifest.json",))

    assert (root / ".bidsignore").read_text().splitlines() == [
        ".duecredit.p", "preproc_manifest.json",
    ]


# ── rescaling: the quantisation fix ─────────────────────────────────


def _tissue_band(volume, tissue, n_bits=8):
    """8-bit levels the tissue occupies after a WHOLE-VOLUME rescale.

    The range must come from the whole volume, because that is what
    FreeSurfer's `conform` uses. Normalising the tissue subset by its own
    min/max always fills 0..255 and measures nothing.
    """
    lo, hi = float(volume.min()), float(volume.max())
    scaled = np.clip((tissue - lo) / max(hi - lo, 1e-9) * (2 ** n_bits - 1),
                     0, 2 ** n_bits - 1).astype(np.uint8)
    return int(scaled.max()) - int(scaled.min())


def test_rescaling_widens_the_range_tissue_occupies(tmp_path):
    """The point of rescale: more quantisation levels for tissue.

    Uses intensities measured from a real MP2RAGE rather than the shared
    fixture's single Gaussian blob — the effect scales with how much of the
    stored range tissue actually spans, and a narrow synthetic brain
    understates it. Real numbers: background ~1900, GM ~3700, WM ~3950,
    stored range 0..4095.
    """
    rng = np.random.default_rng(0)
    uni = rng.normal(1900, 120, (16, 16, 16))
    inv2 = rng.normal(5, 2, (16, 16, 16)).clip(0)
    # Two tissue classes, both parked near the top of the range.
    uni[4:12, 4:12, 4:8] = rng.normal(3700, 60, (8, 8, 4))    # "GM"
    uni[4:12, 4:12, 8:12] = rng.normal(3950, 40, (8, 8, 4))   # "WM"
    inv2[4:12, 4:12, 4:12] = rng.normal(600, 40, (8, 8, 8))

    anat = tmp_path / "in"
    anat.mkdir()
    uni_p, inv2_p = anat / "uni.nii.gz", anat / "inv2.nii.gz"
    _write(uni_p, uni)
    _write(inv2_p, inv2)

    plain, scaled = tmp_path / "plain.nii.gz", tmp_path / "scaled.nii.gz"
    _clean_one(str(uni_p), str(inv2_p), str(plain), "mask", 100.0, 1, False)
    _clean_one(str(uni_p), str(inv2_p), str(scaled), "mask", 100.0, 1, True)

    brain = (slice(5, 11), slice(5, 11), slice(5, 11))
    plain_vol = nb.load(plain).get_fdata()
    scaled_vol = nb.load(scaled).get_fdata()
    spread_plain = _tissue_band(plain_vol, plain_vol[brain])
    spread_scaled = _tissue_band(scaled_vol, scaled_vol[brain])

    # A synthetic volume understates the gain: mask dilation pulls a rim of
    # background into the percentile window, so the stretch is gentler than on
    # a real head. Measured on real data the band goes 32 -> 148 levels
    # (~4.6x); here ~1.7x is the honest expectation, so assert the direction
    # with margin rather than overfitting to a number.
    assert spread_scaled > spread_plain * 1.5, (
        f"rescaling should markedly widen the band tissue occupies "
        f"({spread_plain} -> {spread_scaled} 8-bit levels)"
    )


def test_rescaling_keeps_background_at_zero(bids, tmp_path):
    """Background must not be lifted off zero, or skull-stripping suffers."""
    anat = bids / "src" / "sub-01" / "anat"
    out = tmp_path / "scaled.nii.gz"
    _clean_one(
        str(anat / "sub-01_acq-mp2rage_run-01_T1w.nii.gz"),
        str(anat / "sub-01_acq-mp2rage_run-01_inv-2_MP2RAGE.nii.gz"),
        str(out), "mask", 100.0, 1, True,
    )

    d = nb.load(out).get_fdata()
    assert np.median(d[:2, :2, :2]) == 0


def test_rescale_is_off_by_default(bids, tmp_path):
    """Measured end to end it did not help and could hurt — see the module
    docstring. Opt-in rather than on."""
    wf = MP2RAGEBackgroundClean()
    assert wf._params(_config(bids, tmp_path))["rescale"] is False
    assert wf._params(_config(bids, tmp_path, rescale=True))["rescale"] is True


def test_manifest_records_whether_it_rescaled(bids, tmp_path):
    wf = MP2RAGEBackgroundClean()
    config = _config(bids, tmp_path, rescale=True)
    for uni, inv2, out in _pair_up(config.bids_dir, "01", config.output_dir):
        _clean_one(uni, inv2, out, "soft", 100.0, 2, True)

    manifest = wf.to_manifest(config, {})

    assert manifest.parameters["rescale"] is True
    assert "rescaled" in manifest.additional_steps[0]
