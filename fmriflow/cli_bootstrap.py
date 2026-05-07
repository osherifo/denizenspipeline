"""CLI subcommands that bootstrap and inspect the working directory.

- ``fmriflow init``     — materialise ``$FMRIFLOW_HOME`` layout
- ``fmriflow paths``    — print resolved paths
- ``fmriflow migrate``  — copy legacy locations into the new layout
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fmriflow.core import paths


def add_subcommands(subparsers) -> None:
    """Wire ``init`` / ``paths`` / ``migrate`` into the top-level CLI."""
    init = subparsers.add_parser(
        "init",
        help="Materialise the $FMRIFLOW_HOME layout (idempotent)",
    )
    init.set_defaults(_dispatch="bootstrap_init")

    p = subparsers.add_parser(
        "paths",
        help="Print resolved working-directory paths",
    )
    p.set_defaults(_dispatch="bootstrap_paths")

    m = subparsers.add_parser(
        "migrate",
        help="Copy legacy ~/.fmriflow/* and ./experiments/* into $FMRIFLOW_HOME",
    )
    m.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be copied; don't write anything",
    )
    m.set_defaults(_dispatch="bootstrap_migrate")


def dispatch(args) -> int:
    """Execute whichever bootstrap command is set on *args*."""
    name = getattr(args, "_dispatch", None)
    if name == "bootstrap_init":
        return _cmd_init(args)
    if name == "bootstrap_paths":
        return _cmd_paths(args)
    if name == "bootstrap_migrate":
        return _cmd_migrate(args)
    return 1


def _cmd_init(_args) -> int:
    """Create the $FMRIFLOW_HOME tree and seed subjects.json from the example."""
    home = paths.home()  # auto-creates
    # Touch every subdir so the layout exists even on a fresh install.
    paths.runs_dir()
    paths.configs_root()
    for stage in ("convert", "preproc", "autoflatten", "workflows"):
        paths.config_dir(stage)
    for kind in ("heuristics", "workflows", "modules"):
        paths.addons_dir(kind)
    for store in ("structural_qc", "post_preproc_workflows"):
        paths.store_dir(store)
    paths.secrets_dir()

    # Seed subjects.json from the bundled example if absent.
    db = paths.subjects_db()
    if not db.exists():
        example = paths.builtin() / "subjects.example.json"
        if example.is_file():
            shutil.copy2(example, db)
            print(f"[init] Seeded {db} from builtin/subjects.example.json")

    # Stamp the layout version so future migrations have a hook.
    version_file = home / "version.txt"
    if not version_file.exists():
        version_file.write_text("1\n")

    print(f"[init] $FMRIFLOW_HOME ready at {home}")
    return 0


def _cmd_paths(_args) -> int:
    """Print every resolved path, JSON-friendly."""
    description = paths.describe()
    width = max(len(k) for k in description) + 2
    for k, v in description.items():
        print(f"{k.ljust(width)}{v}")
    return 0


def _cmd_migrate(args) -> int:
    """Copy legacy locations into the new layout."""
    dry = bool(args.dry_run)
    plan: list[tuple[Path, Path]] = []

    legacy_dot = paths.LEGACY_DOTDIR
    if legacy_dot.is_dir():
        plan.extend([
            (legacy_dot / "runs", paths.runs_dir()),
            (legacy_dot / "modules", paths.addons_dir("modules")),
            (legacy_dot / "heuristics", paths.addons_dir("heuristics")),
            (legacy_dot / "structural_qc", paths.store_dir("structural_qc")),
            (legacy_dot / "post_preproc_workflows", paths.store_dir("post_preproc_workflows")),
            (legacy_dot / "convert_configs", paths.config_dir("convert")),
        ])

    legacy_exp = Path("./experiments").resolve()
    if legacy_exp.is_dir():
        for stage in ("convert", "preproc", "autoflatten", "workflows"):
            plan.append((legacy_exp / stage, paths.config_dir(stage)))

    legacy_results = Path("./results").resolve()
    if legacy_results.is_dir():
        plan.append((legacy_results, paths.results_root()))

    legacy_derivs = Path("./derivatives").resolve()
    if legacy_derivs.is_dir():
        plan.append((legacy_derivs, paths.derivatives_root()))

    # Filter out missing sources.
    plan = [(s, d) for s, d in plan if s.is_dir()]

    if not plan:
        print("[migrate] Nothing to copy — no legacy locations found.")
        return 0

    print("[migrate] Plan:")
    for src, dst in plan:
        print(f"  {src} -> {dst}")
    if dry:
        print("[migrate] --dry-run; nothing copied.")
        return 0

    for src, dst in plan:
        dst.mkdir(parents=True, exist_ok=True)
        for entry in src.iterdir():
            target = dst / entry.name
            if target.exists():
                print(f"[migrate] skip (exists) {target}")
                continue
            if entry.is_dir():
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)
            print(f"[migrate] copy {entry} -> {target}")

    print("[migrate] Done. Legacy locations are untouched; remove them when ready.")
    return 0
