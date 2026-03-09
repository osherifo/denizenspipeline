"""Subject database — central lookup for per-subject pycortex metadata.

Loads a JSON file (e.g. ``surfaces.json``) that maps subject IDs to
surface/transform/masktype.  The config loader calls ``resolve_subject_config``
to fill in ``subject_config`` fields that the experiment YAML didn't set
explicitly, so configs can be as minimal as ``subject: TYE``.

Resolution order (explicit config always wins):
    1. Experiment YAML ``subject_config.surface`` -> used as-is
    2. If missing -> looked up from the subject database

The DB file is located via (first match wins):
    1. ``paths.subjects_db`` in config
    2. ``DENIZENS_SUBJECTS_DB`` env var
    3. ``subjects.json`` in the config file's directory
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Fields that can be resolved from the DB into subject_config
_DB_FIELDS = ("surface", "transform", "masktype")


def resolve_subject_config(config: dict, config_dir: Path | None = None) -> dict:
    """Merge subject database values into *config* (in-place).

    Only fills in ``subject_config`` keys that are **not** already set in the
    experiment YAML.  Returns the (possibly mutated) config.
    """
    subject = config.get("subject")
    if not subject:
        return config

    sub_cfg = config.get("subject_config", {})

    # If all fields are already explicit, nothing to do
    if all(sub_cfg.get(f) for f in _DB_FIELDS):
        return config

    db = _load_db(config, config_dir)
    if db is None:
        return config

    entry = db.get(subject)
    if entry is None:
        return config

    # Merge missing fields from DB into subject_config
    if "subject_config" not in config:
        config["subject_config"] = {}
    for field in _DB_FIELDS:
        if not config["subject_config"].get(field) and entry.get(field):
            config["subject_config"][field] = entry[field]
            logger.info("subject_db: %s.%s = %s (from DB)", subject, field, entry[field])

    return config


def _load_db(config: dict, config_dir: Path | None) -> dict | None:
    """Locate and load the subject database file.

    Returns a flat dict: ``{subject_name: {surface, transform, masktype, ...}}``.
    For JSON files where values are arrays (like surfaces.json), the first entry
    with ``description == "default"`` is used, falling back to the first entry.
    """
    db_path = _find_db_path(config, config_dir)
    if db_path is None or not db_path.exists():
        return None

    logger.debug("Loading subject database from %s", db_path)

    with open(db_path) as f:
        raw = json.load(f)

    # Normalise: surfaces.json stores arrays of configs per subject
    db: dict[str, dict] = {}
    for subj, value in raw.items():
        if isinstance(value, list):
            # Pick the "default" entry, or the first one
            entry = next((e for e in value if e.get("description") == "default"), value[0])
            db[subj] = entry
        elif isinstance(value, dict):
            db[subj] = value
        else:
            continue

    return db


def _find_db_path(config: dict, config_dir: Path | None) -> Path | None:
    """Search for the subject database file."""
    # 1. Explicit path in config
    explicit = config.get("paths", {}).get("subjects_db")
    if explicit:
        return Path(explicit).expanduser()

    # 2. Environment variable
    env = os.environ.get("DENIZENS_SUBJECTS_DB")
    if env:
        return Path(env).expanduser()

    # 3. subjects.json next to the config file
    if config_dir:
        candidate = config_dir / "subjects.json"
        if candidate.exists():
            return candidate

    # 4. Built-in package data
    pkg_data = Path(__file__).resolve().parent.parent / "data" / "subjects.json"
    if pkg_data.exists():
        return pkg_data

    return None
