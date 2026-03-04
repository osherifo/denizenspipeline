"""Visual feature extractors: luminance, motion_energy."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.alignment import align_to_trs
from denizenspipeline.core.types import FeatureSet, StimulusData, VisualStim
from denizenspipeline.plugins._decorators import feature_extractor


def _require_visual(stim_run, extractor_name: str) -> VisualStim:
    """Return the VisualStim or raise TypeError."""
    if not isinstance(stim_run.stimulus, VisualStim):
        raise TypeError(
            f"{extractor_name} requires VisualStim, "
            f"got {type(stim_run.stimulus).__name__}"
        )
    return stim_run.stimulus


def _read_frames_gray(video_path, n_frames: int) -> np.ndarray:
    """Read all frames as grayscale uint8 arrays.

    Returns
    -------
    list of np.ndarray
        Each element is a grayscale frame, shape ``(height, width)``.
    """
    try:
        import cv2
    except ImportError:
        raise ImportError(
            "Visual feature extractors require opencv-python. "
            "Install it with: pip install denizenspipeline[video]"
        )

    cap = cv2.VideoCapture(str(video_path))
    frames = []
    try:
        for _ in range(n_frames):
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    finally:
        cap.release()

    return frames


@feature_extractor("luminance")
class LuminanceExtractor:
    """Mean frame luminance averaged per TR."""

    name = "luminance"
    n_dims = 1

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        data = {}
        for run_name in run_names:
            stim = _require_visual(stimuli.runs[run_name], self.name)
            frames = _read_frames_gray(stim.video_path, stim.n_frames)

            lum = np.array([f.mean() for f in frames], dtype=float)
            frame_times = np.arange(len(frames)) / stim.fps

            data[run_name] = align_to_trs(
                lum.reshape(-1, 1), frame_times, stim.tr_times,
            )

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []


@feature_extractor("motion_energy")
class MotionEnergyExtractor:
    """Frame-differencing motion energy averaged per TR."""

    name = "motion_energy"
    n_dims = 1

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        data = {}
        for run_name in run_names:
            stim = _require_visual(stimuli.runs[run_name], self.name)
            frames = _read_frames_gray(stim.video_path, stim.n_frames)

            # Motion energy = mean absolute difference between consecutive frames
            motion = np.zeros(len(frames), dtype=float)
            for i in range(1, len(frames)):
                diff = np.abs(
                    frames[i].astype(float) - frames[i - 1].astype(float)
                )
                motion[i] = diff.mean()

            frame_times = np.arange(len(frames)) / stim.fps

            data[run_name] = align_to_trs(
                motion.reshape(-1, 1), frame_times, stim.tr_times,
            )

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []
