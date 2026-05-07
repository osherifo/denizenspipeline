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

import os
from pathlib import Path
from typing import Literal


# ── Env vars + defaults ──────────────────────────────────────────────

ENV_HOME = "FMRIFLOW_HOME"
ENV_DATA = "FMRIFLOW_DATA"

DEFAULT_HOME = Path.home() / "projects" / "fmriflow"

# Legacy locations — consulted as read-only fallback.
LEGACY_DOTDIR = Path.home() / ".fmriflow"
LEGACY_EXPERIMENTS = Path("./experiments")
LEGACY_RESULTS = Path("./results")
LEGACY_DERIVATIVES = Path("./derivatives")


AddonKind = Literal["heuristics", "workflows", "modules"]
BuiltinKind = Literal["heuristics", "workflows", "modules", "text"]


# ── Roots ────────────────────────────────────────────────────────────

def home() -> Path:
    """Return ``$FMRIFLOW_HOME``, auto-creating it on first use."""
    raw = os.environ.get(ENV_HOME)
    p = Path(raw).expanduser() if raw else DEFAULT_HOME
    p.mkdir(parents=True, exist_ok=True)
    return p


def data() -> Path:
    """Return ``$FMRIFLOW_DATA`` (defaults to ``home() / 'data'``).

    Unlike :func:`home`, missing ``$FMRIFLOW_DATA`` does **not**
    auto-create — accidentally creating a TB tree in the wrong place
    is bad. We do create the default ``home()/data`` if absent.
    """
    raw = os.environ.get(ENV_DATA)
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
    """Path to the FreeSurfer license file (may not exist)."""
    return secrets_dir() / "freesurfer-license.txt"


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
    on startup to log the resolved layout.
    """
    return {
        "FMRIFLOW_HOME": str(home()),
        "FMRIFLOW_DATA": str(data()),
        "builtin": str(builtin()),
        "runs": str(home() / "runs"),
        "configs": str(home() / "configs"),
        "addons": str(home() / "addons"),
        "stores": str(home() / "stores"),
        "license_file": str(license_file()),
        "subjects_db": str(subjects_db()),
        "bids_root": str(data() / "bids"),
        "derivatives_root": str(data() / "derivatives"),
        "results_root": str(data() / "results"),
        "work_root": str(data() / "work"),
    }
