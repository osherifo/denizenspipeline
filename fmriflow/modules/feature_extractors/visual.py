"""Visual feature extractors: luminance, motion_energy, clip."""

from __future__ import annotations

import logging
from pathlib import Path

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
        kinds = {s.source_kind for s in stims.values()}
        if kinds != {"hdf5"}:
            raise ValueError("clip extractor requires an HDF5 image store "
                             f"(source_kind='hdf5'); got {kinds}. For an image "
                             "directory (e.g. Algonauts PNGs) use the alexnet or "
                             "timm extractor instead.")
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


@feature_extractor("alexnet")
class AlexNetExtractor:
    """AlexNet layer activations, one row per shown image.

    Reproduces the Algonauts 2023 dev-kit visual-encoding features: a pretrained
    torchvision AlexNet, activations read from a chosen layer (via
    ``create_feature_extractor``), flattened per image, and optionally reduced
    with PCA — the classic ``AlexNet layer -> PCA -> linear/ridge`` recipe.

    Consumes :class:`ImageSeqStim`.  Images are read on demand from a directory
    of image files (``source_kind='image_dir'``, e.g. Algonauts PNGs) or an HDF5
    store (``'hdf5'``, e.g. NSD).  Identical images shared across runs are
    encoded once and reused.

    Note on PCA: when ``n_pca_components`` is set the basis is fit on **all**
    encoded images (train + held-out), matching common Algonauts reproductions.
    For a leakage-free fit, leave PCA off and let a ridge model regularise the
    full-dimensional features (himalaya handles this natively via the kernel).
    """

    name = "alexnet"
    n_dims = None  # set at extract time from the (flattened / PCA) width
    PARAM_SCHEMA = {
        "layer": {"type": "string", "default": "features.7", "description": "torchvision node to read (e.g. features.2, features.7, classifier.2)"},
        "pretrained": {"type": "bool", "default": True, "description": "Use ImageNet-pretrained weights"},
        "n_pca_components": {"type": "int", "description": "If set, PCA-reduce the flattened features to this many dims (fit on all images)"},
        "batch_size": {"type": "int", "default": 64, "min": 1, "description": "Images per forward pass"},
        "image_size": {"type": "int", "default": 224, "description": "Resize images to this square size before the network"},
    }

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        import torch
        from torchvision.models import alexnet, AlexNet_Weights
        from torchvision.models.feature_extraction import create_feature_extractor
        from torchvision import transforms

        layer = config.get("layer", "features.7")
        pretrained = config.get("pretrained", True)
        n_pca = config.get("n_pca_components")
        batch_size = int(config.get("batch_size", 64))
        image_size = int(config.get("image_size", 224))

        device = "cuda" if torch.cuda.is_available() else "cpu"
        weights = AlexNet_Weights.DEFAULT if pretrained else None
        model = alexnet(weights=weights).eval().to(device)
        fx = create_feature_extractor(model, return_nodes=[layer])
        preprocess = transforms.Compose([
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225]),
        ])

        stims = {r: _require_image_seq(stimuli.runs[r], self.name) for r in run_names}
        sources = {s.source for s in stims.values()}
        kinds = {s.source_kind for s in stims.values()}
        if len(sources) != 1 or len(kinds) != 1:
            raise ValueError("alexnet extractor expects one image store across runs; "
                             f"got sources={sources} kinds={kinds}")
        source, kind = sources.pop(), kinds.pop()
        dataset = next(iter(stims.values())).dataset

        unique_ids = np.unique(np.concatenate([s.image_ids for s in stims.values()]))
        logger.info("alexnet: encoding %d unique images (layer=%s) on %s",
                    len(unique_ids), layer, device)
        feats = self._encode(source, kind, dataset, unique_ids, fx, layer,
                             preprocess, device, batch_size)
        if n_pca:
            feats = self._pca(feats, int(n_pca))
        self.n_dims = int(next(iter(feats.values())).shape[0])

        data = {r: np.stack([feats[int(i)] for i in s.image_ids])
                for r, s in stims.items()}
        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    @staticmethod
    def _encode(source, kind, dataset, ids, fx, layer, preprocess, device, batch_size):
        import torch
        from PIL import Image

        ids_sorted = np.sort(ids)

        def _batches(load):
            out: dict[int, np.ndarray] = {}
            for start in range(0, len(ids_sorted), batch_size):
                chunk = ids_sorted[start:start + batch_size]
                batch = torch.stack([preprocess(load(int(i))) for i in chunk]).to(device)
                with torch.no_grad():
                    act = fx(batch)[layer]
                act = act.reshape(act.shape[0], -1).cpu().numpy().astype(np.float32)
                for i, vec in zip(chunk, act):
                    out[int(i)] = vec
            return out

        if kind == "image_dir":
            files = sorted(Path(source).glob("*.png")) or sorted(Path(source).glob("*.jpg"))
            if not files:
                raise FileNotFoundError(f"no .png/.jpg images under {source}")

            def _load(i):
                # context-manage the handle so large image dirs don't leak fds
                with Image.open(files[i]) as im:
                    return im.convert("RGB")
            return _batches(_load)

        if kind == "hdf5":
            import h5py
            def _from_h5(h):
                brick = h[dataset]
                return _batches(lambda i: Image.fromarray(brick[i]).convert("RGB"))
            if str(source).startswith("s3://"):
                import s3fs
                fs = s3fs.S3FileSystem(anon=True)
                with fs.open(str(source)[len("s3://"):], "rb") as fobj, h5py.File(fobj, "r") as h:
                    return _from_h5(h)
            with h5py.File(source, "r") as h:
                return _from_h5(h)

        raise ValueError(f"alexnet extractor: unsupported source_kind '{kind}'")

    @staticmethod
    def _pca(feats: dict, n_components: int) -> dict:
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        ids = sorted(feats)
        X = StandardScaler().fit_transform(np.stack([feats[i] for i in ids]))
        n = min(n_components, X.shape[0], X.shape[1])
        Xr = PCA(n_components=n, random_state=0).fit_transform(X).astype(np.float32)
        return {i: Xr[k] for k, i in enumerate(ids)}

    def validate_config(self, config: dict) -> list[str]:
        return []


