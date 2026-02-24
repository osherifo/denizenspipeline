"""Immutable data containers that flow between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar, runtime_checkable

import numpy as np

T = TypeVar("T")


# ─── Stimulus Data ────────────────────────────────────────────

@dataclass(frozen=True)
class StimRun:
    """Stimulus data for a single run/story."""
    name: str
    textgrid: Any           # Parsed TextGrid object
    trfile: Any             # Parsed TRFile object
    language: str = "en"
    modality: str = "reading"  # "reading" | "listening"


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
class Preprocessor(Protocol):
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
