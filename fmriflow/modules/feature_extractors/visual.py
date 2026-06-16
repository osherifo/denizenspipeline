"""Visual feature extractors: luminance, motion_energy, clip."""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.alignment import align_to_trs
from fmriflow.core.types import (
    FeatureSet, ImageSeqStim, StimulusData, VisualStim,
)
from fmriflow.modules._decorators import feature_extractor

logger = logging.getLogger(__name__)


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
            "Install it with: pip install fmriflow[video]"
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
    PARAM_SCHEMA = {}

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


def _require_image_seq(stim_run, extractor_name: str) -> ImageSeqStim:
    """Return the ImageSeqStim or raise TypeError."""
    if not isinstance(stim_run.stimulus, ImageSeqStim):
        raise TypeError(
            f"{extractor_name} requires ImageSeqStim, "
            f"got {type(stim_run.stimulus).__name__}"
        )
    return stim_run.stimulus


@feature_extractor("clip")
class CLIPExtractor:
    """CLIP image embeddings, one row per shown image (L2-normalized).

    Consumes :class:`ImageSeqStim` (one still image per response row).  Images
    are read on demand from the run's image store (a local or ``s3://`` HDF5),
    encoded with an open_clip vision model, and L2-normalized.  Identical
    images shared across runs are encoded once and reused.
    """

    name = "clip"
    n_dims = None  # set from the model's embedding width at extract time
    PARAM_SCHEMA = {
        "model": {"type": "string", "default": "ViT-B-32", "description": "open_clip model architecture"},
        "pretrained": {"type": "string", "default": "laion2b_s34b_b79k", "description": "open_clip pretrained tag"},
        "batch_size": {"type": "int", "default": 64, "min": 1, "description": "Images encoded per forward pass"},
    }

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        import torch
        import open_clip

        model_name = config.get("model", "ViT-B-32")
        pretrained = config.get("pretrained", "laion2b_s34b_b79k")
        batch_size = int(config.get("batch_size", 64))

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        model = model.eval().to(device)

        # Resolve the (single) image store and collect every image needed.
        stims = {r: _require_image_seq(stimuli.runs[r], self.name) for r in run_names}
        sources = {s.source for s in stims.values()}
        datasets = {s.dataset for s in stims.values()}
        if len(sources) != 1 or len(datasets) != 1:
            raise ValueError("clip extractor expects one image store across runs; "
                             f"got sources={sources} datasets={datasets}")
        source = sources.pop()
        dataset = datasets.pop()

        unique_ids = np.unique(np.concatenate([s.image_ids for s in stims.values()]))
        logger.info("clip: encoding %d unique images (%s/%s) on %s",
                    len(unique_ids), model_name, pretrained, device)
        emb = self._encode_ids(source, dataset, unique_ids, model, preprocess,
                               device, batch_size)
        self.n_dims = next(iter(emb.values())).shape[0]

        data = {r: np.stack([emb[int(i)] for i in s.image_ids])
                for r, s in stims.items()}
        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    @staticmethod
    def _encode_ids(source, dataset, ids, model, preprocess, device, batch_size):
        import torch
        import h5py
        from PIL import Image

        def _run(brick):
            ids_sorted = np.sort(ids)   # sequential reads minimise S3 range fetches
            out: dict[int, np.ndarray] = {}
            for start in range(0, len(ids_sorted), batch_size):
                chunk = ids_sorted[start:start + batch_size]
                tensors = [preprocess(Image.fromarray(brick[int(i)])) for i in chunk]
                batch = torch.stack(tensors).to(device)
                with torch.no_grad():
                    feats = model.encode_image(batch)
                    feats = feats / feats.norm(dim=-1, keepdim=True)
                feats = feats.cpu().numpy().astype(np.float32)
                for i, vec in zip(chunk, feats):
                    out[int(i)] = vec
            return out

        if str(source).startswith("s3://"):
            import s3fs
            fs = s3fs.S3FileSystem(anon=True)
            with fs.open(str(source)[len("s3://"):], "rb") as fobj, \
                    h5py.File(fobj, "r") as h:
                return _run(h[dataset])
        with h5py.File(source, "r") as h:
            return _run(h[dataset])

    def validate_config(self, config: dict) -> list[str]:
        return []


@feature_extractor("motion_energy")
class MotionEnergyExtractor:
    """Frame-differencing motion energy averaged per TR."""

    name = "motion_energy"
    n_dims = 1
    PARAM_SCHEMA = {}

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
