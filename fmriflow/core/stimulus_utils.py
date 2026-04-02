"""Stimulus loading utilities: TextGrids, TRFiles, transcript parsing.

Standalone implementations based on v1 stimulus_utils.py patterns.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np


class TRFile:
    """Loads and parses trigger time report files from stimulus presentation.

    Parameters
    ----------
    trfilename : str or Path
        Path to the TR file.
    expectedtr : float
        Expected TR duration in seconds.
    """

    def __init__(self, trfilename, expectedtr=2.0045):
        self.expectedtr = expectedtr
        self.trtimes = []
        self.soundstarttime = -1.0
        self.soundstoptime = -1.0
        if trfilename:
            self.load_from_file(trfilename)

    def load_from_file(self, filepath):
        """Parse a TR timing report file."""
        filepath = str(filepath)
        with open(filepath, 'r') as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                time_val = float(parts[0])
                event = parts[1] if len(parts) > 1 else ""
                if event == "trigger" or "trigger" in line.lower():
                    self.trtimes.append(time_val)
                elif "sound" in line.lower() and "start" in line.lower():
                    self.soundstarttime = time_val
                elif "sound" in line.lower() and "stop" in line.lower():
                    self.soundstoptime = time_val

        self.trtimes = sorted(self.trtimes)

    def get_reltriggertimes(self):
        """Return trigger times relative to sound start.

        Returns
        -------
        ndarray
            Trigger times relative to sound onset.
        """
        return np.array(self.trtimes) - self.soundstarttime

    @property
    def avgtr(self):
        """Average TR duration."""
        if len(self.trtimes) < 2:
            return self.expectedtr
        return np.diff(self.trtimes).mean()

    @property
    def n_trs(self):
        """Number of TRs."""
        return len(self.trtimes)


def load_grids_for_stories(experiment, session, grid_dir=None):
    """Load TextGrid files for stories in an experiment.

    Parameters
    ----------
    experiment : str
        Experiment name.
    session : str
        Session name (e.g., 'generic').
    grid_dir : str or Path, optional
        Directory containing TextGrid files.

    Returns
    -------
    dict
        {story_name: TextGrid_object}
    """
    if grid_dir is None:
        data_dir = os.environ.get('FMRIFLOW_DATA_DIR', '.')
        grid_dir = Path(data_dir) / 'stimuli' / experiment / session / 'TextGrids'
    else:
        grid_dir = Path(grid_dir)

    grids = {}
    if grid_dir.exists():
        for f in sorted(grid_dir.glob('*.TextGrid')):
            name = f.stem
            grids[name] = _load_textgrid(f)

    return grids


def load_generic_trfiles(experiment, session, tr_dir=None, expectedtr=2.0045):
    """Load TRFile objects for stories in an experiment.

    Parameters
    ----------
    experiment : str
        Experiment name.
    session : str
        Session name.
    tr_dir : str or Path, optional
        Directory containing TR files.
    expectedtr : float
        Expected TR duration.

    Returns
    -------
    dict
        {story_name: TRFile_object}
    """
    if tr_dir is None:
        data_dir = os.environ.get('FMRIFLOW_DATA_DIR', '.')
        tr_dir = Path(data_dir) / 'stimuli' / experiment / session / 'trfiles'
    else:
        tr_dir = Path(tr_dir)

    trfiles = {}
    if tr_dir.exists():
        for f in sorted(tr_dir.glob('*.report')):
            name = f.stem
            trfiles[name] = TRFile(str(f), expectedtr=expectedtr)

    return trfiles


def load_grids_for_stories_from_cloud(experiment, session, bucket=None):
    """Load TextGrid files from S3 cloud storage.

    Parameters
    ----------
    experiment : str
        Experiment name.
    session : str
        Session name.
    bucket : str, optional
        S3 bucket name.

    Returns
    -------
    dict
        {story_name: TextGrid_object}
    """
    import cottoncandy as cc
    if bucket is None:
        bucket = os.environ.get('FMRIFLOW_S3_BUCKET', 'fmriflow-shared')
    cci = cc.get_interface(bucket)

    prefix = f"stimuli/{experiment}/{session}/TextGrids/"
    grids = {}
    for key in cci.ls(prefix):
        if key.endswith('.TextGrid'):
            name = Path(key).stem
            local_path = cci.download(key)
            grids[name] = _load_textgrid(local_path)

    return grids


def load_trfiles_from_cloud(experiment, session, bucket=None, expectedtr=2.0045):
    """Load TRFile objects from S3 cloud storage."""
    import cottoncandy as cc
    if bucket is None:
        bucket = os.environ.get('FMRIFLOW_S3_BUCKET', 'fmriflow-shared')
    cci = cc.get_interface(bucket)

    prefix = f"stimuli/{experiment}/{session}/trfiles/"
    trfiles = {}
    for key in cci.ls(prefix):
        if key.endswith('.report'):
            name = Path(key).stem
            local_path = cci.download(key)
            trfiles[name] = TRFile(str(local_path), expectedtr=expectedtr)

    return trfiles


def parse_grid(grid, remove_bad_words=False, replace_bad_words=True,
               bad_words=None):
    """Parse a TextGrid into a list of (start, stop, word) tuples.

    Parameters
    ----------
    grid : TextGrid
        Parsed TextGrid object.
    remove_bad_words : bool
        If True, remove non-speech entries.
    replace_bad_words : bool
        If True, replace artifacts with empty string.
    bad_words : set, optional
        Words to filter out.

    Returns
    -------
    list of (str, str, str)
        Parsed transcript entries.
    """
    if bad_words is None:
        bad_words = {"", "sp", "SIL", "{SL}", "{LG}", "{NS}", "{BR}", "{CG}"}

    # Get word tier (typically tier index 1)
    word_tier = grid.tiers[1] if len(grid.tiers) > 1 else grid.tiers[0]
    transcript = word_tier.make_simple_transcript()

    if remove_bad_words:
        transcript = [(s, e, w) for s, e, w in transcript if w.strip() not in bad_words]
    elif replace_bad_words:
        transcript = [(s, e, "" if w.strip() in bad_words else w) for s, e, w in transcript]
        transcript = [(s, e, w) for s, e, w in transcript if w]

    return transcript


def parse_grids(grids, **kwargs):
    """Parse a dictionary of TextGrids.

    Returns
    -------
    dict
        {story_name: parsed_transcript}
    """
    return {name: parse_grid(grid, **kwargs) for name, grid in grids.items()}


def _load_textgrid(filepath):
    """Load a TextGrid file. Returns a simple parsed representation."""
    filepath = str(filepath)
    try:
        import textgrids
        return textgrids.TextGrid(filepath)
    except ImportError:
        pass

    # Skip tgt — its strict overlap checking breaks on some TextGrids,
    # and its tier API differs from what the pipeline expects.

    # Fallback: return a minimal wrapper
    return _SimpleTextGrid(filepath)


class _SimpleTextGrid:
    """Minimal TextGrid parser as fallback when no TextGrid library is available."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.tiers = []
        self._parse(filepath)

    def _parse(self, filepath):
        """Parse a Praat TextGrid file (long-form, short-form, or chronological)."""
        import codecs
        with codecs.open(filepath, 'r', 'utf-8') as f:
            lines = f.read().split('\n')

        # Detect format from header
        header = lines[0].strip().strip('"') if lines else ''
        if header == 'Praat chronological TextGrid text file':
            self._parse_chronological(lines)
        elif any('item [' in ln for ln in lines):
            self._parse_long(lines)
        else:
            self._parse_short(lines)

    def _parse_long(self, lines):
        """Parse long-form TextGrid (with xmin=, xmax=, text= labels)."""
        import re
        tier = None
        in_intervals = False
        current_start = current_end = current_text = None

        for line in lines:
            stripped = line.strip()
            if re.match(r'item\s*\[\d+\]\s*:?\s*$', stripped):
                if tier is not None and tier.intervals:
                    self.tiers.append(tier)
                tier = _SimpleTier()
                in_intervals = False
                continue
            if tier is None:
                continue
            if 'intervals' in stripped and '[' in stripped:
                in_intervals = True
            elif in_intervals:
                if stripped.startswith('xmin'):
                    current_start = stripped.split('=')[1].strip()
                elif stripped.startswith('xmax'):
                    current_end = stripped.split('=')[1].strip()
                elif stripped.startswith('text') and '=' in stripped:
                    current_text = stripped.split('=', 1)[1].strip().strip('"')
                    if current_start is not None:
                        tier.intervals.append((current_start, current_end, current_text))
                    current_start = current_end = current_text = None

        if tier is not None and tier.intervals:
            self.tiers.append(tier)

    def _parse_short(self, lines):
        """Parse short-form TextGrid (bare values, no labels).

        Short-form layout per tier:
            "IntervalTier"
            "tier_name"
            xmin            (tier start)
            xmax            (tier end)
            n_intervals
            xmin_1          (interval start)
            xmax_1          (interval end)
            "text_1"
            ...repeating triplets
        """
        i = 0
        # Skip header lines until first "IntervalTier"
        while i < len(lines):
            if lines[i].strip().strip('"') == 'IntervalTier':
                break
            i += 1

        while i < len(lines):
            stripped = lines[i].strip().strip('"')
            if stripped == 'IntervalTier':
                tier = _SimpleTier()
                i += 1  # tier name
                i += 1  # tier xmin
                i += 1  # tier xmax
                i += 1  # n_intervals line
                if i >= len(lines):
                    break
                n_intervals = int(lines[i].strip())
                i += 1
                for _ in range(n_intervals):
                    if i + 2 >= len(lines):
                        break
                    xmin = lines[i].strip()
                    xmax = lines[i + 1].strip()
                    text = lines[i + 2].strip().strip('"')
                    tier.intervals.append((xmin, xmax, text))
                    i += 3
                self.tiers.append(tier)
            else:
                i += 1


    def _parse_chronological(self, lines):
        """Parse chronological TextGrid (interleaved intervals with tier index).

        Format:
            "Praat chronological TextGrid text file"
            xmin xmax   ! Time domain.
            n_tiers   ! Number of tiers.
            "IntervalTier" "name" xmin xmax    (one per tier)
            tier_index xmin xmax               (1-indexed)
            "text"
            ...repeating pairs
        """
        # Line 2: n_tiers
        n_tiers = int(lines[2].split()[0])
        tiers = [_SimpleTier() for _ in range(n_tiers)]

        # Skip header (3 lines) + tier declarations (n_tiers lines)
        i = 3 + n_tiers
        while i + 1 < len(lines):
            parts = lines[i].strip().split()
            if len(parts) >= 3:
                try:
                    tier_idx = int(parts[0]) - 1  # 1-indexed → 0-indexed
                    xmin = parts[1]
                    xmax = parts[2]
                    text = lines[i + 1].strip().strip('"')
                    if 0 <= tier_idx < n_tiers:
                        tiers[tier_idx].intervals.append((xmin, xmax, text))
                    i += 2
                    continue
                except (ValueError, IndexError):
                    pass
            i += 1

        self.tiers = [t for t in tiers if t.intervals]


class _SimpleTier:
    """Minimal tier representation."""

    def __init__(self):
        self.intervals = []

    def make_simple_transcript(self):
        return list(self.intervals)
