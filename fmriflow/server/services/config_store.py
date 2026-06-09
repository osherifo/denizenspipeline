"""ConfigStore — indexes experiment config YAML files from a directory."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _rebrand_yaml(yaml_text: str, new_name: str) -> tuple[str, str | None]:
    """Rewrite a duplicated config so it has a fresh run identity.

    Replaces every whole-token occurrence of the source's top-level
    identifier (``study:`` / ``group:`` / ``experiment:`` field) with
    ``new_name``. Done as a text-level substitution to preserve YAML
    comments and formatting. The same substitution sweeps every
    occurrence of the identifier *as a path segment or full token*
    (e.g. inside ``output_dir``, nested ``subject_template.experiment``)
    so the duplicate doesn't accidentally write into the source's run
    directory.

    Returns ``(rewritten_text, old_name)``. ``old_name`` is None when
    nothing was rebranded (config didn't have a recognised identifier).
    """
    try:
        cfg = yaml.safe_load(yaml_text) or {}
    except Exception:
        return yaml_text, None
    if not isinstance(cfg, dict):
        return yaml_text, None

    # Order matters: study > group > experiment (a study YAML may also
    # carry an `experiment:` for documentation).
    old_name: str | None = None
    for key in ('study', 'group', 'experiment'):
        val = cfg.get(key)
        if isinstance(val, str) and val:
            old_name = val
            break
    if not old_name or old_name == new_name:
        return yaml_text, old_name

    # Replace `old_name` everywhere it appears as a whole identifier
    # or path segment. ``\w`` matches [A-Za-z0-9_]; we leave it
    # untouched if it's adjacent to another word char (so we don't
    # rewrite ``foo_bar`` when old_name=``foo``). Path separators
    # ``/`` and ``-`` are *not* word chars, so paths like
    # ``./runs/<old>/sub`` are rewritten correctly.
    pattern = re.compile(rf'(?<!\w){re.escape(old_name)}(?!\w)')
    return pattern.sub(new_name, yaml_text), old_name


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
    # GroupOrchestrator config (top-level 'group:' + 'subjects:' list);
    # 'study' for a StudyOrchestrator config (top-level 'study:' +
    # 'groups:' list).
    kind: str = "subject"
    # For group configs only: list of subject IDs in the subjects: block.
    group_subjects: list[str] = field(default_factory=list)
    # For study configs only: list of study-scope group labels.
    study_groups: list[str] = field(default_factory=list)


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
          * ``<configs_dir>/group/*.yaml`` (group configs)
          * ``<configs_dir>/study/*.yaml`` (study configs — new tier)
          * legacy ``./experiments/*.yaml`` (subject)
          * legacy ``./experiments/group/*.yaml`` (group)
          * legacy ``./experiments/study/*.yaml`` (study)
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

        # Primary tier: configs_dir + group/ + study/ subdirs.
        if self.configs_dir.is_dir():
            add_glob(self.configs_dir)
            add_glob(self.configs_dir / "group")
            add_glob(self.configs_dir / "study")

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
            add_glob(legacy / "study")
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

        # Kind detection. Order matters: study takes precedence over
        # group (a malformed YAML that has both top-level study: and
        # group: will be classified as study so the user sees the
        # higher-scope kind in the UI).
        is_study = (
            isinstance(config.get("study"), str)
            and isinstance(config.get("groups"), list)
        )
        is_group = (not is_study) and (
            isinstance(config.get("group"), str)
            and isinstance(config.get("subjects"), list)
        )
        if is_study:
            kind = "study"
        elif is_group:
            kind = "group"
        else:
            kind = "subject"
        group_subjects: list[str] = (
            [str(s) for s in config["subjects"]] if is_group else []
        )
        study_groups: list[str] = []
        if is_study:
            for entry in config.get("groups") or []:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    study_groups.append(entry["name"])

        # Extract feature names
        features = []
        for f in config.get('features', []):
            if isinstance(f, dict) and 'name' in f:
                features.append(f['name'])

        # Preparation type
        prep = config.get('preparation', {})
        prep_type = prep.get('type', 'default') if isinstance(prep, dict) else 'default'

        if kind == "study":
            # Study configs don't carry model/features/etc directly —
            # those live inside each referenced group YAML. Surface the
            # study name as 'experiment' so the dashboard sidebar shows
            # something useful, and the group labels as 'features' so
            # the card preview is informative.
            model_type = ""
            stimulus_loader = ""
            response_loader = ""
            prep_type = "default"
            features = list(study_groups)
            experiment = config.get("study", stem)
            subject = ""
        elif kind == "group":
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
            study_groups=study_groups,
        )

    def list_configs(self) -> list[ConfigSummary]:
        """Return summaries of all configs."""
        self._maybe_rescan()
        return self._cache

    def _resolve_path(self, filename: str) -> Path | None:
        """Resolve a config filename to its on-disk path.

        Single source of truth for "where does this filename actually
        live?": consults the cached scan first (covers
        ``<configs_dir>/group/``, ``<configs_dir>/study/``, and the
        legacy ``./experiments/`` tree), then falls back to the
        primary top-level ``configs_dir`` for any file not yet seen
        by a scan. Returns ``None`` if the file doesn't exist anywhere.
        """
        self._maybe_rescan()
        for cfg in self._cache:
            if cfg.filename == filename:
                p = Path(cfg.path)
                if p.is_file():
                    return p
        fallback = self.configs_dir / filename
        return fallback if fallback.is_file() else None

    def get_config(self, filename: str) -> dict[str, Any] | None:
        """Return full parsed config + raw YAML for one config file.

        Returns dict with keys: filename, path, config, yaml_string.
        Returns None if not found.
        """
        path = self._resolve_path(filename)
        if path is None:
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

        # If the file already exists somewhere (group/, study/, or
        # legacy ./experiments/), overwrite in place — otherwise the
        # edit would create a stray top-level copy and the original
        # would shadow the edited version on next scan.
        existing = self._resolve_path(filename)
        path = existing if existing is not None else (self.configs_dir / filename)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml_string)
        except OSError as e:
            return {'saved': False, 'path': str(path), 'errors': [f'Write failed: {e}']}

        # Invalidate cache so next list_configs() re-scans.
        self._last_scan = 0.0

        return {'saved': True, 'path': str(path.resolve()), 'errors': []}

    def copy_config(self, source: str, new_filename: str) -> dict[str, Any]:
        """Duplicate an existing config under a new filename.

        Resolves the source via the cached scan (so configs living in
        ``<configs_dir>/group/``, ``<configs_dir>/study/``, or the
        legacy ``./experiments/`` tree are all reachable) and falls
        back to ``configs_dir / source``. The destination always lands
        under ``configs_dir`` (writable primary tier), preserving the
        source's ``group/`` or ``study/`` subdir if one was used.
        Refuses to overwrite an existing file.
        """
        if '/' in new_filename or '\\' in new_filename or new_filename in ('.', '..'):
            return {'saved': False, 'path': '', 'errors': [
                f"Invalid filename: {new_filename!r}",
            ]}
        if not new_filename.endswith(('.yaml', '.yml')):
            return {'saved': False, 'path': '', 'errors': [
                "Config filename must end in .yaml or .yml",
            ]}

        src = self._resolve_path(source)
        if src is None:
            return {'saved': False, 'path': '', 'errors': [
                f"Source config not found: {source}",
            ]}

        # Place the duplicate in the same scope subdir under primary.
        # If the source lived at ``<root>/group/foo.yaml`` (primary or
        # legacy), put the copy under ``configs_dir/group/``.
        parent = src.parent.name if src.parent.name in ('group', 'study') else ''
        dest_dir = self.configs_dir / parent if parent else self.configs_dir
        dest = dest_dir / new_filename
        if dest.exists():
            return {'saved': False, 'path': str(dest), 'errors': [
                f"Destination already exists: {new_filename}",
            ]}

        # Rebrand the identifier so the duplicate doesn't inherit the
        # source's run history. New identifier = the new filename's stem.
        new_stem = Path(new_filename).stem
        rebranded, old_name = _rebrand_yaml(src.read_text(), new_stem)

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(rebranded)
        except OSError as e:
            return {'saved': False, 'path': str(dest), 'errors': [f'Write failed: {e}']}

        self._last_scan = 0.0

        return {
            'saved': True,
            'path': str(dest.resolve()),
            'errors': [],
            'rebranded_from': old_name,
            'rebranded_to': new_stem if old_name and old_name != new_stem else None,
        }

    def validate_config(self, filename: str) -> dict[str, Any]:
        """Run full validation on a config file.

        Routes to the right schema validator based on the YAML's shape:
        ``study:`` + ``groups:`` → study schema, ``group:`` + ``subjects:`` →
        group schema, otherwise subject schema (via ``load_config`` so
        inheritance, defaults, and env vars are resolved before the
        subject schema runs).

        Returns dict with keys: valid, errors.
        """
        path = self._resolve_path(filename)
        if path is None:
            return {'valid': False, 'errors': [f'Config file not found: {filename}']}

        try:
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
        except Exception as e:
            return {'valid': False, 'errors': [f'YAML parse error: {e}']}
        if not isinstance(raw, dict):
            return {'valid': False, 'errors': ['Config must be a YAML mapping']}

        is_study = (
            isinstance(raw.get('study'), str)
            and isinstance(raw.get('groups'), list)
        )
        is_group = (not is_study) and (
            isinstance(raw.get('group'), str)
            and isinstance(raw.get('subjects'), list)
        )

        if is_study:
            from fmriflow.config.schema import validate_study_config
            errors = validate_study_config(raw)
            return {'valid': not errors, 'errors': errors}

        if is_group:
            from fmriflow.config.schema import (
                validate_group_config, validate_config as _validate_subject,
            )
            errors = list(validate_group_config(raw))
            # Also check that each subject's resolved config would pass
            # the subject schema at fan-out time. Catches things like a
            # subject_template missing ``split.test_runs`` before a run.
            if not errors:
                try:
                    from fmriflow.group_orchestrator import derive_subject_config
                    for subject in raw['subjects']:
                        sub_cfg = derive_subject_config(
                            raw, subject, validate=False)
                        sub_errs = _validate_subject(sub_cfg)
                        if sub_errs:
                            errors.extend(
                                f"subject '{subject}': {e}" for e in sub_errs)
                            break
                except Exception as e:
                    errors.append(f"subject_template check failed: {e}")
            return {'valid': not errors, 'errors': errors}

        # Subject config — load_config runs the full pipeline
        # (inheritance, defaults, env vars, subject schema).
        try:
            from fmriflow.config.loader import load_config
            load_config(path)
            return {'valid': True, 'errors': []}
        except Exception as e:
            errors = list(e.args[0]) if e.args and isinstance(e.args[0], list) else [str(e)]
            return {'valid': False, 'errors': errors}
