"""Tests for DataSequence class."""

import numpy as np
import pytest

from fmriflow.core.datasequence import (
    DataSequence,
    make_phoneme_ds,
    make_word_ds,
)
from tests.conftest import MockTextGrid, MockTRFile


class TestDataSequenceChunks:
    def test_correct_split_count(self):
        data = np.arange(20)
        split_inds = [5, 10, 15]
        ds = DataSequence(data, split_inds)
        chunks = ds.chunks()
        assert len(chunks) == 4  # n_splits + 1

    def test_chunk_content(self):
        data = np.array([1, 2, 3, 4, 5, 6])
        split_inds = [3]
        ds = DataSequence(data, split_inds)
        chunks = ds.chunks()
        np.testing.assert_array_equal(chunks[0], [1, 2, 3])
        np.testing.assert_array_equal(chunks[1], [4, 5, 6])

    def test_empty_chunks(self):
        data = np.array([1, 2, 3])
        split_inds = [0, 0, 3]
        ds = DataSequence(data, split_inds)
        chunks = ds.chunks()
        assert len(chunks[0]) == 0
        assert len(chunks[1]) == 0


class TestDataSequenceChunksums:
    def test_rect_sums(self):
        data = np.array([[1.0], [2.0], [3.0], [4.0]])
        split_inds = [2]
        ds = DataSequence(data, split_inds)
        sums = ds.chunksums(interp="rect")
        np.testing.assert_allclose(sums[0], [3.0])
        np.testing.assert_allclose(sums[1], [7.0])

    def test_mean_interpolation(self):
        data = np.array([[2.0], [4.0], [6.0], [8.0]])
        split_inds = [2]
        ds = DataSequence(data, split_inds)
        means = ds.chunksums(interp="mean")
        np.testing.assert_allclose(means[0], [3.0])
        np.testing.assert_allclose(means[1], [7.0])


class TestDataSequenceFromChunks:
    def test_roundtrip(self):
        data = np.arange(12)
        split_inds = [3, 7]
        ds = DataSequence(data, split_inds)
        chunks = ds.chunks()
        ds2 = DataSequence.from_chunks(chunks)
        chunks2 = ds2.chunks()
        assert len(chunks) == len(chunks2)
        for c1, c2 in zip(chunks, chunks2):
            np.testing.assert_array_equal(c1, c2)


class TestDataSequenceIndices:
    def test_data_to_chunk_ind(self):
        data = np.arange(10)
        split_inds = [3, 6]
        ds = DataSequence(data, split_inds)
        assert ds.data_to_chunk_ind(0) == 0
        assert ds.data_to_chunk_ind(2) == 0
        assert ds.data_to_chunk_ind(3) == 1
        assert ds.data_to_chunk_ind(5) == 1
        assert ds.data_to_chunk_ind(6) == 2
        assert ds.data_to_chunk_ind(9) == 2

    def test_chunk_to_data_ind(self):
        data = np.arange(10)
        split_inds = [3, 6]
        ds = DataSequence(data, split_inds)
        assert ds.chunk_to_data_ind(0) == (0, 3)
        assert ds.chunk_to_data_ind(1) == (3, 6)
        assert ds.chunk_to_data_ind(2) == (6, 10)


class TestMakeWordDS:
    def test_with_mock_textgrid(self):
        tg = MockTextGrid(n_words=20)
        tr = MockTRFile(n_trs=10, duration=20.0)
        ds = make_word_ds(tg, tr)
        chunks = ds.chunks()
        # Should produce chunks aligned to TRs
        assert len(chunks) > 0
        # Total words across chunks should match (minus filtered bad_words)
        total = sum(len(c) for c in chunks)
        assert total > 0

    def test_with_raw_transcript(self):
        transcript = [
            ("0.0", "0.5", "hello"),
            ("0.5", "1.0", "world"),
            ("1.0", "1.5", "test"),
        ]
        tr = MockTRFile(n_trs=5, duration=2.0)
        ds = make_word_ds(transcript, tr)
        chunks = ds.chunks()
        assert len(chunks) > 0


class TestMakePhonemeDS:
    def test_with_mock_textgrid(self):
        tg = MockTextGrid(n_words=20)
        tr = MockTRFile(n_trs=10, duration=20.0)
        ds = make_phoneme_ds(tg, tr)
        chunks = ds.chunks()
        assert len(chunks) > 0
        total = sum(len(c) for c in chunks)
        assert total > 0


class TestDataSequenceCopy:
    def test_copy_independence(self):
        data = np.array([1.0, 2.0, 3.0, 4.0])
        ds = DataSequence(data, np.array([2]))
        ds2 = ds.copy()
        ds2.data[0] = 99.0
        assert ds.data[0] == 1.0
