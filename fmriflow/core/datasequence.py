"""DataSequence — time-aligned data container.

Handles data that is both continuous and discretely chunked,
e.g. word-level features aligned to fMRI TRs.

Preserved from v1 DataSequence.py with a clean interface.
"""

from __future__ import annotations

import itertools as itools

import numpy as np
from scipy.interpolate import interp1d


class DataSequence:
    """Data container for continuous data with discrete chunk boundaries.

    Parameters
    ----------
    data : array-like
        The data values (e.g., word embeddings, phoneme labels).
    split_inds : array-like
        Indices where data is split into TR chunks.
    data_times : array-like, optional
        Timestamps for each data element.
    tr_times : array-like, optional
        Timestamps for each TR boundary.
    """

    def __init__(self, data, split_inds, data_times=None, tr_times=None):
        self.data = data
        self.split_inds = split_inds
        self.data_times = data_times
        self.tr_times = tr_times

    def chunks(self):
        """Split data into discrete TR chunks.

        Returns
        -------
        list of ndarray
            One array per TR.
        """
        return np.split(self.data, self.split_inds)

    def chunksums(self, interp="rect", **kwargs):
        """Split data into chunks and aggregate.

        Parameters
        ----------
        interp : str
            Interpolation method: "lanczos", "sinc", "mean", or "rect" (default).

        Returns
        -------
        ndarray, shape (n_trs, n_dims)
            Aggregated data per TR.
        """
        if interp == "lanczos":
            return lanczosinterp2D(self.data, self.data_times, self.tr_times, **kwargs)
        elif interp == "sinc":
            return sincinterp2D(self.data, self.data_times, self.tr_times, **kwargs)
        elif interp == "mean":
            chunks = self.chunks()
            return np.array([
                np.mean(c, axis=0) if len(c) > 0 else np.zeros(self.data.shape[1:])
                for c in chunks
            ])
        else:
            # rect filter: sum over each chunk
            chunks = self.chunks()
            return np.array([
                np.sum(c, axis=0) if len(c) > 0 else np.zeros(self.data.shape[1:])
                for c in chunks
            ])

    def chunkstds(self):
        """Get standard deviation within each chunk.

        Returns
        -------
        ndarray, shape (n_chunks, n_dims)
        """
        dsize = self.data.shape[1]
        outmat = np.zeros((len(self.split_inds) + 1, dsize))
        for ci, c in enumerate(self.chunks()):
            if len(c):
                outmat[ci] = np.vstack(c).std(0)
        return outmat

    def data_to_chunk_ind(self, data_ind):
        """Find which chunk contains the given data index."""
        for ci, si in enumerate(self.split_inds):
            if data_ind < si:
                return ci
        return len(self.split_inds)

    def chunk_to_data_ind(self, chunk_ind):
        """Get the range of data indices for a given chunk."""
        start = self.split_inds[chunk_ind - 1] if chunk_ind > 0 else 0
        end = (self.split_inds[chunk_ind]
               if chunk_ind < len(self.split_inds) else len(self.data))
        return start, end

    def copy(self):
        """Return a shallow copy."""
        return DataSequence(
            self.data.copy() if hasattr(self.data, 'copy') else list(self.data),
            np.array(self.split_inds).copy(),
            self.data_times.copy() if self.data_times is not None else None,
            self.tr_times.copy() if self.tr_times is not None else None,
        )

    @classmethod
    def from_chunks(cls, chunks):
        """Create a DataSequence from a list of chunks.

        Inverse of `.chunks()`.
        """
        lens = list(map(len, chunks))
        split_inds = np.cumsum(lens)[:-1]
        data = list(itools.chain(*[list(c) for c in chunks]))
        return cls(data, split_inds)

    @classmethod
    def from_grid(cls, grid_transcript, trfile, word_time="middle"):
        """Create a DataSequence from a TextGrid transcript and TRFile.

        Parameters
        ----------
        grid_transcript : list of (start, stop, word)
            Parsed TextGrid transcript.
        trfile : TRFile
            TR timing information.
        word_time : str
            How to assign word times: "start", "middle", or "end".
        """
        words = list(map(str.lower, list(zip(*grid_transcript))[2]))
        word_starts = np.array(list(map(float, list(zip(*grid_transcript))[0])))
        word_ends = np.array(list(map(float, list(zip(*grid_transcript))[1])))

        if word_time == "start":
            word_times = word_starts
        elif word_time == "end":
            word_times = word_ends
        else:  # middle
            word_times = (word_starts + word_ends) / 2.0

        tr = trfile.avgtr
        trtimes = trfile.get_reltriggertimes()

        split_inds = [(word_starts < (t + tr)).sum() for t in trtimes][:-1]
        return cls(words, split_inds, word_times, trtimes + tr / 2.0)


