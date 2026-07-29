"""PreprocConfigStore — indexes preproc YAML configs.

Mirrors :class:`AutoflattenConfigStore`. YAML files live under
``$FMRIFLOW_HOME/configs/preproc/`` and must contain a top-level
``preproc:`` section matching :class:`fmriflow.preproc.manifest.PreprocConfig`.

These are the configs the workflow runner hands to
``PreprocManager.start_run_from_config_file``; the store exists so they
can be listed, read, written, and shared through the Artifact Hub the
same way analysis, convert and autoflatten configs already are.
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
    mode: str
    bids_dir: str
    output_dir: str


class PreprocConfigStore:
    """Indexes preproc config files from a directory."""

    def __init__(self, configs_dir: Path):
        self.configs_dir = configs_dir
        self._cache: list[PreprocConfigSummary] = []
        self._last_scan = 0.0

    def scan(self) -> None:
        self._cache = []
        if not self.configs_dir.is_dir():
            logger.warning(
                "Preproc configs directory not found: %s", self.configs_dir,
            )
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

        params = section.get("backend_params")
        params = params if isinstance(params, dict) else {}

        return PreprocConfigSummary(
            filename=path.name,
            path=str(path.resolve()),
            subject=str(section.get("subject", "")),
            backend=str(section.get("backend", "")),
            mode=str(params.get("mode", "full")),
            bids_dir=str(section.get("bids_dir", "")),
            output_dir=str(section.get("output_dir", "")),
        )

    def list_configs(self) -> list[PreprocConfigSummary]:
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
            config = yaml.safe_load(raw) or {}
        except Exception:
            config = {}

        return {
            'filename': filename,
            'path': str(resolved),
            'config': config,
            'yaml_string': raw,
        }

    def save_config(self, filename: str, yaml_string: str) -> dict[str, Any]:
        """Overwrite (or create) a config file with raw YAML.

        Validates the YAML parses and contains a top-level ``preproc:``
        section before writing. Rejects filenames with directory
        components.

        Returns dict with keys: saved (bool), path, errors (list[str]).
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

        if not isinstance(parsed, dict) or not isinstance(parsed.get('preproc'), dict):
            return {'saved': False, 'path': '', 'errors': [
                "Config must have a top-level `preproc:` mapping",
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
        """Duplicate an existing config under a new filename.

        Refuses to overwrite existing files. Returns dict with keys:
        saved, path, errors.
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
