"""AudioStimulusLoader — loads WAV files as AudioStim objects."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from fmriflow.core.types import AudioStim, StimulusData, StimRun
from fmriflow.modules._decorators import stimulus_loader


@stimulus_loader("audio")
class AudioStimulusLoader:
    """Loads audio stimulus files (.wav) from a directory.

    Config::

        stimulus:
          loader: audio
          path: /path/to/wav/files
          tr: 2.0
          n_trs:
            run1: 200
            run2: 180
          modality: listening

    Each ``.wav`` file in ``stimulus.path`` becomes a run (filename stem
    is the run name).  TR onset times are synthesized from ``n_trs`` and
    ``tr``.

    Requires the ``librosa`` and ``soundfile`` packages::

        pip install fmriflow[audio]
    """

    name = "audio"

    PARAM_SCHEMA = {
        "path": {"type": "path", "required": True, "description": "Directory containing .wav files"},
        "tr": {"type": "float", "default": 2.0, "min": 0.1, "description": "TR duration in seconds"},
        "n_trs": {"type": "dict", "description": "TR counts per run (run_name → int)"},
        "language": {"type": "string", "default": "en", "enum": ["en", "zh", "es"], "description": "Stimulus language"},
        "modality": {"type": "string", "default": "listening", "enum": ["reading", "listening", "visual"], "description": "Stimulus modality"},
    }

    def load(self, config: dict) -> StimulusData:
        try:
            import librosa
        except ImportError:
            raise ImportError(
                "AudioStimulusLoader requires librosa. "
                "Install it with: pip install fmriflow[audio]"
            )

        stim_cfg = config.get("stimulus", {})
        stim_dir = Path(stim_cfg["path"])
        tr = stim_cfg.get("tr", 2.0)
        n_trs_map = stim_cfg.get("n_trs", {})

        runs: dict[str, StimRun] = {}
        for wav_path in sorted(stim_dir.glob("*.wav")):
            run_name = wav_path.stem
            waveform, sr = librosa.load(wav_path, sr=None, mono=True)

            # Determine TR times
            if run_name in n_trs_map:
                n_trs = n_trs_map[run_name]
            else:
                # Infer from audio duration
                duration = len(waveform) / sr
                n_trs = int(np.ceil(duration / tr))

            tr_times = np.arange(n_trs) * tr

            runs[run_name] = StimRun(
                name=run_name,
                stimulus=AudioStim(
                    waveform=waveform,
                    sample_rate=sr,
                    tr_times=tr_times,
                ),
                language=stim_cfg.get("language", "en"),
                modality=stim_cfg.get("modality", "listening"),
            )

        return StimulusData(runs=runs)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        stim_cfg = config.get("stimulus", {})
        if "path" not in stim_cfg:
            errors.append("audio stimulus loader requires 'stimulus.path'")
        elif not Path(stim_cfg["path"]).is_dir():
            errors.append(
                f"stimulus.path '{stim_cfg['path']}' is not a directory"
            )
        return errors
