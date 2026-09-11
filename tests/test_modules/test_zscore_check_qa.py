"""zscore_check QA reporter on well z-scored data."""

from __future__ import annotations

import numpy as np

from fmriflow.core.types import PreparedData
from fmriflow.modules.qa_reporters.prepare_qa import ZScoreCheck


def _zscored(rng, n_rows, n_cols):
    x = rng.standard_normal((n_rows, n_cols))
    return (x - x.mean(0)) / x.std(0)       # every column std is 1 up to float error


def test_renders_when_column_stds_are_all_one(tmp_path):
    rng = np.random.default_rng(0)
    prepared = PreparedData(
        X_train=_zscored(rng, 200, 30), Y_train=_zscored(rng, 200, 50),
        X_test=_zscored(rng, 40, 30), Y_test=_zscored(rng, 40, 50),
        feature_names=["f"], feature_dims=[30], delays=[1], train_runs=["a"], test_runs=["b"],
    )
    out = ZScoreCheck().report(prepared, {}, tmp_path)
    assert (tmp_path / "zscore_check.png").is_file() and out["zscore"].endswith("zscore_check.png")


def test_renders_with_constant_columns(tmp_path):
    zeros = np.zeros((20, 4))
    prepared = PreparedData(X_train=zeros, Y_train=zeros, X_test=zeros, Y_test=zeros,
                            feature_names=["f"], feature_dims=[4], delays=[1], train_runs=["a"], test_runs=["b"])
    ZScoreCheck().report(prepared, {}, tmp_path)
    assert (tmp_path / "zscore_check.png").is_file()