def make_word_ds(textgrid, trfile):
    """Create a word-level DataSequence from a TextGrid and TRFile.

    Parameters
    ----------
    textgrid : TextGrid or parsed transcript
        If a TextGrid object, extracts the word tier.
        If already a list of (start, stop, word), uses directly.
    trfile : TRFile
        TR timing information.

    Returns
    -------
    DataSequence
        Word-level data sequence aligned to TRs.
    """
    if hasattr(textgrid, 'tiers'):
        # Raw TextGrid object — parse the word tier
        transcript = _parse_grid_transcript(textgrid)
    else:
        transcript = textgrid

    return DataSequence.from_grid(transcript, trfile)


def make_phoneme_ds(textgrid, trfile):
    """Create a phoneme-level DataSequence from a TextGrid and TRFile.

    Parameters
    ----------
    textgrid : TextGrid or parsed transcript
        If a TextGrid object, extracts the phoneme tier.
    trfile : TRFile
        TR timing information.

    Returns
    -------
    DataSequence
        Phoneme-level data sequence aligned to TRs.
    """
    if hasattr(textgrid, 'tiers'):
        transcript = _parse_phoneme_transcript(textgrid)
    else:
        transcript = textgrid

    return DataSequence.from_grid(transcript, trfile)


_BAD_WORDS = frozenset([
    'br', 'lg', 'ls', 'ns', 'sp', 'ig', 'cg', 'sl', '', 'ls)', '(br',
    'ns_ap', 'sil', 'sentence_start', 'sentence_end', 'sentence start',
    'clause_start', 'clause_end', 'paragraph_start', 'paragraph_end',
])


def _parse_grid_transcript(textgrid):
    """Extract word-level transcript from a TextGrid object."""
    # TextGrid word tier is typically tier index 1
    word_tier = textgrid.tiers[1] if len(textgrid.tiers) > 1 else textgrid.tiers[0]
    transcript = word_tier.make_simple_transcript()
    return [(s, e, w) for s, e, w in transcript
            if w.lower().strip("{}[]").strip() not in _BAD_WORDS]


def _parse_phoneme_transcript(textgrid):
    """Extract phoneme-level transcript from a TextGrid object."""
    # Phoneme tier is typically tier index 0
    phone_tier = textgrid.tiers[0]
    transcript = phone_tier.make_simple_transcript()
    return [(s, e, p) for s, e, p in transcript
            if p.lower().strip("{}[]").strip() not in _BAD_WORDS]


# ─── Interpolation helpers ───────────────────────────────────────

def _lanczosfun(cutoff, t, window=3):
    """Lanczos kernel function.

    Ported from text_lite.regression.interpdata.lanczosfun.
    """
    t = t * cutoff
    val = window * np.sin(np.pi * t) * np.sin(np.pi * t / window) / (np.pi**2 * t**2)
    val[t == 0] = 1.0
    val[np.abs(t) > window] = 0.0
    return val


def lanczosinterp2D(data, oldtime, newtime, window=3):
    """Lanczos interpolation for 2D data.

    Ported from text_lite.regression.interpdata.lanczosinterp2D.

    Parameters
    ----------
    data : ndarray, shape (n_samples, n_dims)
    oldtime : array-like, shape (n_samples,)
    newtime : array-like, shape (n_new,)
    window : int
        Lanczos window size (number of lobes).

    Returns
    -------
    ndarray, shape (n_new, n_dims)
    """
    data = np.atleast_2d(data)
    if data.shape[0] == 1:
        data = data.T

    oldtime = np.array(oldtime, dtype=float)
    newtime = np.array(newtime, dtype=float)

    cutoff = 1.0 / np.mean(np.diff(newtime))

    sincmat = np.zeros((len(newtime), len(oldtime)))
    for ndi in range(len(newtime)):
        sincmat[ndi, :] = _lanczosfun(cutoff, newtime[ndi] - oldtime, window)

    return np.dot(sincmat, data)


def sincinterp2D(data, oldtime, newtime, **kwargs):
    """Sinc interpolation for 2D data (falls back to linear interp1d)."""
    data = np.atleast_2d(data)
    if data.shape[0] == 1:
        data = data.T

    oldtime = np.array(oldtime, dtype=float)
    newtime = np.array(newtime, dtype=float)

    f = interp1d(oldtime, data, axis=0, kind='linear',
                 bounds_error=False, fill_value=0.0)
    return f(newtime)
