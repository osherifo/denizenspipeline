"""FIFO leaf matching + read-time reconciliation + run-end sweep."""

from __future__ import annotations

from fmriflow.preproc.nipype_log import (
    NipypeLogParser,
    append_jsonl,
    parse_nipype_events_file,
    reconcile_with_run_state,
)


def _drain(parser: NipypeLogParser, lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for line in lines:
        out.extend(parser.feed(line))
    return out


def test_parser_fifo_pairs_concurrent_same_leaf_in_order():
    """Two `Setting-up` events for the same leaf, then two `Finished` —
    each terminal pops the matching full path FIFO-style."""
    parser = NipypeLogParser()
    events = _drain(parser, [
        '250504-12:00:00,000 nipype.workflow INFO:',
        '\t [Node] Setting-up "wf.a.smooth" in "/work/.../a.smooth".',
        '250504-12:00:00,001 nipype.workflow INFO:',
        '\t [Node] Setting-up "wf.b.smooth" in "/work/.../b.smooth".',
        '250504-12:00:05,000 nipype.workflow INFO:',
        '\t [Node] Finished "smooth", elapsed time 5.0s.',
        '250504-12:00:06,000 nipype.workflow INFO:',
        '\t [Node] Finished "smooth", elapsed time 6.0s.',
    ])
    # 4 events: 2 starts, 2 dones — but the dones must reattach the
    # FIRST start (a.smooth) and THEN the second (b.smooth).
    assert [e["event"] for e in events] == [
        "node_start", "node_start", "node_done", "node_done",
    ]
    assert events[0]["node"] == "wf.a.smooth"
    assert events[1]["node"] == "wf.b.smooth"
    assert events[2]["node"] == "wf.a.smooth"   # first done → first start
    assert events[3]["node"] == "wf.b.smooth"


def test_parser_fifo_documented_limitation_when_finish_order_differs():
    """If sibling leaves finish out of order, FIFO mis-pairs them.

    This is the documented v1 limitation — the run-end sweep catches
    the resulting "stuck running" node afterwards.
    """
    parser = NipypeLogParser()
    events = _drain(parser, [
        '250504-12:00:00,000 nipype.workflow INFO:',
        '\t [Node] Setting-up "wf.a.smooth" in "/work/.../a.smooth".',
        '250504-12:00:00,001 nipype.workflow INFO:',
        '\t [Node] Setting-up "wf.b.smooth" in "/work/.../b.smooth".',
        # b finishes first, but FIFO will assign this done to a.
        '250504-12:00:03,000 nipype.workflow INFO:',
        '\t [Node] Finished "smooth", elapsed time 3.0s.',
    ])
    # FIFO assigns the done to the first start (a.smooth).
    done = events[-1]
    assert done["event"] == "node_done"
    assert done["node"] == "wf.a.smooth"


def test_aggregator_reconciles_legacy_jsonl_with_leaf_only_dones(tmp_path):
    """The on-disk JSONL we produced before the FIFO fix had bare-leaf
    terminal events. The aggregator now does a read-time leaf-walk so
    the existing files render correctly without rewrite.
    """
    p = tmp_path / "nipype_events.jsonl"
    # Two starts with full paths, both dones with bare leaves — the
    # exact shape of the bug we hit on the AN run.
    append_jsonl(p, {"event": "node_start", "node": "wf.a.smooth", "leaf": "smooth",
                     "workflow": "wf.a", "t": 100.0, "level": "INFO"})
    append_jsonl(p, {"event": "node_start", "node": "wf.b.smooth", "leaf": "smooth",
                     "workflow": "wf.b", "t": 101.0, "level": "INFO"})
    append_jsonl(p, {"event": "node_done", "node": "smooth", "leaf": "smooth",
                     "workflow": "", "t": 105.0, "level": "INFO"})
    append_jsonl(p, {"event": "node_done", "node": "smooth", "leaf": "smooth",
                     "workflow": "", "t": 106.0, "level": "INFO"})

    block = parse_nipype_events_file(p)
    assert block.counts == {"running": 0, "ok": 2, "failed": 0,
                            "completed_assumed": 0, "total_seen": 2}
    by_node = {n.node: n.status for n in block.recent_nodes}
    assert by_node == {"wf.a.smooth": "ok", "wf.b.smooth": "ok"}


def test_aggregator_handles_one_done_and_one_orphan_start(tmp_path):
    """One bare-leaf done pops the oldest start; the other start stays
    open and surfaces as ``running``."""
    p = tmp_path / "events.jsonl"
    append_jsonl(p, {"event": "node_start", "node": "wf.a.smooth", "leaf": "smooth",
                     "workflow": "wf.a", "t": 100.0, "level": "INFO"})
    append_jsonl(p, {"event": "node_start", "node": "wf.b.smooth", "leaf": "smooth",
                     "workflow": "wf.b", "t": 101.0, "level": "INFO"})
    append_jsonl(p, {"event": "node_done", "node": "smooth", "leaf": "smooth",
                     "workflow": "", "t": 105.0, "level": "INFO"})
    block = parse_nipype_events_file(p)
    assert block.counts["ok"] == 1
    assert block.counts["running"] == 1


def test_aggregator_keeps_unmatched_bare_leaf_as_separate_node(tmp_path):
    """Bare-leaf done with no matching start at all → recorded as its
    own node so we don't silently drop information."""
    p = tmp_path / "events.jsonl"
    append_jsonl(p, {"event": "node_done", "node": "lonely_leaf", "leaf": "lonely_leaf",
                     "workflow": "", "t": 1.0, "level": "INFO"})
    block = parse_nipype_events_file(p)
    assert block.counts == {"running": 0, "ok": 1, "failed": 0,
                            "completed_assumed": 0, "total_seen": 1}
    assert block.recent_nodes[0].node == "lonely_leaf"


def test_run_end_sweep_marks_orphans_completed_assumed_when_done(tmp_path):
    """When state.json says ``done``, any node still ``running`` in the
    aggregated block is flipped to ``completed_assumed``."""
    p = tmp_path / "events.jsonl"
    append_jsonl(p, {"event": "node_start", "node": "wf.x", "leaf": "x",
                     "workflow": "wf", "t": 1.0, "level": "INFO"})
    block = parse_nipype_events_file(p)
    assert block.counts["running"] == 1
    sweep = reconcile_with_run_state(block, run_status="done")
    assert sweep.counts["running"] == 0
    assert sweep.counts["completed_assumed"] == 1
    assert sweep.recent_nodes[0].status == "completed_assumed"


def test_run_end_sweep_no_op_when_run_still_running(tmp_path):
    p = tmp_path / "events.jsonl"
    append_jsonl(p, {"event": "node_start", "node": "wf.x", "leaf": "x",
                     "workflow": "wf", "t": 1.0, "level": "INFO"})
    block = parse_nipype_events_file(p)
    sweep = reconcile_with_run_state(block, run_status="running")
    assert sweep.counts == block.counts
