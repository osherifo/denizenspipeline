"""PreprocStack — the unified preprocessing pipeline shape.

A preprocessing pipeline is an ordered stack of stages:

- exactly one Bootstrap stage (Stage 0) that takes raw BIDS and
  produces the initial PreprocManifest (fmriprep, nipype, custom,
  bids_app, or passthrough).
- zero or more Transform stages (Stages 1..N) that each consume
  the prior manifest+outputs and emit updated ones (smooth, mask,
  regress, custom user nodes, …).

Stages are pure recipe — they do not bind to a subject. Subject
and dataset binding lives at the run-launch layer (see
PreprocConfig, which Phase 1 keeps untouched for back-compat).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


BOOTSTRAP_KINDS = ("fmriprep", "nipype", "custom", "bids_app", "passthrough")


@dataclass(frozen=True)
class BootstrapStage:
    """Stage 0 — produces the initial PreprocManifest from raw BIDS.

    ``workflow`` is only meaningful for ``kind == "nipype"`` and names
    a workflow registered with @register_preproc_workflow
    (e.g. ``"reference"``, ``"gallantlab_minimal"``).
    """

    kind: str
    workflow: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BootstrapStage:
        return cls(
            kind=data["kind"],
            workflow=data.get("workflow"),
            params=dict(data.get("params") or {}),
        )


@dataclass(frozen=True)
class TransformStage:
    """Stage N — a single transform applied to the prior stage's outputs.

    ``name`` is the registered transform identifier (e.g. ``"smooth"``,
    ``"regress_confounds"``).
    """

    name: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransformStage:
        return cls(
            name=data["name"],
            params=dict(data.get("params") or {}),
        )


@dataclass(frozen=True)
class StepRecord:
    """Canonical provenance entry for one executed stage.

    Populated by the stack runner after each stage completes and
    appended to PreprocManifest.additional_steps. Old string-shaped
    entries in legacy manifests load via from_legacy_string.
    """

    name: str
    version: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    input_stage: int = 0
    output_dir: str = ""
    duration_s: float = 0.0
    fingerprint: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepRecord:
        return cls(
            name=data["name"],
            version=data.get("version", ""),
            params=dict(data.get("params") or {}),
            input_stage=int(data.get("input_stage", 0)),
            output_dir=data.get("output_dir", ""),
            duration_s=float(data.get("duration_s", 0.0)),
            fingerprint=data.get("fingerprint", ""),
        )

    @classmethod
    def from_legacy_string(cls, s: str) -> StepRecord:
        """Wrap a legacy ``additional_steps: list[str]`` entry."""
        return cls(name=s)


@dataclass(frozen=True)
class PreprocStack:
    """The recipe — a bootstrap stage and an ordered list of transforms.

    Subject/dataset binding intentionally lives elsewhere; the stack
    is reusable across subjects.
    """

    bootstrap: BootstrapStage
    transforms: list[TransformStage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())
        return p

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreprocStack:
        bootstrap = BootstrapStage.from_dict(data["bootstrap"])
        transforms = [
            TransformStage.from_dict(t) for t in (data.get("transforms") or [])
        ]
        return cls(bootstrap=bootstrap, transforms=transforms)

    @classmethod
    def from_json(cls, path: str | Path) -> PreprocStack:
        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def from_legacy(cls, config: Any) -> PreprocStack:
        """Auto-wrap a legacy PreprocConfig into a single-bootstrap stack.

        Used during the transition so existing single-backend launches
        keep working unchanged. Subject/dataset/paths from the config
        are ignored — they belong to the run-launch layer, not the
        recipe.
        """
        return cls(
            bootstrap=BootstrapStage(
                kind=config.backend,
                params=dict(getattr(config, "backend_params", {}) or {}),
            ),
            transforms=[],
        )
