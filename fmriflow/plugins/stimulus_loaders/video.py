"""VideoStimulusLoader — loads video metadata as VisualStim objects."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from fmriflow.core.types import StimulusData, StimRun, VisualStim
from fmriflow.plugins._decorators import stimulus_loader

_VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv")


@stimulus_loader("video")
class VideoStimulusLoader:
    """Loads video stimulus files and stores metadata (no frame decoding).

    Config::

        stimulus:
          loader: video
          path: /path/to/video/files
          tr: 2.0
          n_trs:
            run1: 200
            run2: 180
          modality: visual

    Each video file in ``stimulus.path`` becomes a run (filename stem is
    the run name).  Only metadata (path, fps, frame count) is stored;
    frames are decoded on demand by feature extractors.

    Requires ``opencv-python``::

        pip install fmriflow[video]
    """

    name = "video"

    PARAM_SCHEMA = {
        "path": {"type": "path", "required": True, "description": "Directory containing video files"},
        "tr": {"type": "float", "default": 2.0, "min": 0.1, "description": "TR duration in seconds"},
        "n_trs": {"type": "dict", "description": "TR counts per run (run_name → int)"},
        "language": {"type": "string", "default": "en", "enum": ["en", "zh", "es"], "description": "Stimulus language"},
        "modality": {"type": "string", "default": "visual", "enum": ["reading", "listening", "visual"], "description": "Stimulus modality"},
    }

    def load(self, config: dict) -> StimulusData:
        try:
            import cv2
        except ImportError:
            raise ImportError(
                "VideoStimulusLoader requires opencv-python. "
                "Install it with: pip install fmriflow[video]"
            )

        stim_cfg = config.get("stimulus", {})
        stim_dir = Path(stim_cfg["path"])
        tr = stim_cfg.get("tr", 2.0)
        n_trs_map = stim_cfg.get("n_trs", {})

        runs: dict[str, StimRun] = {}
        for video_path in sorted(stim_dir.iterdir()):
            if video_path.suffix.lower() not in _VIDEO_EXTENSIONS:
                continue

            run_name = video_path.stem
            cap = cv2.VideoCapture(str(video_path))
            try:
                fps = cap.get(cv2.CAP_PROP_FPS)
                n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            finally:
                cap.release()

            # Determine TR times
            if run_name in n_trs_map:
                n_trs = n_trs_map[run_name]
            else:
                duration = n_frames / fps if fps > 0 else 0.0
                n_trs = int(np.ceil(duration / tr))

            tr_times = np.arange(n_trs) * tr

            runs[run_name] = StimRun(
                name=run_name,
                stimulus=VisualStim(
                    video_path=video_path,
                    fps=fps,
                    n_frames=n_frames,
                    tr_times=tr_times,
                ),
                language=stim_cfg.get("language", "en"),
                modality=stim_cfg.get("modality", "visual"),
            )

        return StimulusData(runs=runs)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        stim_cfg = config.get("stimulus", {})
        if "path" not in stim_cfg:
            errors.append("video stimulus loader requires 'stimulus.path'")
        elif not Path(stim_cfg["path"]).is_dir():
            errors.append(
                f"stimulus.path '{stim_cfg['path']}' is not a directory"
            )
        return errors
