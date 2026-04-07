"""Histogram feature extractors: english1000, letters, phonemes."""

from __future__ import annotations

import string

import numpy as np

# Punctuation characters to strip from words (matches original pipeline)
_PUNCT_CHARS = string.punctuation + '{}[]'

from fmriflow.core.datasequence import (
    DataSequence, make_phoneme_ds, make_word_ds,
)
from fmriflow.core.types import FeatureSet, StimulusData
from fmriflow.plugins._decorators import feature_extractor

# ARPAbet phoneme set (39 phonemes)
ARPABET_PHONEMES = [
    'AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'B', 'CH', 'D', 'DH',
    'EH', 'ER', 'EY', 'F', 'G', 'HH', 'IH', 'IY', 'JH', 'K',
    'L', 'M', 'N', 'NG', 'OW', 'OY', 'P', 'R', 'S', 'SH',
    'T', 'TH', 'UH', 'UW', 'V', 'W', 'Y', 'Z', 'ZH',
]


@feature_extractor("english1000")
class English1000Extractor:
    """Dense english1000 word embeddings per TR.

    Loads 985-dim dense embeddings from ``data/english1000.npz`` and
    downsamples via Lanczos interpolation, matching the original v1
    ``Features.lexical_embeddings(embedding_name='english1000')``.
    """

    name = "english1000"
    n_dims = 985
    PARAM_SCHEMA = {}

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        embedding_dict, default_emb = self._load_embeddings()
        n_dims = len(default_emb)

        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)
            embeddings = np.zeros((len(wordseq.data), n_dims))
            for i, word in enumerate(wordseq.data):
                w = str(word).lower().strip(_PUNCT_CHARS).strip()
                embeddings[i] = embedding_dict.get(w, default_emb)
            ds = DataSequence(embeddings, wordseq.split_inds,
                              wordseq.data_times, wordseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        self.n_dims = n_dims
        return FeatureSet(name=self.name, data=data, n_dims=n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []

    def _load_embeddings(self):
        """Load dense embeddings from ``data/english1000.npz``."""
        from pathlib import Path
        npz_path = Path(__file__).resolve().parent.parent.parent / 'data' / 'english1000.npz'
        d = np.load(npz_path)
        keys, values = d['keys'], d['values']
        embedding_dict = {k: v for k, v in zip(keys, values)}
        default_emb = np.zeros(values.shape[1])
        return embedding_dict, default_emb


@feature_extractor("letters")
class LetterHistogramExtractor:
    """Letter frequency histogram per TR. Wraps Features.letters()."""

    name = "letters"
    n_dims = 26
    PARAM_SCHEMA = {}

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        letter_to_idx = {c: i for i, c in enumerate(string.ascii_lowercase)}

        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)

            # Build per-word letter histograms
            embeddings = np.zeros((len(wordseq.data), self.n_dims))
            for i, word in enumerate(wordseq.data):
                for c in str(word).lower():
                    if c in letter_to_idx:
                        embeddings[i, letter_to_idx[c]] += 1.0

            ds = DataSequence(embeddings, wordseq.split_inds,
                              wordseq.data_times, wordseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []


@feature_extractor("phonemes")
class PhonemeHistogramExtractor:
    """Phoneme histogram per TR. Wraps Features.phonemes()."""

    name = "phonemes"
    n_dims = 39  # ARPAbet phoneme set
    PARAM_SCHEMA = {}

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        phone_to_idx = {p: i for i, p in enumerate(ARPABET_PHONEMES)}

        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            phonseq = make_phoneme_ds(stim_run.textgrid, stim_run.trfile)

            # Build per-phoneme histograms
            embeddings = np.zeros((len(phonseq.data), self.n_dims))
            for i, phone in enumerate(phonseq.data):
                # Strip stress markers (e.g., 'AH0' -> 'AH')
                p = str(phone).strip().upper().rstrip('012')
                if p in phone_to_idx:
                    embeddings[i, phone_to_idx[p]] = 1.0

            ds = DataSequence(embeddings, phonseq.split_inds,
                              phonseq.data_times, phonseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []
