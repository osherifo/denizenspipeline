"""Basic feature extractors: numwords, numletters, numphonemes, word_length_std."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.datasequence import DataSequence, make_phoneme_ds, make_word_ds
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
            chunks = wordseq.chunks()
            n_trs = len(wordseq.tr_times)
            counts = np.atleast_2d(
                [len(chunks[i]) for i in range(n_trs)]
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
            # Per-word letter counts as a DataSequence, then lanczos downsample
            newdata = np.vstack([len(w) for w in wordseq.data])
            ds = DataSequence(newdata, wordseq.split_inds,
                              wordseq.data_times, wordseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)
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
            chunks = phonseq.chunks()
            n_trs = len(phonseq.tr_times)
            counts = np.atleast_2d(
                [len(chunks[i]) for i in range(n_trs)]
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
            # Per-word letter counts as a DataSequence, then chunkstds
            newdata = np.vstack([len(w) for w in wordseq.data])
            ds = DataSequence(newdata, wordseq.split_inds,
                              wordseq.data_times, wordseq.tr_times)
            data[run_name] = ds.chunkstds()
        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []
