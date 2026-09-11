"""Node records for run summaries: time one module call and emit its node events."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fmriflow import ui as fui
from fmriflow.core.run_summary import NodeIdGen, NodeRecord

logger = logging.getLogger(__name__)


@contextmanager
def _record(
    nodes: list[NodeRecord], idgen: NodeIdGen, kind: str, name: str,
    *, isolate: bool = False,
) -> Iterator[NodeRecord]:
    """Time one plugin invocation and append a NodeRecord on exit.

    ``isolate=True`` swallows the exception so the surrounding stage
    can keep running (used by the analyze + report stages, which the
    existing orchestrator already runs in isolation per plugin).

    Emits ``node_start`` / ``node_done`` / ``node_fail`` events to
    ``$FMRIFLOW_EVENTS_FILE`` so the live in-flight graph viewer can
    light up the specific plugin that's running right now (not just
    the surrounding stage). The events ride the same event_context
    thread-locals as the existing ``stage_*`` events, so they carry
    ``subject`` / ``group`` / ``study`` tags automatically.
    """
    node_id = idgen.make(name)
    rec = NodeRecord(
        id=node_id, kind=kind, name=name,
        status='ok', elapsed_s=0.0,
    )
    t0 = time.time()
    fui.emit_event({
        'event': 'node_start',
        'node_id': node_id, 'kind': kind, 'name': name,
    })
    try:
        yield rec
        elapsed = round(time.time() - t0, 3)
        rec.elapsed_s = elapsed
        nodes.append(rec)
        fui.emit_event({
            'event': 'node_done',
            'node_id': node_id, 'kind': kind, 'name': name,
            'elapsed': elapsed,
            'detail': rec.detail,
        })
    except Exception as exc:
        elapsed = round(time.time() - t0, 3)
        rec.elapsed_s = elapsed
        if rec.status == 'ok':
            rec.status = 'failed'
        if not rec.detail:
            rec.detail = str(exc)
        nodes.append(rec)
        fui.emit_event({
            'event': 'node_fail',
            'node_id': node_id, 'kind': kind, 'name': name,
            'elapsed': elapsed,
            'error': str(exc),
        })
        if not isolate:
            raise


def _relativize(paths: list[str] | None, output_dir: str | None) -> list[str]:
    """Make paths relative to ``output_dir`` where possible.

    Reporters return a ``{logical_name: path}`` dict; ``paths`` here is
    the dict's values. Falls back to the absolute string when the file
    lives outside ``output_dir`` (rare, but happens for shared caches).
    """
    out: list[str] = []
    base = Path(output_dir).resolve() if output_dir else None
    for p in paths or []:
        if not p:
            continue
        try:
            full = Path(str(p)).resolve()
        except Exception:
            out.append(str(p))
            continue
        if base is not None:
            try:
                out.append(str(full.relative_to(base)))
                continue
            except ValueError:
                pass
        out.append(str(full))
    return out