@feature_extractor("timm")
class TimmBackboneExtractor:
    """Pooled features from any `timm` vision backbone, one row per image.

    A generic image-encoder extractor: names a `timm` model (ViT, DINOv2, EVA,
    ConvNeXt, …), runs each image through it, and returns the model's pooled
    embedding (``num_classes=0``).  Covers the feature *backbones* used by the
    top Algonauts 2023 solutions (ViT CLS-token / DINOv2 / EVA) so they can be
    fit with a ridge encoder — it does **not** reproduce those systems' trained
    readouts, memory, or ensembling.

    Consumes :class:`ImageSeqStim`; reads images from an image directory
    (``source_kind='image_dir'``) or an HDF5 store (``'hdf5'``).  Preprocessing
    uses each model's own `timm` data config (correct resize + normalisation).
    """

    name = "timm"
    n_dims = None  # set at extract time from the model's embedding width
    PARAM_SCHEMA = {
        "model": {"type": "string", "default": "vit_base_patch16_224.augreg2_in21k_ft_in1k", "description": "timm model name (e.g. vit_base_patch14_dinov2.lvd142m, eva02_base_patch14_224.mim_in22k_ft_in1k)"},
        "pretrained": {"type": "bool", "default": True, "description": "Load pretrained weights"},
        "batch_size": {"type": "int", "default": 64, "min": 1, "description": "Images per forward pass"},
    }

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        import torch
        import timm

        model_name = config.get("model", "vit_base_patch16_224.augreg2_in21k_ft_in1k")
        pretrained = config.get("pretrained", True)
        batch_size = int(config.get("batch_size", 64))

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = timm.create_model(model_name, pretrained=pretrained, num_classes=0)
        model = model.eval().to(device)
        data_cfg = timm.data.resolve_model_data_config(model)
        preprocess = timm.data.create_transform(**data_cfg, is_training=False)

        stims = {r: _require_image_seq(stimuli.runs[r], self.name) for r in run_names}
        sources = {s.source for s in stims.values()}
        kinds = {s.source_kind for s in stims.values()}
        if len(sources) != 1 or len(kinds) != 1:
            raise ValueError("timm extractor expects one image store across runs; "
                             f"got sources={sources} kinds={kinds}")
        source, kind = sources.pop(), kinds.pop()
        dataset = next(iter(stims.values())).dataset

        unique_ids = np.unique(np.concatenate([s.image_ids for s in stims.values()]))
        logger.info("timm: encoding %d unique images (%s) on %s",
                    len(unique_ids), model_name, device)
        feats = self._encode(source, kind, dataset, unique_ids, model,
                             preprocess, device, batch_size)
        self.n_dims = int(next(iter(feats.values())).shape[0])

        data = {r: np.stack([feats[int(i)] for i in s.image_ids])
                for r, s in stims.items()}
        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    @staticmethod
    def _encode(source, kind, dataset, ids, model, preprocess, device, batch_size):
        import torch
        from PIL import Image

        ids_sorted = np.sort(ids)

        def _batches(load):
            out: dict[int, np.ndarray] = {}
            for start in range(0, len(ids_sorted), batch_size):
                chunk = ids_sorted[start:start + batch_size]
                batch = torch.stack([preprocess(load(int(i))) for i in chunk]).to(device)
                with torch.no_grad():
                    emb = model(batch)                     # (B, D) pooled
                emb = emb.cpu().numpy().astype(np.float32)
                for i, vec in zip(chunk, emb):
                    out[int(i)] = vec
            return out

        if kind == "image_dir":
            files = sorted(Path(source).glob("*.png")) or sorted(Path(source).glob("*.jpg"))
            if not files:
                raise FileNotFoundError(f"no .png/.jpg images under {source}")

            def _load(i):
                # context-manage the handle so large image dirs don't leak fds
                with Image.open(files[i]) as im:
                    return im.convert("RGB")
            return _batches(_load)

        if kind == "hdf5":
            import h5py
            def _from_h5(h):
                brick = h[dataset]
                return _batches(lambda i: Image.fromarray(brick[i]).convert("RGB"))
            if str(source).startswith("s3://"):
                import s3fs
                fs = s3fs.S3FileSystem(anon=True)
                with fs.open(str(source)[len("s3://"):], "rb") as fobj, h5py.File(fobj, "r") as h:
                    return _from_h5(h)
            with h5py.File(source, "r") as h:
                return _from_h5(h)

        raise ValueError(f"timm extractor: unsupported source_kind '{kind}'")

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
