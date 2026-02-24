"""TextGridStimulusLoader — loads TextGrid + TRFile pairs."""

from __future__ import annotations

from denizenspipeline.core.stimulus_utils import (
    load_generic_trfiles,
    load_grids_for_stories,
    load_grids_for_stories_from_cloud,
    load_trfiles_from_cloud,
)
from denizenspipeline.core.types import StimulusData, StimRun


class TextGridStimulusLoader:
    """Loads TextGrid + TRFile pairs from local disk or cloud."""

    name = "textgrid"

    def load(self, config: dict) -> StimulusData:
        stim_cfg = config.get('stimulus', {})
        sessions = stim_cfg.get('sessions', ['generic'])
        experiment = config['experiment']
        source = stim_cfg.get('source', 'local')

        grids = {}
        trfiles = {}

        for session in sessions:
            if source == 'cloud':
                grids.update(load_grids_for_stories_from_cloud(
                    experiment, session))
                trfiles.update(load_trfiles_from_cloud(
                    experiment, session))
            else:
                grids.update(load_grids_for_stories(
                    experiment, session))
                trfiles.update(load_generic_trfiles(
                    experiment, session))

        runs = {}
        for run_name in grids:
            if run_name in trfiles:
                runs[run_name] = StimRun(
                    name=run_name,
                    textgrid=grids[run_name],
                    trfile=trfiles[run_name],
                    language=stim_cfg.get('language', 'en'),
                    modality=stim_cfg.get('modality', 'reading'),
                )

        return StimulusData(runs=runs)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'experiment' not in config:
            errors.append("'experiment' is required")
        return errors
