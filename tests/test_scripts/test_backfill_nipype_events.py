"""Backfill the JSONL of an old finished run with FIFO leaf matching."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path

# Import the script as a module (it lives outside fmriflow/).
_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts" / "backfill_nipype_events.py"
)
spec = importlib.util.spec_from_file_location("backfill", _SCRIPT)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)  # type: ignore[union-attr]


def _write_jsonl(p: Path, events: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _read_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def test_backfill_rewrites_bare_leaf_dones_to_full_paths(tmp_path):
    p = tmp_path / "nipype_events.jsonl"
    _write_jsonl(p, [
        {"event": "node_start", "node": "wf.a.smooth", "leaf": "smooth",
         "workflow": "wf.a", "t": 1.0, "level": "INFO"},
        {"event": "node_start", "node": "wf.b.smooth", "leaf": "smooth",
         "workflow": "wf.b", "t": 2.0, "level": "INFO"},
        {"event": "node_done", "node": "smooth", "leaf": "smooth",
         "workflow": "", "t": 5.0, "level": "INFO"},
        {"event": "node_done", "node": "smooth", "leaf": "smooth",
         "workflow": "", "t": 6.0, "level": "INFO"},
    ])
    rc = backfill.main([str(p)])
    assert rc == 0
    events = _read_jsonl(p)
    dones = [e for e in events if e["event"] == "node_done"]
    assert dones[0]["node"] == "wf.a.smooth"
    assert dones[1]["node"] == "wf.b.smooth"
    # Original preserved as .bak
    assert (p.with_suffix(p.suffix + ".bak")).is_file()


def test_backfill_dry_run_does_not_modify_file(tmp_path):
    p = tmp_path / "nipype_events.jsonl"
    _write_jsonl(p, [
        {"event": "node_start", "node": "wf.a.x", "leaf": "x",
         "workflow": "wf.a", "t": 1.0, "level": "INFO"},
        {"event": "node_done", "node": "x", "leaf": "x",
         "workflow": "", "t": 2.0, "level": "INFO"},
    ])
    before = p.read_text()
    rc = backfill.main(["--dry-run", str(p)])
    assert rc == 0
    assert p.read_text() == before
    assert not (p.with_suffix(p.suffix + ".bak")).exists()


def test_backfill_walks_directory(tmp_path):
    p1 = tmp_path / "run-a" / "nipype_events.jsonl"
    p2 = tmp_path / "run-b" / "nipype_events.jsonl"
    for p in (p1, p2):
        _write_jsonl(p, [
            {"event": "node_start", "node": "wf.x", "leaf": "x",
             "workflow": "wf", "t": 1.0, "level": "INFO"},
            {"event": "node_done", "node": "x", "leaf": "x",
             "workflow": "", "t": 2.0, "level": "INFO"},
        ])
    rc = backfill.main([str(tmp_path)])
    assert rc == 0
    for p in (p1, p2):
        events = _read_jsonl(p)
        assert events[1]["node"] == "wf.x"


def test_backfill_idempotent(tmp_path):
    p = tmp_path / "nipype_events.jsonl"
    _write_jsonl(p, [
        {"event": "node_start", "node": "wf.x", "leaf": "x",
         "workflow": "wf", "t": 1.0, "level": "INFO"},
        {"event": "node_done", "node": "x", "leaf": "x",
         "workflow": "", "t": 2.0, "level": "INFO"},
    ])
    backfill.main([str(p)])
    after_first = p.read_text()
    backfill.main([str(p)])
    assert p.read_text() == after_first


def test_backfill_skips_malformed_lines(tmp_path):
    p = tmp_path / "nipype_events.jsonl"
    p.write_text(
        "not json\n"
        + json.dumps({"event": "node_start", "node": "wf.x", "leaf": "x",
                      "workflow": "wf", "t": 1.0, "level": "INFO"}) + "\n"
        + json.dumps({"event": "node_done", "node": "x", "leaf": "x",
                      "workflow": "", "t": 2.0, "level": "INFO"}) + "\n"
    )
    rc = backfill.main([str(p)])
    assert rc == 0
    lines = p.read_text().splitlines()
    assert lines[0] == "not json"  # malformed left intact
