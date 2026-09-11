"""Analysis graph templates — bundled (``fmriflow/analysis/templates/*.yaml``) and user-made.

A template is a complete :class:`~fmriflow.analysis.graph.AnalysisGraph`
the builder offers as a starting point. Dataset-specific values (paths,
subject, output directory) are graph ``inputs`` referenced as
``$inputs.<name>`` from globals and node params, so a template runs on any
dataset once those inputs are given.

* **bundled** — shipped with the package, read-only.
* **user** — ``$FMRIFLOW_HOME/addons/analysis_pipelines/*.yaml``; carries no
  ``run_defaults`` and may not shadow a bundled name.
"""

from __future__ import annotations

from pathlib import Path

from fmriflow.analysis.graph import AnalysisGraph
from fmriflow.core import paths
from fmriflow.graph.templates import TemplateTiers, concrete_path_warnings, validate_slug  # noqa: F401

TEMPLATES_DIR = Path(__file__).parent / "templates"


def user_templates_dir() -> Path:
    return paths.addons_dir("analysis_pipelines")


_TIERS = TemplateTiers(bundled_dir=TEMPLATES_DIR, user_dir=lambda: user_templates_dir(),
                       graph_cls=AnalysisGraph)


def template_names() -> list[str]:
    return _TIERS.names()


def template_path(name: str) -> tuple[Path, str]:
    return _TIERS.path(name)


def load_template(name: str) -> AnalysisGraph:
    return _TIERS.load(name)


def list_templates() -> list[dict]:
    rows = _TIERS.list()
    for row in rows:
        if not row.get("error"):
            row["scope"] = _TIERS.load(row["name"]).scope
    return rows


def save_user_template(name: str, graph: AnalysisGraph) -> Path:
    return _TIERS.save_user(name, graph)


def delete_user_template(name: str) -> bool:
    return _TIERS.delete_user(name)
