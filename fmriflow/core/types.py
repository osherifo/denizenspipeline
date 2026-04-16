"""Immutable data containers that flow between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

import numpy as np

T = TypeVar("T")


# ─── Preparation State (mutable, internal to the prepare stage) ─────

@dataclass
class PreparationState:
    """Mutable state passed between preparation steps.

    Holds per-run dicts (before concatenation) AND/OR concatenated
    matrices (after).  Steps mutate this in place.  Only lives inside
    the prepare stage — not part of the public inter-stage protocol.
    """

    # ── Per-run data (before concatenation) ──
    responses: dict[str, np.ndarray] = field(default_factory=dict)
    features: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)

    # Concatenated matrices (after concatenation step)
    X_train: np.ndarray | None = None
    Y_train: np.ndarray | None = None
    X_test: np.ndarray | None = None
    Y_test: np.ndarray | None = None

    # Run info
    all_runs: list[str] = field(default_factory=list)
    train_runs: list[str] = field(default_factory=list)
    test_runs: list[str] = field(default_factory=list)

    # Feature metadata
    feature_names: list[str] = field(default_factory=list)
    feature_dims: list[int] = field(default_factory=list)

    # Extra metadata
    delays: list[int] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_concatenated(self) -> bool:
        """Whether data has been concatenated into matrices."""
        return self.X_train is not None

    def to_prepared_data(self) -> PreparedData:
        """Convert final state to immutable PreparedData."""
        if not self.is_concatenated:
            raise ValueError(
                "Cannot convert to PreparedData before concatenation step")
        return PreparedData(
            X_train=self.X_train,
            Y_train=self.Y_train,
            X_test=self.X_test,
            Y_test=self.Y_test,
            feature_names=self.feature_names,
            feature_dims=self.feature_dims,
            delays=self.delays,
            train_runs=self.train_runs,
            test_runs=self.test_runs,
            metadata=self.metadata,
        )


# ─── Stimulus Containers ──────────────────────────────────────

@dataclass(frozen=True)
class LanguageStim:
    """Language stimulus data (TextGrid + TRFile pair)."""
    textgrid: Any           # Parsed TextGrid object
    trfile: Any             # Parsed TRFile object


@dataclass(frozen=True)
class AudioStim:
    """Audio stimulus data (waveform loaded in memory)."""
    waveform: np.ndarray    # (n_samples,)
    sample_rate: int
    tr_times: np.ndarray    # TR onset times in seconds


@dataclass(frozen=True)
class VisualStim:
    """Visual stimulus data (video metadata, frames loaded on demand)."""
    video_path: Path        # path to video file
    fps: float
    n_frames: int
    tr_times: np.ndarray    # TR onset times in seconds


# ─── Stimulus Data ────────────────────────────────────────────

@dataclass(frozen=True)
class StimRun:
    """Stimulus data for a single run/story."""
    name: str
    stimulus: LanguageStim | AudioStim | VisualStim
    language: str = "en"
    modality: str = "reading"  # "reading" | "listening" | "visual"

    @property
    def textgrid(self):
        """Backward-compatible access to TextGrid (language stimuli only).

        Raises
        ------
        TypeError
            If the underlying stimulus is not a LanguageStim.
        """
        if isinstance(self.stimulus, LanguageStim):
            # Allow LanguageStim(textgrid=None) for tests or missing data.
            return self.stimulus.textgrid
        raise TypeError(
            f"StimRun.textgrid is only available for language stimuli; "
            f"got {type(self.stimulus).__name__}."
        )

    @property
    def trfile(self):
        """Backward-compatible access to TRFile (language stimuli only).

        Raises
        ------
        TypeError
            If the underlying stimulus is not a LanguageStim.
        """
        if isinstance(self.stimulus, LanguageStim):
            # Allow LanguageStim(trfile=None) for tests or missing data.
            return self.stimulus.trfile
        raise TypeError(
            f"StimRun.trfile is only available for language stimuli; "
            f"got {type(self.stimulus).__name__}."
        )
@dataclass(frozen=True)
class StimulusData:
    """All stimulus data for an experiment."""
    runs: dict[str, StimRun]                  # {run_name: StimRun}
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── Response Data ────────────────────────────────────────────

@dataclass(frozen=True)
class ResponseData:
    """fMRI response data for a subject."""
    responses: dict[str, np.ndarray]          # {run_name: (n_trs, n_voxels)}
    mask: np.ndarray                          # cortical mask
    surface: str                              # pycortex surface name
    transform: str                            # pycortex transform name
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── Feature Data ─────────────────────────────────────────────

@dataclass(frozen=True)
class FeatureSet:
    """Features extracted by a single extractor or loaded from a source."""
    name: str
    data: dict[str, np.ndarray]               # {run_name: (n_trs, n_dims)}
    n_dims: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeatureData:
    """All features for an experiment."""
    features: dict[str, FeatureSet]           # {feature_name: FeatureSet}

    @property
    def feature_names(self) -> list[str]:
        return list(self.features.keys())

    @property
    def total_dims(self) -> int:
        return sum(fs.n_dims for fs in self.features.values())


# ─── Prepared Data ────────────────────────────────────────────

@dataclass(frozen=True)
class PreparedData:
    """Aligned, preprocessed matrices ready for model fitting."""
    X_train: np.ndarray                       # (n_train_trs, n_delayed_features)
    Y_train: np.ndarray                       # (n_train_trs, n_voxels)
    X_test: np.ndarray                        # (n_test_trs, n_delayed_features)
    Y_test: np.ndarray                        # (n_test_trs, n_voxels)
    feature_names: list[str]
    feature_dims: list[int]                   # dims per feature (before delay)
    delays: list[int]
    train_runs: list[str]
    test_runs: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── Model Result ─────────────────────────────────────────────

@dataclass(frozen=True)
class ModelResult:
    """Output of model fitting."""
    weights: np.ndarray                       # (n_delayed_features, n_voxels)
    scores: np.ndarray                        # (n_voxels,) prediction correlations
    alphas: np.ndarray                        # (n_voxels,) selected regularization
    feature_names: list[str]
    feature_dims: list[int]
    delays: list[int]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def n_voxels(self) -> int:
        return self.scores.shape[0]


# ─── Plugin Protocols ─────────────────────────────────────────

@runtime_checkable
class StimulusLoader(Protocol):
    """Loads stimulus timing data (TextGrids, TRFiles) for an experiment."""
    name: str

    def load(self, config: dict) -> StimulusData: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class ResponseLoader(Protocol):
    """Loads fMRI response data for a subject."""
    name: str

    def load(self, config: dict) -> ResponseData: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class ResponseReader(Protocol):
    """Reads fMRI response data from a specific file format."""
    name: str

    def read(self, resp_dir: Path, run_names: list[str] | None,
             config: dict) -> dict[str, np.ndarray]: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class FeatureSource(Protocol):
    """Loads feature data from a backend (compute, filesystem, cloud)."""
    name: str

    def load(self, run_names: list[str], config: dict) -> FeatureSet: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class FeatureExtractor(Protocol):
    """Extracts a single feature type from stimulus data."""
    name: str
    n_dims: int

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class Preparer(Protocol):
    """Aligns, normalizes, and splits data for model fitting."""
    name: str

    def prepare(self, responses: ResponseData, features: FeatureData,
                config: dict) -> PreparedData: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class Model(Protocol):
    """Fits a voxelwise encoding model."""
    name: str

    def fit(self, data: PreparedData, config: dict) -> ModelResult: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class Reporter(Protocol):
    """Generates output artifacts from model results."""
    name: str

    def report(self, result: ModelResult, context: Any,
               config: dict) -> dict[str, str]: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class Analyzer(Protocol):
    """Computes derived results from model outputs."""
    name: str

    def analyze(self, context: Any, config: dict) -> None: ...
    def validate_config(self, config: dict) -> list[str]: ...


@runtime_checkable
class PreparationStep(Protocol):
    """A single composable preparation step for the pipeline preparer."""
    name: str

    def apply(self, state: PreparationState, params: dict) -> None: ...
    def validate_params(self, params: dict) -> list[str]: ...


# ─── Analysis Results ────────────────────────────────────────

@dataclass(frozen=True)
class VariancePartition:
    """Per-voxel variance explained by each feature or feature group."""
    unique_variance: np.ndarray          # (n_groups, n_voxels)
    shared_variance: np.ndarray          # (n_voxels,)
    total_variance: np.ndarray           # (n_voxels,)
    group_names: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WeightAnalysis:
    """Decomposed and summarized model weights."""
    per_feature_importance: np.ndarray   # (n_features, n_voxels)
    temporal_profiles: np.ndarray        # (n_delays, n_features, n_voxels)
    feature_names: list[str]
    delays: list[int]
    metadata: dict[str, Any] = field(default_factory=dict)
