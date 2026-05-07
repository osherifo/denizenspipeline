#!/usr/bin/env python3
"""Rewrite a nipype_events.jsonl to use full dotted paths everywhere.

Replays the JSONL through the same FIFO leaf-matching the live
aggregator does, then writes back a normalized version where every
``node_done`` / ``node_fail`` event has the full path of its matching
``node_start``. Useful for older finished runs whose JSONL was
produced before the parser fix shipped.

Idempotent: running it twice is a no-op (every event already has a
full dotted path on the second pass).

Usage::

    python scripts/backfill_nipype_events.py [--dry-run] PATH...

PATH can be a JSONL file or a directory containing one (in which case
the script walks the directory looking for ``nipype_events.jsonl``).
A ``.bak`` sidecar is written next to each rewritten file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path


def _backfill_lines(lines: list[str]) -> tuple[list[str], dict[str, int]]:
    """Return (new_lines, stats). Each line is a JSONL event."""
    starts_by_leaf: dict[str, deque[str]] = {}
    out: list[str] = []
    stats = {"rewritten": 0, "passthrough": 0, "orphan_terminals": 0,
             "skipped_malformed": 0}
    for line in lines:
        s = line.strip()
        if not s:
            out.append(line.rstrip("\n"))
            continue
        try:
            ev = json.loads(s)
        except (ValueError, json.JSONDecodeError):
            stats["skipped_malformed"] += 1
            out.append(line.rstrip("\n"))
            continue

        kind = ev.get("event")
        node = ev.get("node")
        leaf = ev.get("leaf") or (node.rsplit(".", 1)[-1] if node else None)
        if not node or not leaf:
            stats["passthrough"] += 1
            out.append(line.rstrip("\n"))
            continue

        if kind == "node_start" and "." in node:
            starts_by_leaf.setdefault(leaf, deque()).append(node)
        elif kind in ("node_done", "node_fail") and "." not in node:
            queue = starts_by_leaf.get(leaf)
            if queue:
                full = queue.popleft()
                ev["node"] = full
                ev["leaf"] = full.rsplit(".", 1)[-1]
                if "." in full:
                    ev["workflow"] = full.rsplit(".", 1)[0]
                if not queue:
                    del starts_by_leaf[leaf]
                stats["rewritten"] += 1
                out.append(json.dumps(ev, ensure_ascii=False))
                continue
            stats["orphan_terminals"] += 1
        stats["passthrough"] += 1
        out.append(json.dumps(ev, ensure_ascii=False))
    return out, stats


def _process_file(p: Path, *, dry_run: bool) -> dict[str, int]:
    raw = p.read_text(encoding="utf-8", errors="replace").splitlines(
        keepends=False,
    )
    new_lines, stats = _backfill_lines(raw)
    if dry_run:
        print(f"  would rewrite {stats['rewritten']} events; "
              f"{stats['orphan_terminals']} orphan terminals; "
              f"{stats['passthrough']} passthrough")
        return stats
    if stats["rewritten"] == 0:
        print(f"  nothing to rewrite — {stats['passthrough']} events untouched")
        return stats
    backup = p.with_suffix(p.suffix + ".bak")
    backup.write_text("\n".join(raw) + ("\n" if raw else ""), encoding="utf-8")
    p.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    print(f"  rewrote {stats['rewritten']} events, "
          f"backup at {backup}")
    return stats


def _resolve_targets(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(p.rglob("nipype_events.jsonl")))
        else:
            print(f"warning: skipping {p} (not a file or directory)",
                  file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", type=Path,
                    help="JSONL file(s) or directory tree(s) to walk.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change without writing.")
    args = ap.parse_args(argv)

    targets = _resolve_targets(args.paths)
    if not targets:
        print("nothing to do — no nipype_events.jsonl files found",
              file=sys.stderr)
        return 1

    overall = {"rewritten": 0, "passthrough": 0, "orphan_terminals": 0,
               "skipped_malformed": 0, "files": 0}
    for t in targets:
        print(t)
        s = _process_file(t, dry_run=args.dry_run)
        overall["files"] += 1
        for k in ("rewritten", "passthrough", "orphan_terminals", "skipped_malformed"):
            overall[k] += s[k]

    print()
    print(f"summary: {overall['files']} file(s) · "
          f"{overall['rewritten']} rewritten · "
          f"{overall['orphan_terminals']} orphan terminals · "
          f"{overall['passthrough']} passthrough · "
          f"{overall['skipped_malformed']} malformed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
