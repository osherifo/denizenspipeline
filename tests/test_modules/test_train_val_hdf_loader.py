"""Response loader for per-subject training/validation HDF5 files."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from fmriflow.modules.response_loaders.train_val_hdf import TrainValHdfResponseLoader


@pytest.fixture
def dataset(tmp_path):
    rng = np.random.default_rng(0)
    resp = tmp_path / "responses"
    resp.mkdir()
    trn = {"story_01": rng.standard_normal((10, 4)), "story_02": rng.standard_normal((8, 4))}
    val = {"story_03": rng.standard_normal((2, 6, 4))}
    trn["story_02"][3, 1] = np.nan
    with h5py.File(resp / "sub01_listening_fmri_data_trn.hdf", "w") as h:
        for k, v in trn.items():
            h[k] = v
    with h5py.File(resp / "sub01_listening_fmri_data_val.hdf", "w") as h:
        for k, v in val.items():
            h[k] = v
    (tmp_path / "mappers").mkdir()
    (tmp_path / "mappers" / "sub01_mappers.hdf").write_bytes(b"")
    return tmp_path, trn, val


def _config(root, **response):
    return {"subject": "sub01", "subject_config": {"surface": "fsaverage", "transform": ""},
            "response": {"loader": "train_val_hdf", "path": str(root / "responses"), "modality": "listening", **response}}


def test_loads_training_and_validation_runs(dataset):
    root, trn, val = dataset
    data = TrainValHdfResponseLoader().load(_config(root))
    assert sorted(data.responses) == ["story_01", "story_02", "story_03"]
    assert data.responses["story_01"].dtype == np.float32
    np.testing.assert_allclose(data.responses["story_01"], trn["story_01"], rtol=1e-6)
    np.testing.assert_allclose(data.responses["story_03"], val["story_03"].mean(axis=0), rtol=1e-6)
    assert data.responses["story_02"][3, 1] == 0.0                        # NaN replaced
    assert data.metadata["splits"] == {"story_01": "trn", "story_02": "trn", "story_03": "val"}
    assert data.metadata["n_repeats"]["story_03"] == 2
    assert data.metadata["mappers_file"].endswith("mappers/sub01_mappers.hdf")
    assert data.surface == "fsaverage" and data.mask.shape == (1,)


def test_repeats_stories_trimming_and_renaming(dataset):
    root, _, val = dataset
    loader = TrainValHdfResponseLoader()
    first = loader.load(_config(root, repeats="first", stories=["story_03"]))
    np.testing.assert_allclose(first.responses["story_03"], val["story_03"][0], rtol=1e-6)
    separate = loader.load(_config(root, repeats="separate", splits=["val"]))
    assert sorted(separate.responses) == ["story_03_rep1", "story_03_rep2"]
    trimmed = loader.load(_config(root, drop_last_trs=2, run_map={"story_01": "first_story"}, splits=["trn"]))
    assert trimmed.responses["first_story"].shape == (8, 4)
    assert trimmed.responses["story_02"].shape == (6, 4)
    with pytest.raises(ValueError, match="story_99"):
        loader.load(_config(root, stories=["story_01", "story_99"]))


def test_subject_can_come_from_the_response_section(dataset):
    root, _, _ = dataset
    cfg = _config(root, subject="sub01", splits=["trn"])
    cfg["subject"] = "someone_else"
    assert sorted(TrainValHdfResponseLoader().load(cfg).responses) == ["story_01", "story_02"]


def test_validate_config(dataset):
    root, _, _ = dataset
    loader = TrainValHdfResponseLoader()
    assert loader.validate_config(_config(root)) == []
    assert any("modality" in e for e in loader.validate_config({"subject": "sub01", "response": {"path": str(root)}}))
    assert any("not found" in e for e in loader.validate_config(_config(root, modality="reading")))
    assert any("repeats" in e for e in loader.validate_config(_config(root, repeats="median")))
    assert any("placeholder" in e for e in loader.validate_config(_config(root, file_pattern="{nope}.hdf")))
