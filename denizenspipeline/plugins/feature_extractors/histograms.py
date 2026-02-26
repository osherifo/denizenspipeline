"""Histogram feature extractors: english1000, letters, phonemes."""

from __future__ import annotations

import string

import numpy as np

from denizenspipeline.core.datasequence import (
    DataSequence, make_phoneme_ds, make_word_ds,
)
from denizenspipeline.core.types import FeatureSet, StimulusData

# ARPAbet phoneme set (39 phonemes)
ARPABET_PHONEMES = [
    'AA', 'AE', 'sub20', 'AO', 'AW', 'AY', 'B', 'CH', 'D', 'DH',
    'EH', 'ER', 'EY', 'F', 'G', 'HH', 'IH', 'IY', 'JH', 'K',
    'L', 'M', 'N', 'NG', 'OW', 'OY', 'P', 'R', 'S', 'SH',
    'T', 'TH', 'UH', 'UW', 'V', 'W', 'Y', 'Z', 'ZH',
]


class English1000Extractor:
    """Top-1000 English word indicator features.

    Wraps Features.lexical_embeddings(embedding_name='english1000').
    """

    name = "english1000"
    n_dims = 985  # Actual count depends on the word list used

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        vocab = self._load_vocab()
        n_dims = len(vocab)
        word_to_idx = {w: i for i, w in enumerate(vocab)}

        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)
            embeddings = np.zeros((len(wordseq.data), n_dims))
            for i, word in enumerate(wordseq.data):
                w = str(word).lower().strip()
                if w in word_to_idx:
                    embeddings[i, word_to_idx[w]] = 1.0
            ds = DataSequence(embeddings, wordseq.split_inds,
                              wordseq.data_times, wordseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        self.n_dims = n_dims
        return FeatureSet(name=self.name, data=data, n_dims=n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []

    def _load_vocab(self):
        """Load the English top-word vocabulary list.

        Returns a list of the most common English words.
        Placeholder implementation using a basic frequency list.
        """
        # In production, this loads from a data file shipped with the package.
        # For now, return a basic set of common English words.
        try:
            from importlib.resources import files
            vocab_path = files('denizenspipeline') / 'data' / 'english1000.txt'
            if vocab_path.is_file():
                with open(vocab_path) as f:
                    return [line.strip() for line in f if line.strip()]
        except Exception:
            pass

        # Fallback: common English words (abbreviated for bootstrap)
        common = [
            'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
            'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
            'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her',
            'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there',
            'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get',
            'which', 'go', 'me',
        ]
        return common


class LetterHistogramExtractor:
    """Letter frequency histogram per TR. Wraps Features.letters()."""

    name = "letters"
    n_dims = 26

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


class PhonemeHistogramExtractor:
    """Phoneme histogram per TR. Wraps Features.phonemes()."""

    name = "phonemes"
    n_dims = 39  # ARPAbet phoneme set

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
                # Strip stress markers (e.g., 'AH0' -> 'sub20')
                p = str(phone).strip().upper().rstrip('012')
                if p in phone_to_idx:
                    embeddings[i, phone_to_idx[p]] = 1.0

            ds = DataSequence(embeddings, phonseq.split_inds,
                              phonseq.data_times, phonseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []
