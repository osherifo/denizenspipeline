"""ConfigStore — indexes experiment config YAML files from a directory."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ConfigSummary:
    """Lightweight metadata extracted from a config YAML."""
    filename: str
    path: str
    experiment: str
    subject: str
    model_type: str
    features: list[str]
    output_dir: str
    group: str
    preparation_type: str
    stimulus_loader: str
    response_loader: str


class ConfigStore:
    """Indexes experiment config files from a directory."""

    def __init__(self, configs_dir: Path):
        self.configs_dir = configs_dir
        self._cache: list[ConfigSummary] = []
        self._last_scan = 0.0

    def scan(self) -> None:
        """Re-scan configs directory for .yaml files."""
        self._cache = []
        if not self.configs_dir.is_dir():
            logger.warning("Configs directory not found: %s", self.configs_dir)
            return

        for yaml_path in sorted(self.configs_dir.glob('*.yaml')):
            try:
                summary = self._extract_summary(yaml_path)
                if summary:
                    self._cache.append(summary)
            except Exception as e:
                logger.debug("Skipping %s: %s", yaml_path, e)

        self._last_scan = time.time()
        logger.info("Scanned %d config(s) from %s", len(self._cache), self.configs_dir)

    def _maybe_rescan(self) -> None:
        """Re-scan if cache is stale (>10s)."""
        if time.time() - self._last_scan > 10.0:
            self.scan()

    def _extract_summary(self, path: Path) -> ConfigSummary | None:
        """Extract lightweight summary from a YAML config."""
        with open(path) as f:
            config = yaml.safe_load(f) or {}

        if not isinstance(config, dict):
            return None

        filename = path.name
        # Skip private/anchor-only files
        if filename.startswith('_'):
            return None

        # Auto-derive group from filename prefix
        stem = path.stem
        parts = stem.split('_')
        group = parts[0] if len(parts) > 1 else stem

        # Extract feature names
        features = []
        for f in config.get('features', []):
            if isinstance(f, dict) and 'name' in f:
                features.append(f['name'])

        # Preparation type
        prep = config.get('preparation', {})
        prep_type = prep.get('type', 'default') if isinstance(prep, dict) else 'default'

        return ConfigSummary(
            filename=filename,
            path=str(path.resolve()),
            experiment=config.get('experiment', stem),
            subject=config.get('subject', ''),
            model_type=config.get('model', {}).get('type', '') if isinstance(config.get('model'), dict) else '',
            features=features,
            output_dir=config.get('reporting', {}).get('output_dir', '') if isinstance(config.get('reporting'), dict) else '',
            group=group,
            preparation_type=prep_type,
            stimulus_loader=config.get('stimulus', {}).get('loader', '') if isinstance(config.get('stimulus'), dict) else '',
            response_loader=config.get('response', {}).get('loader', '') if isinstance(config.get('response'), dict) else '',
        )

    def list_configs(self) -> list[ConfigSummary]:
        """Return summaries of all configs."""
        self._maybe_rescan()
        return self._cache

    def get_config(self, filename: str) -> dict[str, Any] | None:
        """Return full parsed config + raw YAML for one config file.

        Returns dict with keys: filename, path, config, yaml_string.
        Returns None if not found.
        """
        self._maybe_rescan()
        path = self.configs_dir / filename
        if not path.is_file():
            return None

        raw = path.read_text()
        try:
            config = yaml.safe_load(raw) or {}
        except Exception:
            config = {}

        return {
            'filename': filename,
            'path': str(path.resolve()),
            'config': config,
            'yaml_string': raw,
        }

    def field_values(self) -> dict[str, list[str]]:
        """Collect unique string/path values per dotted field path across all configs.

        Used by the frontend Composer for autocomplete suggestions.
        """
        self._maybe_rescan()
        buckets: dict[str, set[str]] = {}

        for yaml_path in sorted(self.configs_dir.glob('*.yaml')):
            if yaml_path.name.startswith('_'):
                continue
            try:
                with open(yaml_path) as f:
                    config = yaml.safe_load(f) or {}
                if isinstance(config, dict):
                    self._walk_config(config, '', buckets)
            except Exception:
                continue

        # Convert sets to sorted lists, drop empty strings
        return {k: sorted(v - {''}) for k, v in buckets.items() if v - {''}}

    def _walk_config(
        self,
        obj: Any,
        prefix: str,
        buckets: dict[str, set[str]],
    ) -> None:
        """Recursively walk a config dict and collect string values.

        For dict-valued fields (like run_map, paths), also stores the whole
        dict as a compact JSON string so it can be offered as a suggestion.
        """
        if isinstance(obj, dict):
            for key, val in obj.items():
                # Skip private/anchor keys
                if isinstance(key, str) and key.startswith('_'):
                    continue
                path = f"{prefix}.{key}" if prefix else key
                # If the value is a dict of scalars, also store it whole as JSON
                if isinstance(val, dict) and val and all(
                    isinstance(v, (str, int, float)) for v in val.values()
                ):
                    import json
                    buckets.setdefault(path, set()).add(
                        json.dumps(val, ensure_ascii=False)
                    )
                self._walk_config(val, path, buckets)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    self._walk_config(item, prefix, buckets)
                elif isinstance(item, str):
                    buckets.setdefault(prefix, set()).add(item)
        elif isinstance(obj, str):
            buckets.setdefault(prefix, set()).add(obj)

    def validate_config(self, filename: str) -> dict[str, Any]:
        """Run full validation on a config file.

        Returns dict with keys: valid, errors.
        """
        path = self.configs_dir / filename
        if not path.is_file():
            return {'valid': False, 'errors': [f'Config file not found: {filename}']}

        try:
            from fmriflow.config.loader import load_config
            load_config(path)
            return {'valid': True, 'errors': []}
        except Exception as e:
            errors = list(e.args[0]) if isinstance(e.args[0], list) else [str(e)]
            return {'valid': False, 'errors': errors}
