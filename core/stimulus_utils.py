"""Stimulus loading utilities: TextGrids, TRFiles, transcript parsing.

Standalone implementations based on v1 stimulus_utils.py patterns.
"""

from __future__ import annotations

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
        data_dir = os.environ.get('DENIZENS_DATA_DIR', '.')
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
        data_dir = os.environ.get('DENIZENS_DATA_DIR', '.')
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
        bucket = os.environ.get('DENIZENS_S3_BUCKET', 'glab-denizens-shared')
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
        bucket = os.environ.get('DENIZENS_S3_BUCKET', 'glab-denizens-shared')
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
        bad_words = {"", "sp", "SIL", "{SL}", "{sub23}", "{NS}", "{BR}", "{CG}"}

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

    try:
        import tgt
        return tgt.io.read_textgrid(filepath)
    except ImportError:
        pass

    # Fallback: return a minimal wrapper
    return _SimpleTextGrid(filepath)


class _SimpleTextGrid:
    """Minimal TextGrid parser as fallback when no TextGrid library is available."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.tiers = []
        self._parse(filepath)

    def _parse(self, filepath):
        """Parse a Praat TextGrid file."""
        import codecs
        with codecs.open(filepath, 'r', 'utf-8') as f:
            content = f.read()

        # Simple parser for interval tiers
        tier = _SimpleTier()
        in_intervals = False
        current_start = current_end = None
        current_text = None

        for line in content.split('\n'):
            line = line.strip()
            if 'intervals' in line and '[' in line:
                in_intervals = True
            elif in_intervals:
                if line.startswith('xmin'):
                    current_start = line.split('=')[1].strip()
                elif line.startswith('xmax'):
                    current_end = line.split('=')[1].strip()
                elif line.startswith('text'):
                    current_text = line.split('=', 1)[1].strip().strip('"')
                    if current_start is not None:
                        tier.intervals.append((current_start, current_end, current_text))
                    current_start = current_end = current_text = None

        if tier.intervals:
            self.tiers.append(tier)


class _SimpleTier:
    """Minimal tier representation."""

    def __init__(self):
        self.intervals = []

    def make_simple_transcript(self):
        return list(self.intervals)
