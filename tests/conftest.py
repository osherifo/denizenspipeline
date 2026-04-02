"""Shared fixtures for fmriflow test suite."""

import numpy as np
import pytest

from fmriflow.core.types import (
    FeatureData,
    FeatureSet,
    LanguageStim,
    ModelResult,
    PreparedData,
    ResponseData,
    StimRun,
    StimulusData,
)

# ── Constants ──────────────────────────────────────────────────────
N_TRS = 50
N_VOXELS = 20
N_FEATURES = 5
RUN_NAMES = ["story1", "story2", "story3"]


# ── Mock TextGrid / TRFile ────────────────────────────────────────

class MockTier:
    """Fake TextGrid tier with a make_simple_transcript method."""

    def __init__(self, entries):
        self._entries = entries

    def make_simple_transcript(self):
        return self._entries


class MockTextGrid:
    """Fake TextGrid with phoneme (tier 0) and word (tier 1) tiers."""

    def __init__(self, n_words=20):
        duration = 20.0
        word_dur = duration / n_words
        words = ["hello", "world", "the", "quick", "brown",
                 "fox", "jumps", "over", "lazy", "dog"] * (n_words // 10 + 1)
        words = words[:n_words]
        word_entries = []
        for i, w in enumerate(words):
            start = f"{i * word_dur:.3f}"
            end = f"{(i + 1) * word_dur:.3f}"
            word_entries.append((start, end, w))

        phones = ["HH", "sub20", "L", "OW", "W", "ER", "L", "D",
                  "DH", "sub20", "K", "W", "IH", "K", "B", "R",
                  "AW", "N", "F", "AA"] * (n_words // 10 + 1)
        phones = phones[:n_words * 2]
        phone_dur = duration / len(phones)
        phone_entries = []
        for i, p in enumerate(phones):
            start = f"{i * phone_dur:.3f}"
            end = f"{(i + 1) * phone_dur:.3f}"
            phone_entries.append((start, end, p))

        self.tiers = [MockTier(phone_entries), MockTier(word_entries)]


class MockTRFile:
    """Fake TRFile that returns evenly spaced trigger times."""

    def __init__(self, n_trs=N_TRS, duration=20.0):
        self._n_trs = n_trs
        self._duration = duration

    def get_reltriggertimes(self):
        return np.linspace(0, self._duration, self._n_trs)


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def rng():
    return np.random.RandomState(42)


@pytest.fixture
def mock_trfile():
    return MockTRFile()


@pytest.fixture
def mock_textgrid():
    return MockTextGrid()


@pytest.fixture
def mock_stim_run(mock_textgrid, mock_trfile):
    return StimRun(
        name="story1",
        stimulus=LanguageStim(
            textgrid=mock_textgrid,
            trfile=mock_trfile,
        ),
    )


@pytest.fixture
def mock_stimuli(mock_textgrid, mock_trfile):
    runs = {}
    for name in RUN_NAMES:
        runs[name] = StimRun(
            name=name,
            stimulus=LanguageStim(
                textgrid=MockTextGrid(),
                trfile=MockTRFile(),
            ),
        )
    return StimulusData(runs=runs)


@pytest.fixture
def mock_responses(rng):
    responses = {
        name: rng.randn(N_TRS, N_VOXELS).astype(np.float32)
        for name in RUN_NAMES
    }
    return ResponseData(
        responses=responses,
        mask=np.ones(N_VOXELS, dtype=bool),
        surface="test_surface",
        transform="test_transform",
    )


@pytest.fixture
def mock_feature_set(rng):
    data = {
        name: rng.randn(N_TRS, N_FEATURES).astype(np.float32)
        for name in RUN_NAMES
    }
    return FeatureSet(name="test_feature", data=data, n_dims=N_FEATURES)


@pytest.fixture
def mock_feature_data(mock_feature_set):
    return FeatureData(features={"test_feature": mock_feature_set})


@pytest.fixture
def mock_prepared_data(rng):
    n_train_trs = N_TRS * 2
    n_test_trs = N_TRS
    delays = [1, 2, 3, 4]
    n_delayed = N_FEATURES * len(delays)

    return PreparedData(
        X_train=rng.randn(n_train_trs, n_delayed).astype(np.float32),
        Y_train=rng.randn(n_train_trs, N_VOXELS).astype(np.float32),
        X_test=rng.randn(n_test_trs, n_delayed).astype(np.float32),
        Y_test=rng.randn(n_test_trs, N_VOXELS).astype(np.float32),
        feature_names=["test_feature"],
        feature_dims=[N_FEATURES],
        delays=delays,
        train_runs=["story1", "story2"],
        test_runs=["story3"],
    )


@pytest.fixture
def mock_model_result(rng):
    delays = [1, 2, 3, 4]
    n_delayed = N_FEATURES * len(delays)
    return ModelResult(
        weights=rng.randn(n_delayed, N_VOXELS).astype(np.float32),
        scores=rng.rand(N_VOXELS).astype(np.float32),
        alphas=np.full(N_VOXELS, 100.0),
        feature_names=["test_feature"],
        feature_dims=[N_FEATURES],
        delays=delays,
    )


@pytest.fixture
def minimal_config():
    return {
        "experiment": "test_exp",
        "subject": "test_subj",
        "features": [
            {"name": "numwords", "source": "compute"},
        ],
        "split": {
            "test_runs": ["story3"],
        },
        "preprocessing": {
            "trim_start": 5,
            "trim_end": 5,
            "delays": [1, 2, 3, 4],
            "zscore": True,
        },
        "model": {
            "type": "bootstrap_ridge",
            "params": {},
        },
        "reporting": {
            "formats": ["metrics"],
            "output_dir": "./results",
        },
    }


@pytest.fixture
def npz_feature_dir(tmp_path, rng):
    """Write .npz feature files per run, return the directory path."""
    feat_dir = tmp_path / "features"
    feat_dir.mkdir()
    for name in RUN_NAMES:
        arr = rng.randn(N_TRS, N_FEATURES).astype(np.float32)
        np.savez_compressed(feat_dir / f"{name}.npz", data=arr)
    return feat_dir
