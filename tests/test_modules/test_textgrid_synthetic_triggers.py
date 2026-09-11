"""TextGrid stimuli with synthetic triggers, and the phoneme histogram vocabulary."""

from __future__ import annotations

import numpy as np
import pytest

from fmriflow.modules.feature_extractors.basic import NumWordsExtractor
from fmriflow.modules.feature_extractors.histograms import ARPABET_PHONEMES, PhonemeHistogramExtractor
from fmriflow.modules.stimulus_loaders.textgrid import TextGridStimulusLoader, _SyntheticTRFile

GRID = """File type = "ooTextFile"
Object class = "TextGrid"

xmin = 0
xmax = 6
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "phone"
        xmin = 0
        xmax = 6
        intervals: size = 3
        intervals [1]:
            xmin = 0
            xmax = 1
            text = "HH"
        intervals [2]:
            xmin = 1
            xmax = 2
            text = "AH0"
        intervals [3]:
            xmin = 2
            xmax = 6
            text = "sp"
    item [2]:
        class = "IntervalTier"
        name = "word"
        xmin = 0
        xmax = 6
        intervals: size = 2
        intervals [1]:
            xmin = 0
            xmax = 2
            text = "HUH"
        intervals [2]:
            xmin = 2
            xmax = 6
            text = "sp"
"""


@pytest.fixture
def grid_dir(tmp_path):
    (tmp_path / "story_en.TextGrid").write_text(GRID)
    return tmp_path


def _stimuli(grid_dir, **stimulus):
    cfg = {"experiment": "x", "stimulus": {"loader": "textgrid", "textgrid_dir": str(grid_dir), "file_suffix": "_en",
                                           "tr": 1.0, "n_trs": {"story": 8}, **stimulus}}
    return TextGridStimulusLoader().load(cfg)


def test_synthetic_trfile_behaves_like_a_trfile():
    trf = _SyntheticTRFile(4, tr=1.5, sound_start=3.0)
    assert trf.avgtr == 1.5 and trf.n_trs == 4
    np.testing.assert_allclose(trf.get_reltriggertimes(), [-3.0, -1.5, 0.0, 1.5])


def test_features_extract_with_synthetic_triggers_and_follow_sound_start(grid_dir):
    at_zero = NumWordsExtractor().extract(_stimuli(grid_dir), ["story"], {}).data["story"][:, 0]
    assert at_zero.shape == (8,) and int(np.argmax(at_zero)) == 0
    shifted = NumWordsExtractor().extract(_stimuli(grid_dir, sound_start=2.0), ["story"], {}).data["story"][:, 0]
    assert int(np.argmax(shifted)) == 2
    per_run = _stimuli(grid_dir, sound_start=2.0, sound_starts={"story": 4.0})
    assert int(np.argmax(NumWordsExtractor().extract(per_run, ["story"], {}).data["story"][:, 0])) == 4


def test_phoneme_histogram_counts_ah(grid_dir):
    assert "AH" in ARPABET_PHONEMES and len(set(ARPABET_PHONEMES)) == 39
    hist = PhonemeHistogramExtractor().extract(_stimuli(grid_dir), ["story"], {}).data["story"]
    assert hist[:, ARPABET_PHONEMES.index("AH")].max() > 0
    assert hist[:, ARPABET_PHONEMES.index("HH")].max() > 0
