"""Response loader for BIDS runs with one task per stimulus, repeats and multi-echo outputs."""

from __future__ import annotations

import nibabel as nib
import numpy as np
import pytest

from fmriflow.modules.response_loaders import bids_mult
from fmriflow.modules.response_loaders.bids_mult import BidsMultResponseLoader

SHAPE = (4, 3, 2, 6)          # x, y, z, t


def _volume(offset: float) -> np.ndarray:
    x, y, z, t = np.meshgrid(*[np.arange(n) for n in SHAPE], indexing="ij")
    return (1000 * t + 100 * x + 10 * y + z + offset).astype(np.int32)


def _save(path, data, tr=1.5):
    img = nib.Nifti1Image(data, np.eye(4))
    img.header.set_zooms((1.0, 1.0, 1.0, tr))
    nib.save(img, path)


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    func = tmp_path / "sub-01" / "ses-02" / "func"
    func.mkdir(parents=True)
    stem = "sub-01_ses-02_task-{task}_run-{run}"
    _save(func / f"{stem.format(task='storya', run='01')}_desc-preproc_bold.nii.gz", _volume(0))
    _save(func / f"{stem.format(task='storyb', run='02')}_desc-preproc_bold.nii.gz", _volume(0))
    _save(func / f"{stem.format(task='storyb', run='03')}_desc-preproc_bold.nii.gz", _volume(2))
    # files that must be ignored
    _save(func / f"{stem.format(task='storya', run='01')}_echo-1_desc-preproc_bold.nii.gz", _volume(500))
    _save(func / f"{stem.format(task='storya', run='01')}_desc-ocweights_bold.nii.gz", _volume(700))
    mask = np.zeros((2, 3, 4), dtype=bool)         # z, y, x
    mask[1, 2, 3] = True                           # voxel x=3, y=2, z=1
    mask[0, 0, 1] = True                           # voxel x=1, y=0, z=0
    monkeypatch.setattr(bids_mult, "_load_mask", lambda surface, transform, mask_type: mask)
    return tmp_path


def _config(root, **response):
    return {"subject": "01", "subject_config": {"surface": "sub01fs", "transform": "xfm"},
            "response": {"loader": "bids_mult", "path": str(root), **response}}


def test_one_run_per_task_with_axes_reordered_and_repeats_averaged(dataset):
    data = BidsMultResponseLoader().load(_config(dataset))
    assert sorted(data.responses) == ["storya", "storyb"]
    a = data.responses["storya"]
    assert a.shape == (6, 2) and a.dtype == np.float32
    # mask order is C order over (z, y, x): (0,0,1) first, then (1,2,3)
    np.testing.assert_array_equal(a[:, 0], 1000 * np.arange(6) + 100)
    np.testing.assert_array_equal(a[:, 1], 1000 * np.arange(6) + 321)
    np.testing.assert_array_equal(data.responses["storyb"], a + 1)      # mean of offsets 0 and 2
    assert data.metadata["n_repeats"] == {"storya": 1, "storyb": 2}
    assert data.metadata["tr"] == 1.5
    assert data.mask.shape == (2, 3, 4)


def test_repeat_modes_tasks_and_run_map(dataset):
    loader = BidsMultResponseLoader()
    separate = loader.load(_config(dataset, repeats="separate", tasks=["storyb"]))
    assert sorted(separate.responses) == ["storyb_ses-02_run-02", "storyb_ses-02_run-03"]
    first = loader.load(_config(dataset, repeats="first", run_map={"storyb": "test"}))
    np.testing.assert_array_equal(first.responses["test"], first.responses["storya"])
    echo = loader.load(_config(dataset, echo=1, tasks=["storya"]))
    np.testing.assert_array_equal(echo.responses["storya"][:, 0], 1000 * np.arange(6) + 600)


def test_errors(dataset, monkeypatch):
    loader = BidsMultResponseLoader()
    with pytest.raises(ValueError, match="storyc"):
        loader.load(_config(dataset, tasks=["storya", "storyc"]))
    monkeypatch.setattr(bids_mult, "_load_mask", lambda *a: np.ones((5, 5, 5), dtype=bool))
    with pytest.raises(ValueError, match="grid"):
        loader.load(_config(dataset))


def test_validate_config(dataset):
    loader = BidsMultResponseLoader()
    assert loader.validate_config(_config(dataset, sessions=["02"])) == []
    assert any("storyc" in e for e in loader.validate_config(_config(dataset, tasks=["storyc"])))
    assert any("repeats" in e for e in loader.validate_config(_config(dataset, repeats="median")))
    no_xfm = _config(dataset)
    no_xfm["subject_config"] = {}
    assert any("transform" in e for e in loader.validate_config(no_xfm))
    assert any("subject folder" in e for e in loader.validate_config({**_config(dataset), "subject": "02"}))
