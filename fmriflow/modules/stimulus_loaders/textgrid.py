"""TextGridStimulusLoader — loads TextGrid + TRFile pairs."""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

from fmriflow.core.stimulus_utils import (
    TRFile,
    load_generic_trfiles,
    load_grids_for_stories,
    load_grids_for_stories_from_cloud,
    load_trfiles_from_cloud,
)
from fmriflow.core.types import LanguageStim, StimulusData, StimRun
from fmriflow.modules._decorators import stimulus_loader


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
        default ``$FMRIFLOW_DATA_DIR/stimuli/{experiment}/{session}/TextGrids``
        convention.
    trfile_dir : str, optional
        Explicit path to directory of .report files.  Overrides the
        default convention.
    file_suffix : str, optional
        When set, only load TextGrid/TRFile names ending with this suffix
        and strip it from the run name.  E.g. ``Audio_en`` turns
        ``storyAudio_en.TextGrid`` into run name ``story``.
    trfile_subject : str, optional
        When set alongside *file_suffix*, match trfiles named
        ``{story}{suffix}_{subject}_0.report`` and strip the extra parts.
        Useful when trfiles are per-subject.
    n_trs : dict[str, int], optional
        If no TRFiles are found, synthesize evenly-spaced triggers using
        this per-run TR count.  Keys are run names, values are ints.
    tr : float, optional
        TR duration in seconds for synthetic triggers (default 2.0).
    """

    name = "textgrid"

    PARAM_SCHEMA = {
        "language": {"type": "string", "default": "en", "enum": ["en", "zh", "es"], "description": "Stimulus language"},
        "modality": {"type": "string", "default": "reading", "enum": ["reading", "listening", "visual"], "description": "Stimulus modality"},
        "sessions": {"type": "list[string]", "default": ["generic"], "description": "Session labels"},
        "source": {"type": "string", "default": "local", "enum": ["local", "cloud"], "description": "Where to load stimulus files from"},
        "file_suffix": {"type": "string", "description": "Filter and rename TextGrid files by suffix"},
        "trfile_subject": {"type": "string", "description": "Match TRFiles per-subject"},
        "n_trs": {"type": "dict", "description": "Synthetic TR counts per run (run_name → int)"},
        "tr": {"type": "float", "default": 2.0, "min": 0.1, "description": "TR duration in seconds for synthetic triggers"},
    }

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

        # Filter and rename by file_suffix (e.g. "Audio_en")
        suffix = stim_cfg.get('file_suffix', '')
        if suffix:
            grids = {
                name[:-len(suffix)]: grid
                for name, grid in grids.items()
                if name.endswith(suffix)
            }
            trfile_subject = stim_cfg.get('trfile_subject', '')
            if trfile_subject:
                target = f"{suffix}_{trfile_subject}_0"
                trfiles = {
                    name[:-len(target)]: trf
                    for name, trf in trfiles.items()
                    if name.endswith(target)
                }
            else:
                trfiles = {
                    name[:-len(suffix)]: trf
                    for name, trf in trfiles.items()
                    if name.endswith(suffix)
                }

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

        # Log loaded stimuli summary
        if suffix:
            logger.info("file_suffix=%s  trfile_subject=%s",
                        suffix, stim_cfg.get('trfile_subject', '(none)'))
        logger.info("Loaded %d grids, %d trfiles, %d matched runs",
                    len(grids), len(trfiles), len(runs))
        for run_name in sorted(runs):
            trf = runs[run_name].stimulus.trfile
            n_trs = trf.n_trs if hasattr(trf, 'n_trs') else len(trf.get_reltriggertimes())
            grid = runs[run_name].stimulus.textgrid
            n_tiers = len(grid.tiers) if hasattr(grid, 'tiers') else '?'
            logger.info("  %-30s  trs=%d  tiers=%s", run_name, n_trs, n_tiers)

        return StimulusData(runs=runs)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'experiment' not in config:
            errors.append("'experiment' is required")
        return errors
