"""Execution graph for pipeline run summaries."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fmriflow.core.run_summary import RunSummary

logger = logging.getLogger(__name__)

STATUS_COLORS = {
    'ok': '#4caf50',
    'warning': '#ff9800',
    'failed': '#f44336',
    'skipped': '#9e9e9e',
}


def save_timeline_chart(summary: RunSummary, path: Path) -> None:
    """Render a directed execution graph of the pipeline run.

    Wrapped in try/except so rendering failures never break the pipeline.
    """
    try:
        _render(summary, path)
    except Exception:
        logger.warning("Could not render execution graph", exc_info=True)


def _render(summary: RunSummary, path: Path) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import networkx as nx

    from fmriflow.core.run_summary import fmt_time

    stages = summary.stages
    if not stages:
        return

    G = nx.DiGraph()

    # Add nodes and sequential edges
    for i, stage in enumerate(stages):
        G.add_node(stage.name, status=stage.status, elapsed=stage.elapsed_s,
                    detail=stage.detail)
        if i > 0:
            G.add_edge(stages[i - 1].name, stage.name)

    # Layout: left-to-right with even spacing
    pos = {}
    n = len(stages)
    for i, stage in enumerate(stages):
        pos[stage.name] = (i * 2.0, 0)

    node_colors = [STATUS_COLORS.get(s.status, '#9e9e9e') for s in stages]

    # Scale figure width to number of stages
    fig_w = max(10, n * 2.2)
    fig, ax = plt.subplots(figsize=(fig_w, 3.5))

    # Draw edges
    nx.draw_networkx_edges(
        G, pos, ax=ax,
        edge_color='#bbbbbb',
        arrows=True,
        arrowsize=18,
        arrowstyle='-|>',
        width=2.0,
        min_source_margin=28,
        min_target_margin=28,
    )

    # Draw nodes
    nx.draw_networkx_nodes(
        G, pos, ax=ax,
        node_color=node_colors,
        node_size=2200,
        edgecolors='white',
        linewidths=2.0,
    )

    # Stage name labels (inside nodes)
    nx.draw_networkx_labels(
        G, pos, ax=ax,
        font_size=9,
        font_weight='bold',
        font_color='white',
    )

    # Timing labels (below nodes)
    label_pos = {name: (x, y - 0.35) for name, (x, y) in pos.items()}
    time_labels = {}
    for stage in stages:
        line = fmt_time(stage.elapsed_s)
        if stage.detail:
            # Truncate long details
            detail = stage.detail if len(stage.detail) <= 30 else stage.detail[:27] + '...'
            line += f"\n{detail}"
        time_labels[stage.name] = line

    nx.draw_networkx_labels(
        G, label_pos, labels=time_labels, ax=ax,
        font_size=7,
        font_color='#333333',
    )

    title = f"{summary.experiment} \u2014 {summary.subject}"
    subtitle = f"Total: {fmt_time(summary.total_elapsed_s)}"
    ax.set_title(f"{title}\n{subtitle}", fontsize=13, fontweight='bold')

    ax.axis('off')

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
