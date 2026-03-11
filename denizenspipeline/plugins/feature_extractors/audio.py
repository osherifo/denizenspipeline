"""Audio feature extractors: mel_spectrogram, rms_energy."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.alignment import align_to_trs
from denizenspipeline.core.types import AudioStim, FeatureSet, StimulusData
from denizenspipeline.plugins._decorators import feature_extractor


def _require_audio(stim_run, extractor_name: str) -> AudioStim:
    """Return the AudioStim or raise TypeError."""
    if not isinstance(stim_run.stimulus, AudioStim):
        raise TypeError(
            f"{extractor_name} requires AudioStim, "
            f"got {type(stim_run.stimulus).__name__}"
        )
    return stim_run.stimulus


@feature_extractor("mel_spectrogram")
class MelSpectrogramExtractor:
    """Mel spectrogram averaged per TR.

    Params
    ------
    n_mels : int
        Number of mel bands (default 128).
    """

    name = "mel_spectrogram"
    n_dims = 128  # default, overridden at extract time
    PARAM_SCHEMA = {
        "n_mels": {"type": "int", "default": 128, "min": 1, "description": "Number of mel frequency bands"},
    }

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        try:
            import librosa
        except ImportError:
            raise ImportError(
                "mel_spectrogram extractor requires librosa. "
                "Install it with: pip install denizenspipeline[audio]"
            )

        params = config.get("params", {})
        n_mels = params.get("n_mels", 128)

        data = {}
        for run_name in run_names:
            stim = _require_audio(stimuli.runs[run_name], self.name)

            mel = librosa.feature.melspectrogram(
                y=stim.waveform, sr=stim.sample_rate, n_mels=n_mels,
            )
            mel_db = librosa.power_to_db(mel, ref=np.max)  # (n_mels, n_frames)
            mel_db = mel_db.T  # (n_frames, n_mels)

            hop_length = 512  # librosa default
            frame_times = librosa.frames_to_time(
                np.arange(mel_db.shape[0]),
                sr=stim.sample_rate, hop_length=hop_length,
            )

            data[run_name] = align_to_trs(mel_db, frame_times, stim.tr_times)

        return FeatureSet(name=self.name, data=data, n_dims=n_mels)

    def validate_config(self, config: dict) -> list[str]:
        return []


@feature_extractor("rms_energy")
class RMSEnergyExtractor:
    """Root mean square energy averaged per TR."""

    name = "rms_energy"
    n_dims = 1
    PARAM_SCHEMA = {}

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        try:
            import librosa
        except ImportError:
            raise ImportError(
                "rms_energy extractor requires librosa. "
                "Install it with: pip install denizenspipeline[audio]"
            )

        data = {}
        for run_name in run_names:
            stim = _require_audio(stimuli.runs[run_name], self.name)

            rms = librosa.feature.rms(y=stim.waveform)  # (1, n_frames)
            rms = rms[0]  # (n_frames,)

            hop_length = 512
            frame_times = librosa.frames_to_time(
                np.arange(len(rms)),
                sr=stim.sample_rate, hop_length=hop_length,
            )

            data[run_name] = align_to_trs(
                rms.reshape(-1, 1), frame_times, stim.tr_times,
            )

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []
