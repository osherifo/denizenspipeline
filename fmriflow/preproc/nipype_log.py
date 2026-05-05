"""Parse fmriprep's nipype-formatted log lines into node-status events.

fmriprep prints structured ``[Node]`` / ``[Workflow]`` lines on stdout
that we already tail in ``preproc_manager._LogTailer``. This module is a
small stateful parser that turns those lines into events the frontend
can render as a per-node status strip.

Recognised line shapes (real fmriprep stdout):

    250504-12:31:02,123 nipype.workflow INFO:
         [Node] Setting-up "fmriprep_wf.single_subject_01_wf...bold_split" in "/work/.../bold_split".
    250504-12:31:18,847 nipype.workflow INFO:
         [Node] Finished "fmriprep_wf...bold_split", elapsed time 16.7s.
    250504-12:35:11,002 nipype.workflow ERROR:
         [Node] Error on "fmriprep_wf.sdc_estimate_wf.fmap2field_wf.unwarp_wf" (...)

Unknown / unmatched lines are silently dropped — the parser must
degrade gracefully across nipype releases.
"""

from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Match the leading nipype timestamp + level. Group: ts, level.
# 250504-12:31:02,123 nipype.workflow INFO:
_HEADER = re.compile(
    r"^\s*(?P<ts>\d{6}-\d{2}:\d{2}:\d{2},\d{3})\s+nipype\.workflow\s+(?P<level>INFO|WARNING|ERROR|CRITICAL):"
)

# Same line OR a continuation may carry the [Node] / [Workflow] payload.
# Captures: action, node_path. Action is one of the verbs we know.
_NODE = re.compile(
    r"\[(?P<kind>Node|Workflow|MultiProc)\]\s+"
    r"(?P<action>Setting-up|Running|Executing node|Finished|Cached|Collecting|Error on|crashed|Skipping)\s+"
    r"\"(?P<node>[^\"]+)\""
)


@dataclass
class _Pending:
    """A header we've matched but whose [Node] payload may be on the next line."""
    ts: str
    level: str
    received_at: float


def _parse_ts(ts: str) -> float:
    """Parse nipype's ``YYMMDD-HH:MM:SS,mmm`` timestamp into a unix float.

    Returns ``time.time()`` on parse failure — the events file's
    monotonic order is more important than absolute accuracy.
    """
    try:
        # Naive local-time parse; fmriprep doesn't include tz. Treat as UTC for stability.
        dt = datetime.strptime(ts, "%y%m%d-%H:%M:%S,%f").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return time.time()


def _split_node_path(node: str) -> tuple[str, str]:
    """Return (workflow_path, leaf) — leaf = last dotted segment."""
    if "." not in node:
        return ("", node)
    head, _, leaf = node.rpartition(".")
    return (head, leaf)


def _action_to_event(action: str, level: str) -> str | None:
    """Map a (verb, log-level) pair to one of our event kinds."""
    a = action.lower()
    if a in ("setting-up", "running", "executing node"):
        return "node_start"
    if a in ("finished", "cached", "collecting"):
        return "node_done"
    if a in ("error on", "crashed") or level in ("ERROR", "CRITICAL"):
        return "node_fail"
    return None


class NipypeLogParser:
    """Stateful line-by-line parser; emits node-status events."""

    def __init__(self) -> None:
        self._pending: _Pending | None = None
        # fmriprep's nipype emits the full dotted path on "Setting-up"
        # but only the leaf on "Finished" / "Error on". Per-leaf FIFO
        # queue: appendleft on node_start (so the oldest in-flight is at
        # the right end), pop on node_done/_fail. Survives sibling
        # concurrency when finish order matches start order, and avoids
        # the dict[leaf,str] last-write-wins bug where two starts of the
        # same leaf would mis-pair the dones.
        self._full_by_leaf: dict[str, deque[str]] = {}

    def feed(self, line: str) -> Iterable[dict]:
        """Process one log line; yield 0 or 1 event dicts.

        Each event::

            {
              "event": "node_start" | "node_done" | "node_fail",
              "node": "<full.dotted.path>",
              "workflow": "<root.sub...>",   # parent workflow (dotted path minus leaf)
              "leaf": "<leaf-name>",
              "t": <unix float>,
              "level": "INFO" | "ERROR" | ...,
            }
        """
        if line is None:
            return
        line = line.rstrip("\r\n")

        # Case 1: a single line containing both header and payload.
        h = _HEADER.search(line)
        if h:
            payload = line[h.end():]
            n = _NODE.search(payload)
            if n:
                ts_unix = _parse_ts(h.group("ts"))
                ev = self._make_event(
                    n, level=h.group("level"), t=ts_unix,
                )
                self._pending = None
                if ev is not None:
                    yield ev
                return
            # Header without payload — payload may be on the next line.
            self._pending = _Pending(
                ts=h.group("ts"),
                level=h.group("level"),
                received_at=time.time(),
            )
            return

        # Case 2: line is a continuation of a previously-matched header.
        if self._pending is not None:
            n = _NODE.search(line)
            if n is not None:
                ts_unix = _parse_ts(self._pending.ts)
                ev = self._make_event(
                    n, level=self._pending.level, t=ts_unix,
                )
                self._pending = None
                if ev is not None:
                    yield ev
                return
            # Drop the pending state if the next line clearly isn't ours
            # (e.g. blank, or starts another header). We only allow ~5 s of
            # carry-over to avoid forever-pending state on log gaps.
            if time.time() - self._pending.received_at > 5.0:
                self._pending = None

    def _make_event(self, match: re.Match, *, level: str, t: float) -> dict | None:
        action = match.group("action")
        node = match.group("node")
        kind = _action_to_event(action, level)
        if kind is None:
            return None
        wf, leaf = _split_node_path(node)
        # On node_start, append the full dotted path to the per-leaf
        # FIFO queue. On terminal events whose payload is leaf-only, pop
        # the oldest queued full path back. (No-op if the queue is
        # empty or the start carried only a leaf.)
        if kind == "node_start" and "." in node:
            self._full_by_leaf.setdefault(leaf, deque()).append(node)
        elif kind in ("node_done", "node_fail") and "." not in node:
            queue = self._full_by_leaf.get(leaf)
            if queue:
                full = queue.popleft()
                node = full
                wf, leaf = _split_node_path(node)
                if not queue:
                    del self._full_by_leaf[leaf]
        return {
            "event": kind,
            "node": node,
            "workflow": wf,
            "leaf": leaf,
            "t": t,
            "level": level,
        }


# ── JSONL append + aggregation ───────────────────────────────────────────


