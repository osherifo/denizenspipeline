"""SkipStimulusLoader — no-op loader for precomputed-feature workflows."""

from __future__ import annotations

from fmriflow.core.types import StimulusData
from fmriflow.plugins._decorators import stimulus_loader


@stimulus_loader("skip")
class SkipStimulusLoader:
    """Returns empty stimuli. Use when all features are precomputed.

    Any feature with ``source: compute`` will fail if stimuli are skipped,
    since compute sources need TextGrid data.  Features loaded from
    ``filesystem`` or ``cloud`` only need run names, which the orchestrator
    derives from the response data instead.

    Config::

        stimulus:
          loader: skip
    """

    name = "skip"

    PARAM_SCHEMA = {}

    def load(self, config: dict) -> StimulusData:
        return StimulusData(runs={})

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        for feat_cfg in config.get('features', []):
            if feat_cfg.get('source', 'compute') == 'compute':
                errors.append(
                    f"feature '{feat_cfg.get('name', '?')}' uses source: compute "
                    f"which requires stimuli, but stimulus loader is 'skip'")
        return errors
