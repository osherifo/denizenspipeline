"""HTML summary of a group run.

Renders a single-page report: header with timing, per-subject status table,
group-stage timings, and a list of group artifacts (with per-key shape /
type hints). Saves alongside ``group_summary.json`` in the group output dir.

Heavy artifact rendering (flatmaps, RGB semantic maps) is deferred to
Phase 4 in the proposal — this reporter is the textual/structural summary.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

import numpy as np

from fmriflow.core.group_types import GroupResult
from fmriflow.modules._decorators import group_reporter
from fmriflow.modules.group_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@group_reporter("group_summary_html")
class GroupSummaryHtmlReporter:
    """Render a self-contained ``group_summary.html`` next to the run dir."""

    name = "group_summary_html"
    PARAM_SCHEMA = {
        "output_dir": {
            "type": "str",
            "description": (
                "Directory for the HTML output. Defaults to the group run "
                "directory (next to group_summary.json)."
            ),
        },
        "filename": {
            "type": "str",
            "default": "group_summary.html",
            "description": "Filename within the output dir.",
        },
    }

    def report(self, group: GroupResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        # The orchestrator writes group_summary.json into self.group_dir,
        # but reporters don't have that path directly — fall back to the
        # group config's output_dir, then to cwd.
        outdir_str = cfg.get("output_dir") or config.get("output_dir")
        outdir = Path(outdir_str).resolve() if outdir_str else Path.cwd()
        outdir.mkdir(parents=True, exist_ok=True)
        filename = cfg.get("filename", "group_summary.html")
        out_path = outdir / filename

        html_text = _render(group, config)
        out_path.write_text(html_text)
        return {"summary": str(out_path)}

    def validate_config(self, config: dict) -> list[str]:
        return []


# ─── rendering ─────────────────────────────────────────────────

def _render(group: GroupResult, config: dict) -> str:
    summary = group.group_summary
    header = _header(group, summary)
    subjects = _subjects_table(group)
    stages = _stages_table(summary)
    artifacts = _artifacts_table(group)
    return _PAGE.format(
        title=html.escape(group.group_name),
        header=header,
        subjects=subjects,
        stages=stages,
        artifacts=artifacts,
    )


def _header(group: GroupResult, summary) -> str:
    if summary is None:
        return f"<h1>{html.escape(group.group_name)}</h1>"
    return (
        f"<h1>{html.escape(group.group_name)}</h1>"
        f"<p class='meta'>"
        f"Started: {html.escape(summary.started_at)}<br/>"
        f"Finished: {html.escape(summary.finished_at)}<br/>"
        f"Elapsed: {summary.total_elapsed_s:.2f}s<br/>"
        f"Subjects: {len(summary.subjects)}"
        f"</p>"
    )


def _subjects_table(group: GroupResult) -> str:
    rows = []
    for sr in group.subjects:
        rs = sr.run_summary
        stages_failed = sum(1 for s in rs.stages if s.status == 'failed')
        rows.append(
            f"<tr class='status-{sr.status}'>"
            f"<td>{html.escape(sr.subject)}</td>"
            f"<td>{html.escape(sr.status)}</td>"
            f"<td>{rs.total_elapsed_s:.2f}s</td>"
            f"<td>{len(rs.stages)} stages"
            f"{f' ({stages_failed} failed)' if stages_failed else ''}</td>"
            f"<td><code>{html.escape(str(sr.run_dir))}</code></td>"
            f"</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='5'><em>No subjects</em></td></tr>"
    return (
        "<h2>Subjects</h2>"
        "<table><thead><tr>"
        "<th>Subject</th><th>Status</th><th>Elapsed</th>"
        "<th>Stages</th><th>Run dir</th>"
        "</tr></thead><tbody>"
        + body
        + "</tbody></table>"
    )


def _stages_table(summary) -> str:
    if summary is None or not summary.group_stages:
        return "<h2>Group stages</h2><p><em>None recorded.</em></p>"
    rows = []
    for s in summary.group_stages:
        rows.append(
            f"<tr class='status-{s.status}'>"
            f"<td>{html.escape(s.name)}</td>"
            f"<td>{html.escape(s.status)}</td>"
            f"<td>{s.elapsed_s:.2f}s</td>"
            f"<td>{html.escape(str(s.detail))}</td>"
            f"</tr>"
        )
    return (
        "<h2>Group stages</h2>"
        "<table><thead><tr>"
        "<th>Stage</th><th>Status</th><th>Elapsed</th><th>Detail</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _artifacts_table(group: GroupResult) -> str:
    if not group.artifacts:
        return "<h2>Group artifacts</h2><p><em>None.</em></p>"
    rows = []
    for key, value in sorted(group.artifacts.items()):
        rows.append(
            f"<tr>"
            f"<td><code>{html.escape(key)}</code></td>"
            f"<td>{html.escape(_describe(value))}</td>"
            f"</tr>"
        )
    return (
        "<h2>Group artifacts</h2>"
        "<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _describe(value: Any) -> str:
    if isinstance(value, np.ndarray):
        return f"ndarray shape={value.shape} dtype={value.dtype}"
    if isinstance(value, dict):
        keys = ', '.join(sorted(str(k) for k in value.keys())[:8])
        return f"dict({keys})"
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if isinstance(value, (int, float)):
        return f"{type(value).__name__}({value:.6g})" if isinstance(value, float) else f"{value}"
    if isinstance(value, str):
        return value if len(value) < 100 else value[:97] + "..."
    return f"{type(value).__name__}"


_PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<title>Group run — {title}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         background: #0f1419; color: #d9e0e6; max-width: 1100px;
         margin: 2em auto; padding: 0 1.5em; }}
  h1 {{ margin: 0 0 0.2em; font-weight: 600; }}
  h2 {{ margin-top: 2em; border-bottom: 1px solid #2a313a; padding-bottom: 0.3em; }}
  .meta {{ color: #8a96a4; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.5em; }}
  th, td {{ text-align: left; padding: 0.4em 0.8em; border-bottom: 1px solid #1f262e; }}
  th {{ color: #8a96a4; font-weight: 500; font-size: 0.9em; }}
  code {{ font-size: 0.85em; color: #b5d4ff; }}
  tr.status-ok td {{ }}
  tr.status-failed td {{ color: #ff8a8a; }}
  tr.status-warning td {{ color: #f0c674; }}
  tr.status-unknown td {{ color: #8a96a4; }}
</style>
</head><body>
{header}
{subjects}
{stages}
{artifacts}
</body></html>
"""