def append_jsonl(path: Path, event: dict) -> None:
    """Append one JSON event as a line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False))
        f.write("\n")


@dataclass
class NipypeNodeStatus:
    node: str
    leaf: str
    workflow: str
    status: str  # "running" | "ok" | "failed"
    started_at: float = 0.0
    finished_at: float = 0.0
    elapsed: float = 0.0
    crash_file: str | None = None
    level: str = "INFO"

    def to_dict(self) -> dict:
        return {
            "node": self.node,
            "leaf": self.leaf,
            "workflow": self.workflow,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed": self.elapsed,
            "crash_file": self.crash_file,
            "level": self.level,
        }


@dataclass
class NipypeStatusBlock:
    counts: dict = field(default_factory=lambda: {
        "running": 0, "ok": 0, "failed": 0,
        "completed_assumed": 0, "total_seen": 0,
    })
    recent_nodes: list[NipypeNodeStatus] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "counts": dict(self.counts),
            "recent_nodes": [n.to_dict() for n in self.recent_nodes],
        }


def _recompute_counts(nodes: list[NipypeNodeStatus]) -> dict:
    return {
        "running":           sum(1 for n in nodes if n.status == "running"),
        "ok":                sum(1 for n in nodes if n.status == "ok"),
        "failed":            sum(1 for n in nodes if n.status == "failed"),
        "completed_assumed": sum(1 for n in nodes if n.status == "completed_assumed"),
        "total_seen":        len(nodes),
    }


def parse_nipype_events_file(path: str | Path, *, cap: int = 200) -> NipypeStatusBlock:
    """Collapse the JSONL events file into a NipypeStatusBlock.

    Cap limits the number of nodes returned (most recent N).

    Performs a read-time **FIFO leaf-matching pass** so JSONLs written
    before the parser's same-leaf fix (where Finished/Error lines
    carried bare-leaf names) still aggregate cleanly without rewrite:
    a leaf-only terminal event pops the oldest queued ``node_start`` of
    that leaf and applies the terminal status to that full path. Truly
    unmatched bare-leaf events are kept as their own nodes.
    """
    p = Path(path)
    if not p.is_file():
        return NipypeStatusBlock()

    by_node: dict[str, NipypeNodeStatus] = {}
    order: list[str] = []  # insertion order on first sighting
    # Per-leaf FIFO of full dotted paths still awaiting a terminal event.
    starts_by_leaf: dict[str, deque[str]] = {}

    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        kind = ev.get("event")
        node = ev.get("node")
        leaf = ev.get("leaf") or (node.rsplit(".", 1)[-1] if node else None)
        if not node or not leaf:
            continue

        # Reconciliation: rewrite leaf-only terminal events to their
        # matching node_start's full path (FIFO).
        if (
            kind in ("node_done", "node_fail")
            and "." not in node
        ):
            queue = starts_by_leaf.get(leaf)
            if queue:
                full = queue.popleft()
                node = full
                leaf = node.rsplit(".", 1)[-1]
                if not queue:
                    del starts_by_leaf[leaf]

        if kind == "node_start" and "." in node:
            starts_by_leaf.setdefault(leaf, deque()).append(node)

        if node not in by_node:
            by_node[node] = NipypeNodeStatus(
                node=node,
                leaf=leaf,
                workflow=(ev.get("workflow") or
                          (node.rsplit(".", 1)[0] if "." in node else "")),
                status="running",
                started_at=float(ev.get("t") or 0.0),
                level=ev.get("level") or "INFO",
            )
            order.append(node)
        n = by_node[node]
        if kind == "node_start" and n.started_at == 0.0:
            n.started_at = float(ev.get("t") or 0.0)
        elif kind == "node_done":
            n.status = "ok"
            n.finished_at = float(ev.get("t") or 0.0)
            if n.started_at and n.finished_at:
                n.elapsed = max(0.0, n.finished_at - n.started_at)
        elif kind == "node_fail":
            n.status = "failed"
            n.finished_at = float(ev.get("t") or 0.0)
            if n.started_at and n.finished_at:
                n.elapsed = max(0.0, n.finished_at - n.started_at)
            n.level = ev.get("level") or n.level

    nodes = [by_node[k] for k in order]
    counts = _recompute_counts(nodes)
    if cap and len(nodes) > cap:
        nodes = nodes[-cap:]
    return NipypeStatusBlock(counts=counts, recent_nodes=nodes)


def reconcile_with_run_state(
    block: NipypeStatusBlock,
    *,
    run_status: str,
) -> NipypeStatusBlock:
    """Run-end sweep: if the parent preproc run finished cleanly, mark
    any still-``running`` nodes as ``completed_assumed``.

    fmriprep's nipype occasionally emits log lines whose terminal verbs
    we don't recognise, or batches them in a way that drops the line
    entirely. When the parent run says ``done``, those orphans are
    almost certainly fine — surface them as ``completed_assumed`` so
    the user sees that we didn't observe a Finished line directly.
    Failed/cancelled/lost runs leave the orphans as ``running`` so the
    failure context is preserved.
    """
    if run_status != "done":
        return block
    if not block.recent_nodes:
        return block
    flipped = False
    for n in block.recent_nodes:
        if n.status == "running":
            n.status = "completed_assumed"
            flipped = True
    if flipped:
        block.counts = _recompute_counts(block.recent_nodes)
    return block
