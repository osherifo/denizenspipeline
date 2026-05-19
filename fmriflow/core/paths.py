"""Single source of truth for every on-disk location fmriflow uses.

Two-tier model:

- **builtin** — content shipped inside the package
  (``fmriflow/builtin/``). Read-only at runtime.
- **user** — content under ``$FMRIFLOW_HOME``
  (default ``~/projects/fmriflow/``). Everything the user owns:
  addons, configs, runs, stores, and (by default) data.

Resolution for tiered content (heuristics, workflow templates,
addon modules) is **user > builtin** — drop a file with the same
name into ``$FMRIFLOW_HOME/addons/<kind>/`` and it shadows the
shipped built-in.

The ``data/`` subtree (BIDS, derivatives, work, results) lives
under ``$FMRIFLOW_HOME/data/`` by default. Power users can set
``$FMRIFLOW_DATA`` to put it on a different disk.

Legacy paths (``~/.fmriflow/``, ``./experiments/``, ``./results/``)
are still consulted as a read-only fallback for two minor versions
to ease migration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal


# ── Env vars + defaults ──────────────────────────────────────────────

ENV_HOME = "FMRIFLOW_HOME"
ENV_DATA = "FMRIFLOW_DATA"
ENV_FS_LICENSE = "FS_LICENSE"
ENV_SINGULARITY_BIN = "FMRIFLOW_SINGULARITY_BIN"

DEFAULT_HOME = Path.home() / "projects" / "fmriflow"

# Runtime config — written by the Settings tab. Sits below env
# vars in precedence so an explicit shell export always wins.
RUNTIME_CONFIG_PATH = Path.home() / ".config" / "fmriflow" / "settings.json"

_RUNTIME_KEYS = {"FMRIFLOW_HOME", "FMRIFLOW_DATA", "FS_LICENSE", "FMRIFLOW_SINGULARITY_BIN"}


def _load_runtime_config() -> dict[str, str]:
    """Return persisted runtime overrides (or {} if none)."""
    p = RUNTIME_CONFIG_PATH
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text())
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: str(v) for k, v in data.items() if k in _RUNTIME_KEYS and v}


def save_runtime_config(updates: dict[str, str | None]) -> dict[str, str]:
    """Merge *updates* into the persisted runtime config and return the result.

    Keys with empty/None values are removed (so the env var or
    default takes over). Unknown keys are ignored.
    """
    current = _load_runtime_config()
    for key, value in updates.items():
        if key not in _RUNTIME_KEYS:
            continue
        if value:
            current[key] = str(value)
        else:
            current.pop(key, None)
    RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIG_PATH.write_text(json.dumps(current, indent=2) + "\n")
    return current


def _resolve_env(key: str) -> str | None:
    """Return the effective value for *key*: env var > runtime config."""
    val = os.environ.get(key)
    if val:
        return val
    cfg = _load_runtime_config()
    return cfg.get(key)

# Legacy locations — consulted as read-only fallback.
LEGACY_DOTDIR = Path.home() / ".fmriflow"
LEGACY_EXPERIMENTS = Path("./experiments")
LEGACY_RESULTS = Path("./results")
LEGACY_DERIVATIVES = Path("./derivatives")


AddonKind = Literal[
    "heuristics", "workflows", "modules", "transforms", "pipelines",
]
BuiltinKind = Literal[
    "heuristics", "workflows", "modules", "text", "transforms", "pipelines",
]


# ── Roots ────────────────────────────────────────────────────────────

def home() -> Path:
    """Return ``$FMRIFLOW_HOME``, auto-creating it on first use.

    Resolution: env var > settings.json > default
    (``~/projects/fmriflow``).
    """
    raw = _resolve_env(ENV_HOME)
    p = Path(raw).expanduser() if raw else DEFAULT_HOME
    p.mkdir(parents=True, exist_ok=True)
    return p


def data() -> Path:
    """Return ``$FMRIFLOW_DATA`` (defaults to ``home() / 'data'``).

    Unlike :func:`home`, an explicitly configured but missing data
    root raises — accidentally creating a TB tree in the wrong place
    is bad. The default ``home()/data`` is auto-created.
    """
    raw = _resolve_env(ENV_DATA)
    if raw:
        p = Path(raw).expanduser()
        if not p.exists():
            raise FileNotFoundError(
                f"$FMRIFLOW_DATA points to {p} which does not exist. "
                "Create it manually or unset $FMRIFLOW_DATA to use "
                "the default ($FMRIFLOW_HOME/data)."
            )
        return p
    p = home() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def builtin() -> Path:
    """Return the package-bundled ``fmriflow/builtin/`` directory."""
    # __file__ is fmriflow/core/paths.py → parent.parent is fmriflow/
    return Path(__file__).resolve().parent.parent / "builtin"


# ── User-tier subdirectories ─────────────────────────────────────────

def runs_dir() -> Path:
    p = home() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir(stage: str) -> Path:
    """``$FMRIFLOW_HOME/configs/<stage>/`` — convert / preproc / etc."""
    p = home() / "configs" / stage
    p.mkdir(parents=True, exist_ok=True)
    return p


def configs_root() -> Path:
    p = home() / "configs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def addons_dir(kind: AddonKind) -> Path:
    """``$FMRIFLOW_HOME/addons/<kind>/`` — user-provided overrides."""
    p = home() / "addons" / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


def store_dir(name: str) -> Path:
    """``$FMRIFLOW_HOME/stores/<name>/`` — named state stores."""
    p = home() / "stores" / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def secrets_dir() -> Path:
    p = home() / "secrets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def license_file() -> Path:
    """Path to the FreeSurfer license file (may not exist).

    Resolution: ``$FS_LICENSE`` env var > settings.json > default
    (``$FMRIFLOW_HOME/secrets/freesurfer-license.txt``).
    """
    raw = _resolve_env(ENV_FS_LICENSE)
    if raw:
        return Path(raw).expanduser()
    return secrets_dir() / "freesurfer-license.txt"


def singularity_bin() -> str | None:
    """Return the apptainer/singularity binary path if configured."""
    return _resolve_env(ENV_SINGULARITY_BIN)


def subjects_db() -> Path:
    """Path to the user's ``subjects.json`` (may not exist)."""
    return home() / "subjects.json"


