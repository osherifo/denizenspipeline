"""PipelineStore — saved preprocessing pipelines under ``$FMRIFLOW_HOME/configs/preproc/``.

Each pipeline is one YAML file holding a
:class:`~fmriflow.preproc.graph.Pipeline` (see that module for the
schema). Files in the same directory that are *not* pipelines — the
pre-redesign ``preproc: {backend: ..., backend_params: ...}`` configs —
are reported separately as ``legacy`` so the UI can point at
``fmriflow preproc migrate`` instead of silently ignoring them.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from fmriflow.preproc.graph import Pipeline

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*$")
LEGACY_KEYS = ("backend", "backend_params")


def validate_slug(name: str) -> str:
    if not name or not _SLUG_RE.match(name):
        raise ValueError(
            f"invalid pipeline name {name!r}: letters, digits, '_' and '-' only"
        )
    return name


def is_legacy_preproc_config(data: Any) -> bool:
    """True for the old ``preproc: {backend: ...}`` stage config shape."""
    if not isinstance(data, dict):
        return False
    section = data.get("preproc") if isinstance(data.get("preproc"), dict) else data
    return "nodes" not in section and any(k in section for k in LEGACY_KEYS)


@dataclass
class PipelineSummary:
    name: str
    path: str
    description: str = ""
    n_nodes: int = 0
    node_types: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    mtime: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "path": self.path, "description": self.description,
            "n_nodes": self.n_nodes, "node_types": self.node_types, "inputs": self.inputs,
            "mtime": self.mtime, "error": self.error,
        }


class PipelineStore:
    """Lists / loads / saves pipeline YAMLs; 5 s directory-scan cache."""

    SCAN_TTL_S = 5.0

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root else None
        self._cache: tuple[list[PipelineSummary], list[dict]] | None = None
        self._scanned_at = 0.0

    @property
    def root(self) -> Path:
        if self._root is None:
            from fmriflow.core import paths
            self._root = paths.config_dir("preproc")
        self._root.mkdir(parents=True, exist_ok=True)
        return self._root

    def _path(self, name: str) -> Path:
        return self.root / f"{validate_slug(name)}.yaml"

    def invalidate(self) -> None:
        self._cache = None

    def scan(self, *, force: bool = False) -> tuple[list[PipelineSummary], list[dict]]:
        """Return ``(pipelines, legacy)``; ``legacy`` lists old-shape configs."""
        now = time.time()
        if not force and self._cache is not None and now - self._scanned_at < self.SCAN_TTL_S:
            return self._cache
        pipelines: list[PipelineSummary] = []
        legacy: list[dict] = []
        for path in sorted(self.root.glob("*.yaml")) + sorted(self.root.glob("*.yml")):
            try:
                data = yaml.safe_load(path.read_text()) or {}
            except Exception as e:
                pipelines.append(PipelineSummary(name=path.stem, path=str(path), error=f"YAML error: {e}"))
                continue
            if is_legacy_preproc_config(data):
                legacy.append({"name": path.stem, "path": str(path),
                               "hint": "old preproc config; run `fmriflow preproc migrate`"})
                continue
            try:
                p = Pipeline.from_yaml(path.read_text())
            except Exception as e:
                pipelines.append(PipelineSummary(name=path.stem, path=str(path), error=str(e)))
                continue
            pipelines.append(PipelineSummary(
                name=path.stem, path=str(path), description=p.description,
                n_nodes=len(p.nodes), node_types=[n.type for n in p.nodes],
                inputs=p.inputs, mtime=path.stat().st_mtime,
            ))
        self._cache = (pipelines, legacy)
        self._scanned_at = now
        return self._cache

    def list_pipelines(self) -> list[PipelineSummary]:
        return self.scan()[0]

    def list_legacy(self) -> list[dict]:
        return self.scan()[1]

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def load(self, name: str) -> Pipeline:
        path = self._path(name)
        if not path.is_file():
            raise KeyError(f"no pipeline named {name!r}")
        data = yaml.safe_load(path.read_text()) or {}
        if is_legacy_preproc_config(data):
            raise ValueError(
                f"{path.name} is an old-style preproc config (backend/backend_params). "
                f"Convert it with `fmriflow preproc migrate`."
            )
        p = Pipeline.from_dict(data["pipeline"] if "pipeline" in data and "nodes" not in data else data)
        if p.name == "untitled":
            p.name = name
        return p

    def save(self, name: str, pipeline: Pipeline) -> Path:
        path = self._path(name)
        pipeline.name = name
        path.write_text(pipeline.to_yaml())
        self.invalidate()
        return path

    # ── config-store compatibility (artifact hub) ─────────────────

    def list_configs(self) -> list[PipelineSummary]:
        """Hub-facing alias: summaries carry ``filename`` too."""
        out = []
        for p in self.list_pipelines():
            out.append(PipelineSummary(**{**p.__dict__}))
            out[-1].filename = Path(p.path).name  # type: ignore[attr-defined]
        return out

    def get_config(self, filename: str) -> dict[str, Any] | None:
        name = Path(filename).stem
        path = self.root / f"{name}.yaml"
        if not path.is_file():
            return None
        raw = path.read_text()
        try:
            config = yaml.safe_load(raw) or {}
        except Exception:
            config = {}
        return {"filename": path.name, "path": str(path), "config": config, "yaml_string": raw}

    def save_config(self, filename: str, yaml_string: str) -> dict[str, Any]:
        """Write raw YAML if it parses as a pipeline; legacy shapes are refused."""
        name = Path(filename).stem
        try:
            validate_slug(name)
            data = yaml.safe_load(yaml_string) or {}
        except Exception as e:
            return {"saved": False, "errors": [str(e)]}
        if is_legacy_preproc_config(data):
            return {"saved": False, "errors": ["old-style preproc config (backend/backend_params); run `fmriflow preproc migrate`"]}
        body = data["pipeline"] if isinstance(data, dict) and "pipeline" in data and "nodes" not in data else data
        if not isinstance(body, dict) or "nodes" not in body:
            return {"saved": False, "errors": ["not a pipeline: no 'nodes' list"]}
        try:
            pipeline = Pipeline.from_dict(body)
        except Exception as e:
            return {"saved": False, "errors": [f"not a pipeline: {e}"]}
        path = self._path(name)
        path.write_text(yaml_string)
        self.invalidate()
        return {"saved": True, "path": str(path), "name": pipeline.name}

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not path.is_file():
            return False
        path.unlink()
        self.invalidate()
        return True
