"""CLI entry points for the triage subsystem.

Currently exposes one subcommand:

    fmriflow triage scan   — walk ~/.fmriflow/runs/, re-run the
                              extractor + matcher on failed runs
                              whose triage.json is missing or stale.

Useful when the KB grows new fingerprints that might retroactively
explain older failures.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from fmriflow.core import paths
from fmriflow.triage.capture import TriageFileName
from fmriflow.triage.matcher import load_kb_entries
from fmriflow.triage.service import triage as triage_sync

logger = logging.getLogger(__name__)


def add_triage_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``triage`` and its sub-subcommands on the main CLI."""
    triage_parser = subparsers.add_parser(
        "triage",
        help="Automatic error capture — re-triage past failed runs",
    )
    sub = triage_parser.add_subparsers(dest="triage_command")

    scan_parser = sub.add_parser(
        "scan",
        help="Walk ~/.fmriflow/runs/ and re-triage failed runs",
    )
    scan_parser.add_argument(
        "--runs-root", type=str, default=None,
        help="Registry root (default: $FMRIFLOW_HOME/runs/)",
    )
    scan_parser.add_argument(
        "--force", action="store_true",
        help="Re-run even when triage.json already exists and is newer than the KB",
    )
    scan_parser.add_argument(
        "--kind", type=str, default=None,
        help="Only triage runs of this kind (preproc/convert/autoflatten/run)",
    )
    scan_parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after processing this many runs",
    )


def run_triage_command(args: argparse.Namespace) -> int:
    """Dispatch to the right triage sub-subcommand."""
    sub = getattr(args, "triage_command", None)
    if sub == "scan":
        return _cmd_scan(args)
    print("Unknown triage subcommand. Try: fmriflow triage scan --help")
    return 2


# ── Sub-subcommands ─────────────────────────────────────────────────────

def _cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.runs_root).expanduser() if args.runs_root else paths.runs_dir()
    if not root.is_dir():
        print(f"No runs root at {root} — nothing to do.")
        return 0

    kb_entries = load_kb_entries(force_rescan=True)
    kb_max_mtime = _kb_max_mtime()

    total = 0
    triaged = 0
    skipped = 0
    no_state = 0

    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        state_path = run_dir / "state.json"
        if not state_path.is_file():
            no_state += 1
            continue
        try:
            state = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError):
            no_state += 1
            continue

        if state.get("status") != "failed":
            continue
        if args.kind and state.get("kind") != args.kind:
            continue

        total += 1
        if args.limit is not None and (triaged + skipped) >= args.limit:
            break

        triage_path = run_dir / TriageFileName
        if triage_path.is_file() and not args.force:
            # Skip when triage.json is newer than the most recent KB edit.
            try:
                triage_mtime = triage_path.stat().st_mtime
            except OSError:
                triage_mtime = 0.0
            if triage_mtime >= kb_max_mtime:
                skipped += 1
                continue

        print(f"Triaging {run_dir.name} (kind={state.get('kind')})")
        try:
            cap = triage_sync(
                run_id=state.get("run_id") or run_dir.name,
                kind=state.get("kind") or "run",
                state=state,
                run_dir=run_dir,
            )
        except Exception as e:
            print(f"  ! extractor crashed: {e}")
            continue
        if cap is None:
            print("  ! no capture produced")
            continue
        n_matches = len(cap.candidate_matches)
        if n_matches == 0:
            print("  → no KB matches")
        else:
            top = cap.candidate_matches[0]
            print(f"  → {n_matches} match(es), top: #{top.id} "
                  f"({int(top.confidence * 100)}%) {top.title[:70]}")
        triaged += 1

    print()
    print(f"Total failed runs: {total}")
    print(f"  triaged: {triaged}")
    print(f"  skipped (triage.json fresh, KB unchanged): {skipped}")
    print(f"  no state.json: {no_state}")
    print(f"KB entries with fingerprints: "
          f"{sum(1 for e in kb_entries if e.get('fingerprints'))}")
    return 0


def _kb_max_mtime() -> float:
    """Max mtime across all KB YAMLs, for 'is the KB newer than this
    triage.json' comparisons."""
    kb_dir = Path(__file__).resolve().parents[2] / "devdocs" / "errors"
    if not kb_dir.is_dir():
        return 0.0
    max_m = 0.0
    for p in kb_dir.glob("*.yaml"):
        try:
            max_m = max(max_m, p.stat().st_mtime)
        except OSError:
            continue
    return max_m