# ── Builtin-tier subdirectories ──────────────────────────────────────

def builtin_dir(kind: BuiltinKind) -> Path:
    """Path to a bundled subtree (read-only, always exists)."""
    return builtin() / kind


# ── Data subtree ─────────────────────────────────────────────────────

def bids_root() -> Path:
    p = data() / "bids"
    p.mkdir(parents=True, exist_ok=True)
    return p


def dicoms_root() -> Path:
    p = data() / "dicoms"
    p.mkdir(parents=True, exist_ok=True)
    return p


def derivatives_root() -> Path:
    p = data() / "derivatives"
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_root() -> Path:
    p = data() / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p


def work_root() -> Path:
    p = data() / "work"
    p.mkdir(parents=True, exist_ok=True)
    return p


def derivatives_dir(study: str) -> Path:
    p = derivatives_root() / study
    p.mkdir(parents=True, exist_ok=True)
    return p


def bids_dir(study: str) -> Path:
    p = bids_root() / study
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir(study: str, run: str | None = None) -> Path:
    base = results_root() / study
    p = base / run if run else base
    p.mkdir(parents=True, exist_ok=True)
    return p


def work_dir(run_id: str) -> Path:
    p = work_root() / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Two-tier resolution ──────────────────────────────────────────────

def find_in_tiers(kind: AddonKind, name: str) -> Path | None:
    """Resolve a named addon to a real path.

    Looks under ``$FMRIFLOW_HOME/addons/<kind>/<name>`` first, then
    ``fmriflow/builtin/<kind>/<name>``. Returns ``None`` if neither
    exists.
    """
    user = addons_dir(kind) / name
    if user.exists():
        return user
    bundled = builtin() / kind / name
    if bundled.exists():
        return bundled
    return None


# ── Legacy fallback helpers (read-only) ──────────────────────────────

def legacy_runs_root() -> Path:
    return LEGACY_DOTDIR / "runs"


def legacy_modules_root() -> Path:
    return LEGACY_DOTDIR / "modules"


def legacy_heuristics_root() -> Path:
    return LEGACY_DOTDIR / "heuristics"


def legacy_store_dir(name: str) -> Path:
    return LEGACY_DOTDIR / name


def legacy_convert_configs_root() -> Path:
    return LEGACY_DOTDIR / "convert_configs"


# ── Debug helper used by ``fmriflow paths`` ──────────────────────────

def describe() -> dict[str, str]:
    """Return a human-readable mapping of every resolved root.

    Used by the ``fmriflow paths`` CLI subcommand and by the server
    on startup to log the resolved layout. ``$FMRIFLOW_DATA`` may
    be configured to a missing path; in that case the data-derived
    entries report the error string rather than raising.
    """
    try:
        data_root = data()
        data_str = str(data_root)
    except FileNotFoundError as e:
        data_str = f"<error: {e}>"
        data_root = None

    out = {
        "FMRIFLOW_HOME": str(home()),
        "FMRIFLOW_DATA": data_str,
        "builtin": str(builtin()),
        "runs": str(home() / "runs"),
        "configs": str(home() / "configs"),
        "addons": str(home() / "addons"),
        "stores": str(home() / "stores"),
        "license_file": str(license_file()),
        "subjects_db": str(subjects_db()),
    }
    if data_root is not None:
        out["bids_root"] = str(data_root / "bids")
        out["derivatives_root"] = str(data_root / "derivatives")
        out["results_root"] = str(data_root / "results")
        out["work_root"] = str(data_root / "work")
    return out


def settings_snapshot() -> dict[str, object]:
    """Return a structured view for the Settings UI.

    For each writable key, reports the source (env var / persisted /
    default) so the UI can show why each value is what it is.
    """
    persisted = _load_runtime_config()
    snapshot: dict[str, object] = {
        "runtime_config_path": str(RUNTIME_CONFIG_PATH),
        "values": {},
        "resolved": describe(),
    }
    for key in (ENV_HOME, ENV_DATA, ENV_FS_LICENSE, ENV_SINGULARITY_BIN):
        env_val = os.environ.get(key)
        persisted_val = persisted.get(key)
        if env_val:
            source = "env"
            effective = env_val
        elif persisted_val:
            source = "persisted"
            effective = persisted_val
        else:
            source = "default"
            effective = ""
        snapshot["values"][key] = {  # type: ignore[index]
            "env": env_val,
            "persisted": persisted_val,
            "effective": effective,
            "source": source,
        }
    # Diagnostic flags the UI surfaces:
    snapshot["license_file_exists"] = license_file().is_file()
    sd = subjects_db()
    snapshot["subjects_db_exists"] = sd.is_file()
    if sd.is_file():
        try:
            obj = json.loads(sd.read_text())
            snapshot["subjects_db_count"] = len([k for k in obj if not k.startswith("_")])
        except Exception:
            snapshot["subjects_db_count"] = None
    return snapshot
