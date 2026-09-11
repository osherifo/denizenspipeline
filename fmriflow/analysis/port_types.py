"""Port types for analysis graphs.

Each name maps to the Python classes a value on that port may be, and to
parent types for compatibility (an output can feed an input of the same type,
a parent type, or ``any``). The builder fetches this table to check
connections before the server validates the graph.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from fmriflow.analysis.values import ContextValue, GroupRun, StudyRun, SubjectRun
from fmriflow.core.types import (
    FeatureData,
    FeatureSet,
    ModelResult,
    PreparedData,
    ResponseData,
    SemanticSubspace,
    StimulusData,
    VariancePartition,
    WeightAnalysis,
)
from fmriflow.graph.ports import ANY, TypeLattice

LATTICE = TypeLattice()
_PYTHON_TYPES: dict[str, tuple[type, ...]] = {}
_DESCRIPTIONS: dict[str, str] = {ANY: "Any value"}


def register_port_type(name: str, py_types: tuple[type, ...] = (), *,
                       parents: tuple[str, ...] = (), description: str = "") -> None:
    LATTICE.register(name, parents)
    _PYTHON_TYPES[name] = tuple(py_types)
    _DESCRIPTIONS[name] = description


def value_matches(type_name: str, value: Any) -> bool:
    """True when ``value`` is acceptable for a port of ``type_name``."""
    classes = _PYTHON_TYPES.get(type_name)
    if type_name == ANY or not classes:
        return True
    return isinstance(value, classes)


def describe() -> list[dict[str, Any]]:
    parents = LATTICE.to_dict()
    return [{"name": n, "parents": parents.get(n, []), "description": _DESCRIPTIONS.get(n, "")}
            for n in LATTICE.names()]


register_port_type("StimulusData", (StimulusData,), description="Stimuli per run (text grids, audio, video, images)")
register_port_type("ResponseData", (ResponseData,), description="fMRI responses per run, with mask, surface and transform")
register_port_type("FeatureSet", (FeatureSet,), description="One feature space: a matrix per run")
register_port_type("FeatureData", (FeatureData,), description="Ordered feature spaces used together in one model")
register_port_type("PreparedData", (PreparedData,), description="Train/test design and response matrices")
register_port_type("ModelResult", (ModelResult,), description="Weights, prediction scores and regularisation per voxel")
register_port_type("VariancePartition", (VariancePartition,), description="Unique and shared variance per feature group")
register_port_type("WeightAnalysis", (WeightAnalysis,), description="Per-feature importance and temporal weight profiles")
register_port_type("SemanticSubspace", (SemanticSubspace,), description="Weight-space basis shared across subjects")
register_port_type("Array", (np.ndarray,), description="A numeric array, e.g. one value per voxel")
register_port_type("Artifacts", (dict,), description="Files written by a reporter: {label: path}")
register_port_type("Context", (ContextValue,), description="Context keys (result, analysis.*, ...) for context-reading modules")
register_port_type("SubjectRun", (SubjectRun,), description="One subject's run inside a fan-out")
register_port_type("GroupRun", (GroupRun,), description="Subject runs of one group plus group artifacts")
register_port_type("StudyRun", (StudyRun,), description="Labelled groups plus study artifacts")
