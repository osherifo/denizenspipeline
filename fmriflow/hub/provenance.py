"""Install-time provenance ledger.

Records where each installed artifact came from so the existing browsers can
badge it ("from <source> · lab/community"). Without this, a hub install is an
ordinary user-tier file and its origin is lost. Stored as a small JSON map at
``$FMRIFLOW_HOME/stores/hub/installed.json``, keyed ``<kind>:<key>`` where
*key* is the identifier the relevant browser uses (module name, config
filename, error id, heuristic name, …).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fmriflow.core import paths

logger = logging.getLogger(__name__)


def _ledger_path():
    return paths.hub_cache_dir() / "installed.json"


def _load() -> dict:
    p = _ledger_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


def record(kind: str, key: str, *, source, artifact_name: str, sha256: str) -> None:
    """Record that ``<kind>:<key>`` was installed from *source*."""
    data = _load()
    data[f"{kind}:{key}"] = {
        "source_id": source.id,
        "source_name": source.name,
        "tier": source.tier,
        "artifact_name": artifact_name,
        "sha256": sha256,
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _save(data)


def all_records() -> dict:
    return _load()


def forget(kind: str, key: str) -> None:
    data = _load()
    if data.pop(f"{kind}:{key}", None) is not None:
        _save(data)
