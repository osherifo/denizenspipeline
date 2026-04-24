"""AutoflattenConfigStore — indexes autoflatten YAML configs.

Mirrors the analysis / preproc ConfigStore pattern. YAML files live under
``./experiments/autoflatten/`` and must contain a top-level
``autoflatten:`` section matching
:class:`fmriflow.preproc.autoflatten.AutoflattenConfig`.
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
class AutoflattenConfigSummary:
    """Lightweight metadata extracted from an autoflatten YAML."""
    filename: str
    path: str
    subject: str
    subjects_dir: str
    hemispheres: str
    backend: str
    output_dir: str


class AutoflattenConfigStore:
    """Indexes autoflatten config files from a directory."""

    def __init__(self, configs_dir: Path):
        self.configs_dir = configs_dir
        self._cache: list[AutoflattenConfigSummary] = []
        self._last_scan = 0.0

    def scan(self) -> None:
        self._cache = []
        if not self.configs_dir.is_dir():
            logger.warning(
                "Autoflatten configs directory not found: %s",
                self.configs_dir,
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
            "Scanned %d autoflatten config(s) from %s",
            len(self._cache), self.configs_dir,
        )

    def _maybe_rescan(self) -> None:
        if time.time() - self._last_scan > 10.0:
            self.scan()

    def _extract_summary(
        self, path: Path,
    ) -> AutoflattenConfigSummary | None:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return None

        section = data.get("autoflatten")
        if not isinstance(section, dict):
            return None

        return AutoflattenConfigSummary(
            filename=path.name,
            path=str(path.resolve()),
            subject=str(section.get("subject", "")),
            subjects_dir=str(section.get("subjects_dir", "")),
            hemispheres=str(section.get("hemispheres", "both")),
            backend=str(section.get("backend", "pyflatten")),
            output_dir=str(section.get("output_dir", "")),
        )

    def list_configs(self) -> list[AutoflattenConfigSummary]:
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

        Validates the YAML parses and contains a top-level
        ``autoflatten:`` section before writing. Rejects filenames
        with directory components.

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

        if not isinstance(parsed, dict) or not isinstance(parsed.get('autoflatten'), dict):
            return {'saved': False, 'path': '', 'errors': [
                "Config must have a top-level `autoflatten:` mapping",
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
