"""Run records carry BIDS parts verbatim; legacy manifests upgrade on load."""

from __future__ import annotations

from fmriflow.convert.manifest import ConvertManifest, ConvertRunRecord, bids_parts
from fmriflow.convert.runner import collect_bids
from fmriflow.convert.manifest import ConvertConfig


def test_bids_parts_reads_datatype_suffix_and_entities():
    dt, sfx, ent = bids_parts("sub-01/ses-01/func/sub-01_ses-01_task-story_run-02_bold.nii.gz")
    assert (dt, sfx) == ("func", "bold")
    assert ent == {"sub": "01", "ses": "01", "task": "story", "run": "02"}
    dt, sfx, ent = bids_parts("sub-01/anat/sub-01_inv-1_MP2RAGE.nii.gz")
    assert (dt, sfx) == ("anat", "MP2RAGE") and ent == {"sub": "01", "inv": "1"}


def test_collect_bids_does_not_invent_run_or_modality(tmp_path):
    (tmp_path / "sub-01" / "anat").mkdir(parents=True)
    (tmp_path / "sub-01" / "ses-01" / "func").mkdir(parents=True)
    (tmp_path / "sub-01" / "anat" / "sub-01_acq-mp2rage_inv-2_MP2RAGE.nii.gz").write_bytes(b"")
    (tmp_path / "sub-01" / "ses-01" / "func" / "sub-01_ses-01_task-story_run-03_bold.nii.gz").write_bytes(b"")

    m = collect_bids(ConvertConfig(source_dir="", bids_dir=str(tmp_path), subject="01", heuristic=""))
    by_suffix = {r.suffix: r for r in m.runs}
    anat = by_suffix["MP2RAGE"]
    assert anat.datatype == "anat" and anat.run_name == "" and anat.session == ""
    assert anat.entities == {"sub": "01", "acq": "mp2rage", "inv": "2"}
    func = by_suffix["bold"]
    assert func.datatype == "func" and func.run_name == "03" and func.task == "story" and func.session == "01"
    assert not hasattr(anat, "modality")


def test_legacy_manifest_record_upgrades_on_load():
    rec = ConvertRunRecord.from_dict({
        "run_name": "01", "task": "", "session": "", "source_series": "",
        "output_file": "sub-01/anat/sub-01_T1w.nii.gz", "sidecar_file": "",
        "n_volumes": 1, "modality": "T1w", "shape": [1, 2, 3], "tr": None, "notes": None,
    })
    assert rec.datatype == "anat" and rec.suffix == "T1w" and rec.entities == {"sub": "01"}
    assert rec.run_name == ""  # the old default "01" was a guess, not an entity

    d = ConvertManifest.from_dict({
        "subject": "01", "dataset": "d", "sessions": [], "runs": [{
            "run_name": "02", "task": "x", "session": "", "source_series": "",
            "output_file": "sub-01/func/sub-01_task-x_run-02_bold.nii.gz", "sidecar_file": "",
            "n_volumes": 10, "modality": "bold",
        }], "heudiconv_version": "", "heuristic": None, "parameters": {}, "source_dir": "",
        "scanner": None, "bids_dir": "", "created": "",
    })
    assert d.runs[0].suffix == "bold" and d.runs[0].run_name == "02"
