"""Parse fmriprep nipype log lines into structured node-status events."""

from __future__ import annotations

import json

from fmriflow.preproc.nipype_log import (
    NipypeLogParser,
    append_jsonl,
    parse_nipype_events_file,
)


# A short captured-style fmriprep log snippet covering setup / finish / error.
SAMPLE_LOG = """\
250504-12:31:02,123 nipype.workflow INFO:
\t [Node] Setting-up "fmriprep_wf.single_subject_01_wf.bold_preproc_wf.bold_split" in "/work/.../bold_split".
250504-12:31:18,847 nipype.workflow INFO:
\t [Node] Finished "fmriprep_wf.single_subject_01_wf.bold_preproc_wf.bold_split", elapsed time 16.7s.
250504-12:31:20,001 nipype.workflow INFO:
\t [Node] Setting-up "fmriprep_wf.single_subject_01_wf.bold_t1_trans_wf.merge" in "/work/.../merge".
250504-12:35:11,002 nipype.workflow ERROR:
\t [Node] Error on "fmriprep_wf.sdc_estimate_wf.fmap2field_wf.unwarp_wf" (some traceback that follows on later lines)
random unrelated stdout line we should ignore
"""


def _drain(parser: NipypeLogParser, lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for line in lines:
        out.extend(parser.feed(line))
    return out


def test_parser_emits_start_finish_error():
    parser = NipypeLogParser()
    events = _drain(parser, SAMPLE_LOG.splitlines())

    kinds = [e["event"] for e in events]
    assert kinds == ["node_start", "node_done", "node_start", "node_fail"]

    # First event metadata
    e0 = events[0]
    assert e0["leaf"] == "bold_split"
    assert e0["workflow"].startswith("fmriprep_wf.")
    assert "node" in e0 and "fmriprep_wf" in e0["node"]
    assert e0["t"] > 0

    # Failure event has level ERROR
    fail = events[-1]
    assert fail["event"] == "node_fail"
    assert fail["level"] == "ERROR"
    assert fail["leaf"] == "unwarp_wf"


def test_parser_drops_unmatched_lines():
    parser = NipypeLogParser()
    events = _drain(parser, [
        "totally unrelated stdout",
        "Bash: command not found",
        "",
    ])
    assert events == []


def test_parser_recovers_from_lone_header():
    parser = NipypeLogParser()
    # A header followed immediately by a non-node line should not stick.
    events = _drain(parser, [
        "250504-12:31:02,123 nipype.workflow INFO:",
        "  ... payload that doesn't match [Node] pattern ...",
        "250504-12:31:18,847 nipype.workflow INFO:",
        "\t [Node] Finished \"foo.bar.baz\", elapsed time 5s.",
    ])
    assert [e["event"] for e in events] == ["node_done"]
    assert events[0]["leaf"] == "baz"


def test_aggregator_collapses_jsonl(tmp_path):
    p = tmp_path / "nipype_events.jsonl"
    append_jsonl(p, {"event": "node_start", "node": "wf.a.smooth", "leaf": "smooth",
                     "workflow": "wf.a", "t": 100.0, "level": "INFO"})
    append_jsonl(p, {"event": "node_start", "node": "wf.a.mask", "leaf": "mask",
                     "workflow": "wf.a", "t": 105.0, "level": "INFO"})
    append_jsonl(p, {"event": "node_done", "node": "wf.a.smooth", "leaf": "smooth",
                     "workflow": "wf.a", "t": 110.0, "level": "INFO"})
    append_jsonl(p, {"event": "node_fail", "node": "wf.a.mask", "leaf": "mask",
                     "workflow": "wf.a", "t": 115.0, "level": "ERROR"})

    block = parse_nipype_events_file(p)
    by_leaf = {n.leaf: n for n in block.recent_nodes}
    assert by_leaf["smooth"].status == "ok"
    assert by_leaf["smooth"].elapsed == 10.0
    assert by_leaf["mask"].status == "failed"
    assert by_leaf["mask"].elapsed == 10.0
    assert block.counts == {"running": 0, "ok": 1, "failed": 1, "total_seen": 2}


def test_aggregator_unfinished_nodes_default_to_running(tmp_path):
    p = tmp_path / "events.jsonl"
    append_jsonl(p, {"event": "node_start", "node": "wf.a.x", "leaf": "x",
                     "workflow": "wf.a", "t": 10.0, "level": "INFO"})
    block = parse_nipype_events_file(p)
    assert block.counts["running"] == 1
    assert block.recent_nodes[0].status == "running"


def test_aggregator_caps_total_returned(tmp_path):
    p = tmp_path / "events.jsonl"
    for i in range(50):
        append_jsonl(p, {"event": "node_done", "node": f"wf.a.n{i}", "leaf": f"n{i}",
                         "workflow": "wf.a", "t": 100.0 + i, "level": "INFO"})
    block = parse_nipype_events_file(p, cap=10)
    assert len(block.recent_nodes) == 10
    # Most-recent retained.
    assert block.recent_nodes[-1].leaf == "n49"
    assert block.counts["total_seen"] == 50  # counts reflect full set


def test_aggregator_empty_path_returns_zeros(tmp_path):
    block = parse_nipype_events_file(tmp_path / "missing.jsonl")
    assert block.counts == {"running": 0, "ok": 0, "failed": 0, "total_seen": 0}
    assert block.recent_nodes == []


def test_aggregator_skips_malformed_lines(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text("not json\n" + json.dumps({
        "event": "node_done", "node": "wf.x", "leaf": "x", "workflow": "wf",
        "t": 1.0, "level": "INFO",
    }) + "\n")
    block = parse_nipype_events_file(p)
    assert block.counts["ok"] == 1
