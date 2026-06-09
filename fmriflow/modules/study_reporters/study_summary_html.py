"""HTML summary of a study run.

Renders a single-page report: study header, included groups (with
per-group run_id + status + elapsed), study-stage timings, and a list
of study artifacts (with per-key shape/type hints). Saves alongside
``study_summary.json`` in the study output dir.

One scope up from :class:`GroupSummaryHtmlReporter` — same structure,
different containers.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_reporter
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_reporter("study_summary_html")
class StudySummaryHtmlReporter:
    """Render a self-contained ``study_summary.html`` next to the run dir."""

    name = "study_summary_html"
    PARAM_SCHEMA = {
        "output_dir": {
            "type": "str",
            "description": (
                "Directory for the HTML output. Defaults to the study "
                "run dir (next to study_summary.json)."
            ),
        },
        "filename": {
            "type": "str",
            "default": "study_summary.html",
            "description": "Filename within the output dir.",
        },
    }

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        outdir_str = cfg.get("output_dir") or config.get("output_dir")
        outdir = Path(outdir_str).resolve() if outdir_str else Path.cwd()
        outdir.mkdir(parents=True, exist_ok=True)
        filename = cfg.get("filename", "study_summary.html")
        out_path = outdir / filename

        out_path.write_text(_render(study))
        return {"summary": str(out_path)}

    def validate_config(self, config: dict) -> list[str]:
        return []


# ─── rendering ─────────────────────────────────────────────────


def _render(study: StudyResult) -> str:
    summary = study.study_summary
    header = _header(study, summary)
    groups = _groups_table(study)
    stages = _stages_table(summary)
    artifacts = _artifacts_table(study)
    return _PAGE.format(
        title=html.escape(study.study_name),
        header=header,
        groups=groups,
        stages=stages,
        artifacts=artifacts,
    )


def _header(study: StudyResult, summary) -> str:
    if summary is None:
        return f"<h1>{html.escape(study.study_name)}</h1>"
    return (
        f"<h1>{html.escape(study.study_name)}</h1>"
        f"<p class='meta'>"
        f"Started: {html.escape(summary.started_at)}<br/>"
        f"Finished: {html.escape(summary.finished_at)}<br/>"
        f"Elapsed: {summary.total_elapsed_s:.2f}s<br/>"
        f"Groups: {len(summary.group_labels)}"
        f"</p>"
    )


def _groups_table(study: StudyResult) -> str:
    rows = []
    for g in study.groups:
        label = g.study_label or g.group_name
        gs = g.group_summary
        if gs is None:
            rows.append(
                f"<tr class='status-unknown'>"
                f"<td>{html.escape(label)}</td>"
                f"<td>{html.escape(g.group_name)}</td>"
                f"<td>—</td><td>—</td><td>—</td><td>—</td>"
                f"</tr>"
            )
            continue
        n_subj = len(gs.subject_summaries)
        n_failed = sum(
            1 for s in gs.subject_summaries
            if any(st.status == 'failed' for st in s.stages)
        )
        overall = 'failed' if n_failed > 0 else 'ok'
        rows.append(
            f"<tr class='status-{overall}'>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{html.escape(g.group_name)}</td>"
            f"<td><code>{html.escape(gs.run_id)}</code></td>"
            f"<td>{n_subj} subject(s)"
            f"{f' ({n_failed} failed)' if n_failed else ''}</td>"
            f"<td>{gs.total_elapsed_s:.1f}s</td>"
            f"<td>{html.escape(overall)}</td>"
            f"</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='6'><em>No groups</em></td></tr>"
    return (
        "<h2>Groups</h2>"
        "<table><thead><tr>"
        "<th>Label</th><th>Group name</th><th>Run ID</th>"
        "<th>Subjects</th><th>Elapsed</th><th>Status</th>"
        "</tr></thead><tbody>"
        + body
        + "</tbody></table>"
    )


def _stages_table(summary) -> str:
    if summary is None or not summary.study_stages:
        return "<h2>Study stages</h2><p><em>None recorded.</em></p>"
    rows = []
    for s in summary.study_stages:
        rows.append(
            f"<tr class='status-{s.status}'>"
            f"<td>{html.escape(s.name)}</td>"
            f"<td>{html.escape(s.status)}</td>"
            f"<td>{s.elapsed_s:.2f}s</td>"
            f"<td>{html.escape(str(s.detail))}</td>"
            f"</tr>"
        )
    return (
        "<h2>Study stages</h2>"
        "<table><thead><tr>"
        "<th>Stage</th><th>Status</th><th>Elapsed</th><th>Detail</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _artifacts_table(study: StudyResult) -> str:
    if not study.artifacts:
        return "<h2>Study artifacts</h2><p><em>None.</em></p>"
    rows = []
    for key, value in sorted(study.artifacts.items()):
        rows.append(
            f"<tr>"
            f"<td><code>{html.escape(key)}</code></td>"
            f"<td>{html.escape(_describe(value))}</td>"
            f"</tr>"
        )
    return (
        "<h2>Study artifacts</h2>"
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
    if isinstance(value, float):
        return f"float({value:.6g})"
    if isinstance(value, (int, bool)):
        return f"{value}"
    if isinstance(value, str):
        return value if len(value) < 100 else value[:97] + "..."
    return f"{type(value).__name__}"


_PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<title>Study run — {title}</title>
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
{groups}
{stages}
{artifacts}
</body></html>
"""
