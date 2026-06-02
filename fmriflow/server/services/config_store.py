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
    # 'subject' for a single-subject pipeline yaml; 'group' for a
    # GroupOrchestrator config (top-level 'group:' + 'subjects:' list).
    kind: str = "subject"
    # For group configs only: list of subject IDs in the subjects: block.
    group_subjects: list[str] = field(default_factory=list)


class ConfigStore:
    """Indexes analysis config files from
    ``$FMRIFLOW_HOME/configs/analysis/``.

    Falls back read-only to two legacy locations so existing
    installs keep working through one migration window:

    1. ``$FMRIFLOW_HOME/configs/*.yaml`` — where an earlier version
       of this code put analysis YAMLs before the
       per-stage-subdirectory layout was finalised.
    2. ``./experiments/*.yaml`` — the original cwd-relative layout.

    Same-name files in the primary directory shadow the legacy
    versions. Writes always go to the primary dir.
    """

    def __init__(self, configs_dir: Path):
        self.configs_dir = configs_dir
        self._cache: list[ConfigSummary] = []
        self._last_scan = 0.0
        # Legacy read-only fallback. Top-level only; stage subdirs
        # (convert/, preproc/, …) are owned by their own stores.
        self._legacy_dirs = [
            self.configs_dir.parent if self.configs_dir.name == "analysis" else None,
            Path("./experiments").resolve(),
        ]
        self._legacy_dirs = [d for d in self._legacy_dirs if d is not None]

    def _yamls_with_legacy_fallback(self) -> list[Path]:
        """Return YAML paths to scan, primary-tier first, no dups.

        Walks:
          * ``<configs_dir>/*.yaml`` (subject configs)
          * ``<configs_dir>/group/*.yaml`` (group configs — new tier)
          * legacy ``./experiments/*.yaml`` (subject)
          * legacy ``./experiments/group/*.yaml`` (group)
        """
        seen: set[str] = set()
        out: list[Path] = []

        def add_glob(d: Path) -> None:
            if not d.is_dir():
                return
            for p in sorted(d.glob("*.yaml")):
                if p.name not in seen:
                    seen.add(p.name)
                    out.append(p)

        # Primary tier: configs_dir and its group/ subdir.
        if self.configs_dir.is_dir():
            add_glob(self.configs_dir)
            add_glob(self.configs_dir / "group")

        # Legacy: ./experiments/ and ./experiments/group/, plus the
        # parent of configs_dir (older layout).
        for legacy in self._legacy_dirs:
            try:
                if legacy.resolve() == self.configs_dir.resolve():
                    continue  # same dir, already scanned
            except Exception:
                pass
            add_glob(legacy)
            add_glob(legacy / "group")
        return out

    def scan(self) -> None:
        """Re-scan configs directory for .yaml files."""
        self._cache = []
        for yaml_path in self._yamls_with_legacy_fallback():
            try:
                summary = self._extract_summary(yaml_path)
                if summary:
                    self._cache.append(summary)
            except Exception as e:
                logger.debug("Skipping %s: %s", yaml_path, e)

        self._last_scan = time.time()
        logger.info(
            "Scanned %d config(s) (primary: %s)", len(self._cache), self.configs_dir,
        )

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

        # Group-vs-subject kind detection. A group config has a top-level
        # 'group:' key (the group name) AND a 'subjects:' list. Subject
        # configs have 'subject:' (singular).
        is_group = (
            isinstance(config.get("group"), str)
            and isinstance(config.get("subjects"), list)
        )
        kind = "group" if is_group else "subject"
        group_subjects: list[str] = (
            [str(s) for s in config["subjects"]] if is_group else []
        )

        # Extract feature names
        features = []
        for f in config.get('features', []):
            if isinstance(f, dict) and 'name' in f:
                features.append(f['name'])

        # Preparation type
        prep = config.get('preparation', {})
        prep_type = prep.get('type', 'default') if isinstance(prep, dict) else 'default'

        if kind == "group":
            # For group configs the model/features/etc live under
            # subject_template. Lift the relevant fields up so the
            # browser shows useful info.
            template = config.get("subject_template", {}) or {}
            template = template if isinstance(template, dict) else {}
            features = []
            for f in template.get("features", []) or []:
                if isinstance(f, dict) and "name" in f:
                    features.append(f["name"])
            model_obj = template.get("model", {})
            model_type = (
                model_obj.get("type", "") if isinstance(model_obj, dict) else ""
            )
            prep_obj = template.get("preparation", {})
            prep_type = (
                prep_obj.get("type", "default") if isinstance(prep_obj, dict) else "default"
            )
            stim_obj = template.get("stimulus", {})
            stimulus_loader = (
                stim_obj.get("loader", "") if isinstance(stim_obj, dict) else ""
            )
            resp_obj = template.get("response", {})
            response_loader = (
                resp_obj.get("loader", "") if isinstance(resp_obj, dict) else ""
            )
            experiment = config.get("group", stem)
            subject = ""  # not applicable
        else:
            model_obj = config.get("model")
            model_type = (
                model_obj.get("type", "") if isinstance(model_obj, dict) else ""
            )
            stim_obj = config.get("stimulus")
            stimulus_loader = (
                stim_obj.get("loader", "") if isinstance(stim_obj, dict) else ""
            )
            resp_obj = config.get("response")
            response_loader = (
                resp_obj.get("loader", "") if isinstance(resp_obj, dict) else ""
            )
            experiment = config.get("experiment", stem)
            subject = config.get("subject", "")

        output_dir = ""
        rpt = config.get("reporting")
        if isinstance(rpt, dict):
            output_dir = rpt.get("output_dir", "")
        if not output_dir:
            output_dir = config.get("output_dir", "")

        return ConfigSummary(
            filename=filename,
            path=str(path.resolve()),
            experiment=experiment,
            subject=subject,
            model_type=model_type,
            features=features,
            output_dir=output_dir,
            group=group,
            preparation_type=prep_type,
            stimulus_loader=stimulus_loader,
            response_loader=response_loader,
            kind=kind,
            group_subjects=group_subjects,
        )

    def list_configs(self) -> list[ConfigSummary]:
        """Return summaries of all configs."""
        self._maybe_rescan()
        return self._cache

    def get_config(self, filename: str) -> dict[str, Any] | None:
        """Return full parsed config + raw YAML for one config file.

        Returns dict with keys: filename, path, config, yaml_string.
        Returns None if not found.

        Looks up by filename via the cached summaries first (so group
        configs under ``<configs_dir>/group/`` or ``./experiments/group/``
        resolve correctly), and falls back to the primary configs_dir
        for any file not yet seen by a scan.
        """
        self._maybe_rescan()
        path: Path | None = None
        for cfg in self._cache:
            if cfg.filename == filename:
                path = Path(cfg.path)
                break
        if path is None:
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

    def save_config(self, filename: str, yaml_string: str) -> dict[str, Any]:
        """Overwrite (or create) a config file with raw YAML.

        Validates the YAML parses before writing. Rejects paths that
        would escape ``configs_dir`` (no directory components allowed).

        Returns dict with keys: saved (bool), path, errors (list[str]).
        """
        # Disallow directory components — filename only.
        if '/' in filename or '\\' in filename or filename in ('.', '..'):
            return {'saved': False, 'path': '', 'errors': [
                f"Invalid filename: {filename!r}",
            ]}
        if not filename.endswith(('.yaml', '.yml')):
            return {'saved': False, 'path': '', 'errors': [
                "Config filename must end in .yaml or .yml",
            ]}

        # Ensure YAML parses before writing.
        try:
            yaml.safe_load(yaml_string)
        except yaml.YAMLError as e:
            return {'saved': False, 'path': '', 'errors': [f'YAML parse error: {e}']}

        path = self.configs_dir / filename
        try:
            self.configs_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml_string)
        except OSError as e:
            return {'saved': False, 'path': str(path), 'errors': [f'Write failed: {e}']}

        # Invalidate cache so next list_configs() re-scans.
        self._last_scan = 0.0

        return {'saved': True, 'path': str(path.resolve()), 'errors': []}

    def copy_config(self, source: str, new_filename: str) -> dict[str, Any]:
        """Duplicate an existing config under a new filename.

        Refuses to overwrite an existing file — pick a name that doesn't
        collide. Returns dict with keys: saved, path, errors.
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
