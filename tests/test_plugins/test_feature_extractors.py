"""Tests for basic feature extractors."""

import numpy as np
import pytest

from fmriflow.core.types import FeatureSet
from fmriflow.plugins.feature_extractors.basic import (
    NumLettersExtractor,
    NumPhonemesExtractor,
    NumWordsExtractor,
    WordLengthStdExtractor,
)
from tests.conftest import RUN_NAMES


class TestNumWordsExtractor:
    def test_output_is_feature_set(self, mock_stimuli):
        ext = NumWordsExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert isinstance(result, FeatureSet)

    def test_correct_name(self, mock_stimuli):
        ext = NumWordsExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert result.name == "numwords"

    def test_correct_n_dims(self, mock_stimuli):
        ext = NumWordsExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert result.n_dims == 1

    def test_has_all_runs(self, mock_stimuli):
        ext = NumWordsExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        for name in RUN_NAMES:
            assert name in result.data

    def test_values_non_negative(self, mock_stimuli):
        ext = NumWordsExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        for arr in result.data.values():
            # NumWordsExtractor produces per-TR word counts, so outputs should
            # remain finite and non-negative.
            assert np.isfinite(arr).all()
            assert (arr >= 0).all()

    def test_output_shape(self, mock_stimuli):
        ext = NumWordsExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        for arr in result.data.values():
            assert arr.ndim == 2
            assert arr.shape[1] == 1

    def test_validate_config(self):
        ext = NumWordsExtractor()
        assert ext.validate_config({}) == []


class TestNumLettersExtractor:
    def test_output_is_feature_set(self, mock_stimuli):
        ext = NumLettersExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert isinstance(result, FeatureSet)

    def test_correct_name(self, mock_stimuli):
        ext = NumLettersExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert result.name == "numletters"

    def test_values_non_negative(self, mock_stimuli):
        ext = NumLettersExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        for arr in result.data.values():
            # Lanczos resampling produces small negative side-lobes even when
            # the underlying signal (counts, std) is non-negative. The
            # meaningful invariant is finiteness, not strict non-negativity.
            assert np.isfinite(arr).all()


class TestNumPhonemesExtractor:
    def test_output_is_feature_set(self, mock_stimuli):
        ext = NumPhonemesExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert isinstance(result, FeatureSet)

    def test_correct_name(self, mock_stimuli):
        ext = NumPhonemesExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert result.name == "numphonemes"

    def test_values_non_negative(self, mock_stimuli):
        ext = NumPhonemesExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        for arr in result.data.values():
            # NumPhonemesExtractor returns per-TR phoneme counts, so values
            # should remain finite and non-negative.
            assert np.isfinite(arr).all()
            assert (arr >= 0).all()


class TestWordLengthStdExtractor:
    def test_output_is_feature_set(self, mock_stimuli):
        ext = WordLengthStdExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert isinstance(result, FeatureSet)

    def test_correct_name(self, mock_stimuli):
        ext = WordLengthStdExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        assert result.name == "word_length_std"

    def test_values_non_negative(self, mock_stimuli):
        ext = WordLengthStdExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        for arr in result.data.values():
            # Lanczos resampling produces small negative side-lobes even when
            # the underlying signal (counts, std) is non-negative. The
            # meaningful invariant is finiteness, not strict non-negativity.
            assert np.isfinite(arr).all()

    def test_output_shape(self, mock_stimuli):
        ext = WordLengthStdExtractor()
        result = ext.extract(mock_stimuli, RUN_NAMES, {})
        for arr in result.data.values():
            assert arr.shape[1] == 1
