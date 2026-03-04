"""TextGridStimulusLoader — loads TextGrid + TRFile pairs."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.stimulus_utils import (
    TRFile,
    load_generic_trfiles,
    load_grids_for_stories,
    load_grids_for_stories_from_cloud,
    load_trfiles_from_cloud,
)
from denizenspipeline.core.types import LanguageStim, StimulusData, StimRun
from denizenspipeline.plugins._decorators import stimulus_loader


class _SyntheticTRFile:
    """Stand-in TRFile with evenly spaced trigger times.

    Used when no .report files exist (e.g. reading experiments where
    TRs are uniform).  Requires ``n_trs`` and ``tr`` in the stimulus
    config.
    """

    def __init__(self, n_trs: int, tr: float = 2.0):
        self._times = np.arange(n_trs) * tr

    def get_reltriggertimes(self):
        return self._times


@stimulus_loader("textgrid")
class TextGridStimulusLoader:
    """Loads TextGrid + TRFile pairs from local disk or cloud.

    Config keys
    -----------
    textgrid_dir : str, optional
        Explicit path to directory of .TextGrid files. Overrides the
        default ``$DENIZENS_DATA_DIR/stimuli/{experiment}/{session}/TextGrids``
        convention.
    trfile_dir : str, optional
        Explicit path to directory of .report files.  Overrides the
        default convention.
    n_trs : dict[str, int], optional
        If no TRFiles are found, synthesize evenly-spaced triggers using
        this per-run TR count.  Keys are run names, values are ints.
    tr : float, optional
        TR duration in seconds for synthetic triggers (default 2.0).
    """

    name = "textgrid"

    def load(self, config: dict) -> StimulusData:
        stim_cfg = config.get('stimulus', {})
        sessions = stim_cfg.get('sessions', ['generic'])
        experiment = config['experiment']
        source = stim_cfg.get('source', 'local')

        grids = {}
        trfiles = {}

        textgrid_dir = stim_cfg.get('textgrid_dir')
        trfile_dir = stim_cfg.get('trfile_dir')

        for session in sessions:
            if source == 'cloud':
                grids.update(load_grids_for_stories_from_cloud(
                    experiment, session))
                trfiles.update(load_trfiles_from_cloud(
                    experiment, session))
            else:
                grids.update(load_grids_for_stories(
                    experiment, session, grid_dir=textgrid_dir))
                trfiles.update(load_generic_trfiles(
                    experiment, session, tr_dir=trfile_dir))

        # Synthesize TRFiles for any grid that has no matching .report
        n_trs_map = stim_cfg.get('n_trs', {})
        tr = stim_cfg.get('tr', 2.0)
        for run_name in grids:
            if run_name not in trfiles and run_name in n_trs_map:
                trfiles[run_name] = _SyntheticTRFile(n_trs_map[run_name], tr)

        runs = {}
        for run_name in grids:
            if run_name in trfiles:
                runs[run_name] = StimRun(
                    name=run_name,
                    stimulus=LanguageStim(
                        textgrid=grids[run_name],
                        trfile=trfiles[run_name],
                    ),
                    language=stim_cfg.get('language', 'en'),
                    modality=stim_cfg.get('modality', 'reading'),
                )

        return StimulusData(runs=runs)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'experiment' not in config:
            errors.append("'experiment' is required")
        return errors
