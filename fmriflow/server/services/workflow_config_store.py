"""WorkflowConfigStore — indexes end-to-end workflow YAMLs.

A workflow YAML strings together the four existing stage configs
(convert / preproc / autoflatten / analysis) into a single ordered
execution. The file format is intentionally minimal — each stage
entry just references an existing stage-config YAML that already
lives under ``./experiments/<stage>/``:

    workflow:
      name: AN_reading_full
      stages:
        - { stage: convert,     config: experiments/convert/an_reading_en.yaml }
        - { stage: preproc,     config: experiments/preproc/fmriprep_AN.yaml }
        - { stage: autoflatten, config: experiments/autoflatten/AN.yaml }
        - { stage: analysis,    config: experiments/mkr_AN.yaml }

The WorkflowManager executes these in order via the existing
stage-manager ``start_run_from_config_file`` entry points, stopping
on the first failure. Each stage's child run retains its own
detach / reattach semantics.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

VALID_STAGES = ("convert", "preproc", "autoflatten", "analysis")


@dataclass
class WorkflowStageRef:
    stage: str
    config: str  # path (relative or absolute)


@dataclass
class WorkflowConfigSummary:
    filename: str
    path: str
    name: str
    n_stages: int
    stage_names: list[str]


class WorkflowConfigStore:
    """Indexes workflow YAMLs from a directory."""

    def __init__(self, configs_dir: Path):
        self.configs_dir = configs_dir
        self._cache: list[WorkflowConfigSummary] = []
        self._last_scan = 0.0

    def scan(self) -> None:
        self._cache = []
        if not self.configs_dir.is_dir():
            logger.warning(
                "Workflow configs directory not found: %s", self.configs_dir,
            )
            return
        for path in sorted(self.configs_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            try:
                summary = self._extract_summary(path)
                if summary:
                    self._cache.append(summary)
            except Exception as e:
                logger.debug("Skipping %s: %s", path, e)
        self._last_scan = time.time()

    def _maybe_rescan(self) -> None:
        if time.time() - self._last_scan > 10.0:
            self.scan()

    def _extract_summary(
        self, path: Path,
    ) -> WorkflowConfigSummary | None:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return None
        section = data.get("workflow")
        if not isinstance(section, dict):
            return None
        stages = section.get("stages") or []
        stage_names: list[str] = []
        for s in stages:
            if isinstance(s, dict) and "stage" in s:
                stage_names.append(str(s["stage"]))
        return WorkflowConfigSummary(
            filename=path.name,
            path=str(path.resolve()),
            name=str(section.get("name", path.stem)),
            n_stages=len(stages),
            stage_names=stage_names,
        )

    def list_configs(self) -> list[WorkflowConfigSummary]:
        self._maybe_rescan()
        return self._cache

    def get_config(self, filename: str) -> dict[str, Any] | None:
        self._maybe_rescan()
        resolved = (self.configs_dir / filename).resolve()
        if not resolved.is_relative_to(self.configs_dir.resolve()):
            return None
        if not resolved.is_file():
            return None
        raw = resolved.read_text()
        try:
            data = yaml.safe_load(raw) or {}
        except Exception:
            data = {}
        return {
            "filename": filename,
            "path": str(resolved),
            "config": data,
            "yaml_string": raw,
        }

    def save_config(self, filename: str, yaml_string: str) -> dict[str, Any]:
        """Overwrite (or create) a workflow config file with raw YAML.

        Validates the YAML parses and contains a top-level
        ``workflow:`` mapping before writing. Rejects filenames with
        directory components.
        """
        if '/' in filename or '\\' in filename or filename in ('.', '..'):
            return {'saved': False, 'path': '', 'errors': [
                f"Invalid filename: {filename!r}",
            ]}
        if not filename.endswith(('.yaml', '.yml')):
            return {'saved': False, 'path': '', 'errors': [
                "Config filename must end in .yaml or .yml",
            ]}

        try:
            parsed = yaml.safe_load(yaml_string)
        except yaml.YAMLError as e:
            return {'saved': False, 'path': '', 'errors': [f'YAML parse error: {e}']}

        if not isinstance(parsed, dict) or not isinstance(parsed.get('workflow'), dict):
            return {'saved': False, 'path': '', 'errors': [
                "Config must have a top-level `workflow:` mapping",
            ]}

        path = self.configs_dir / filename
        try:
            self.configs_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml_string)
        except OSError as e:
            return {'saved': False, 'path': str(path), 'errors': [f'Write failed: {e}']}

        self._last_scan = 0.0
        return {'saved': True, 'path': str(path.resolve()), 'errors': []}

    def copy_config(self, source: str, new_filename: str) -> dict[str, Any]:
        """Duplicate an existing workflow config under a new filename.

        Refuses to overwrite existing files.
        """
        if '/' in new_filename or '\\' in new_filename or new_filename in ('.', '..'):
            return {'saved': False, 'path': '', 'errors': [
                f"Invalid filename: {new_filename!r}",
            ]}
        if not new_filename.endswith(('.yaml', '.yml')):
            return {'saved': False, 'path': '', 'errors': [
                "Config filename must end in .yaml or .yml",
            ]}

        src = self.configs_dir / source
        if not src.is_file():
            return {'saved': False, 'path': '', 'errors': [
                f"Source config not found: {source}",
            ]}

        dest = self.configs_dir / new_filename
        if dest.exists():
            return {'saved': False, 'path': str(dest), 'errors': [
                f"Destination already exists: {new_filename}",
            ]}

        try:
            dest.write_text(src.read_text())
        except OSError as e:
            return {'saved': False, 'path': str(dest), 'errors': [f'Write failed: {e}']}

        self._last_scan = 0.0
        return {'saved': True, 'path': str(dest.resolve()), 'errors': []}


def parse_stage_refs(workflow: dict) -> list[WorkflowStageRef]:
    """Validate + extract stage refs from a workflow dict.

    Raises ValueError on schema errors.
    """
    if not isinstance(workflow, dict):
        raise ValueError("workflow must be a mapping")
    stages = workflow.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("workflow.stages must be a non-empty list")
    refs: list[WorkflowStageRef] = []
    for i, s in enumerate(stages):
        if not isinstance(s, dict):
            raise ValueError(f"stage[{i}] must be a mapping")
        stage = s.get("stage")
        cfg = s.get("config")
        if stage not in VALID_STAGES:
            raise ValueError(
                f"stage[{i}].stage must be one of {VALID_STAGES}, got {stage!r}"
            )
        if not cfg or not isinstance(cfg, str):
            raise ValueError(f"stage[{i}].config must be a path string")
        refs.append(WorkflowStageRef(stage=str(stage), config=str(cfg)))
    return refs
