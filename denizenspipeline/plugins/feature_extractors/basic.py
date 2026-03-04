"""Basic feature extractors: numwords, numletters, numphonemes, word_length_std."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.datasequence import make_phoneme_ds, make_word_ds
from denizenspipeline.core.types import FeatureSet, StimulusData
from denizenspipeline.plugins._decorators import feature_extractor


@feature_extractor("numwords")
class NumWordsExtractor:
    """Count of words per TR. Wraps Features.numwords()."""

    name = "numwords"
    n_dims = 1

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)
            counts = np.atleast_2d(
                [len(chunk) for chunk in wordseq.chunks()]
            ).T.astype(float)
            data[run_name] = counts
        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []


@feature_extractor("numletters")
class NumLettersExtractor:
    """Total letter count per TR. Wraps Features.numletters()."""

    name = "numletters"
    n_dims = 1

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)
            lengths = np.atleast_2d(
                [sum(len(w) for w in chunk) for chunk in wordseq.chunks()]
            ).T.astype(float)
            data[run_name] = lengths
        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []


@feature_extractor("numphonemes")
class NumPhonemesExtractor:
    """Count of phonemes per TR. Wraps Features.numphonemes()."""

    name = "numphonemes"
    n_dims = 1

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            phonseq = make_phoneme_ds(stim_run.textgrid, stim_run.trfile)
            counts = np.atleast_2d(
                [len(chunk) for chunk in phonseq.chunks()]
            ).T.astype(float)
            data[run_name] = counts
        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []


@feature_extractor("word_length_std")
class WordLengthStdExtractor:
    """Standard deviation of word lengths per TR."""

    name = "word_length_std"
    n_dims = 1

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)
            stds = np.atleast_2d([
                np.std([len(w) for w in chunk]) if len(chunk) > 0 else 0.0
                for chunk in wordseq.chunks()
            ]).T.astype(float)
            data[run_name] = stds
        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []
