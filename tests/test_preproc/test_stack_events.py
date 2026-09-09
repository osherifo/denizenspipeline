"""EventWriter — the append-only JSONL sink the detached pipeline runner streams through."""

from __future__ import annotations

import json

from fmriflow.preproc.stack_events import EventWriter


def test_event_writer_appends_timestamped_jsonl(tmp_path):
    path = tmp_path / "events.jsonl"
    with EventWriter(path) as w:
        w({"event": "started", "n_nodes": 2})
        w({"event": "node_start", "node": "wf.a", "t": 1.0, "timestamp": 5.0})
    with EventWriter(path) as w:   # reopen appends, never truncates
        w({"event": "completed"})
    events = [json.loads(l) for l in path.read_text().splitlines()]
    assert [e["event"] for e in events] == ["started", "node_start", "completed"]
    assert all("timestamp" in e for e in events)
    assert events[1]["timestamp"] == 5.0
