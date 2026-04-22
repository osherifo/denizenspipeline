"""PreprocConfigStore — indexes preprocessing YAML configs from a directory.

Mirrors the analysis ``ConfigStore`` pattern: YAMLs live in a directory
(default ``./experiments/preproc/``) and must contain a top-level ``preproc:``
section that maps to :class:`fmriflow.preproc.manifest.PreprocConfig`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PreprocConfigSummary:
    """Lightweight metadata extracted from a preproc YAML."""
    filename: str
    path: str
    subject: str
    backend: str
    bids_dir: str
    output_dir: str
    container: str
    container_type: str
    mode: str


class PreprocConfigStore:
    """Indexes preprocessing config files from a directory."""

    def __init__(self, configs_dir: Path):
        self.configs_dir = configs_dir
        self._cache: list[PreprocConfigSummary] = []
        self._last_scan = 0.0

    def scan(self) -> None:
        """Re-scan configs directory for .yaml files with a preproc: section."""
        self._cache = []
        if not self.configs_dir.is_dir():
            logger.warning("Preproc configs directory not found: %s", self.configs_dir)
            return

        for yaml_path in sorted(self.configs_dir.glob('*.yaml')):
            if yaml_path.name.startswith('_'):
                continue
            try:
                summary = self._extract_summary(yaml_path)
                if summary:
                    self._cache.append(summary)
            except Exception as e:
                logger.debug("Skipping %s: %s", yaml_path, e)

        self._last_scan = time.time()
        logger.info(
            "Scanned %d preproc config(s) from %s",
            len(self._cache), self.configs_dir,
        )

    def _maybe_rescan(self) -> None:
        if time.time() - self._last_scan > 10.0:
            self.scan()

    def _extract_summary(self, path: Path) -> PreprocConfigSummary | None:
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        if not isinstance(data, dict):
            return None

        section = data.get("preproc")
        if not isinstance(section, dict):
            return None

        params = section.get("backend_params") or {}
        if not isinstance(params, dict):
            params = {}

        return PreprocConfigSummary(
            filename=path.name,
            path=str(path.resolve()),
            subject=str(section.get("subject", "")),
            backend=str(section.get("backend", "")),
            bids_dir=str(section.get("bids_dir", "")),
            output_dir=str(section.get("output_dir", "")),
            container=str(params.get("container", "")),
            container_type=str(params.get("container_type", "")),
            mode=str(params.get("mode", "")),
        )

    def list_configs(self) -> list[PreprocConfigSummary]:
        """Return summaries of all preproc configs."""
        self._maybe_rescan()
        return self._cache

    def get_config(self, filename: str) -> dict[str, Any] | None:
        """Return full parsed config + raw YAML for one file."""
        self._maybe_rescan()
        resolved = (self.configs_dir / filename).resolve()
        if not resolved.is_relative_to(self.configs_dir.resolve()):
            return None
        if not resolved.is_file():
            return None

        raw = resolved.read_text()
        try:
            config = yaml.safe_load(raw) or {}
        except Exception:
            config = {}

        return {
            'filename': filename,
            'path': str(resolved),
            'config': config,
            'yaml_string': raw,
        }
