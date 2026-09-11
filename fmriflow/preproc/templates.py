"""Pipeline templates — bundled (``fmriflow/preproc/templates/*.yaml``) and user-made.

A template is a complete :class:`~fmriflow.preproc.graph.Pipeline` the
Build tab offers as a starting point. Loading one produces an unsaved
draft; saving that under a name in ``$FMRIFLOW_HOME/configs/preproc/``
makes it the user's own pipeline.

Two tiers, like heuristics:

* **bundled** — shipped with the package, read-only.
* **user** — ``$FMRIFLOW_HOME/addons/pipelines/*.yaml``, written by
  *Save as template* in the Build tab (or by hand). A template carries no
  ``run_defaults``: the Run panel values are dataset-specific, and a
  template is meant to outlive any one dataset.

A user template may not shadow a bundled name — saving under one is
refused so the two lists never disagree about what a name means.

The tier mechanics live in :class:`fmriflow.graph.templates.TemplateTiers`;
this module binds them to the preprocessing directories.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fmriflow.core import paths
from fmriflow.graph.templates import (  # noqa: F401  (re-exported)
    _SLUG_RE,
    TemplateTiers,
    concrete_path_warnings,
    validate_slug,
)
from fmriflow.preproc.graph import Pipeline

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

Tier = str  # "bundled" | "user"


def user_templates_dir() -> Path:
    return paths.addons_dir("pipelines")


# The lambda looks the function up at call time, so patching
# ``user_templates_dir`` still redirects the user tier.
_TIERS = TemplateTiers(
    bundled_dir=TEMPLATES_DIR,
    user_dir=lambda: user_templates_dir(),
    graph_cls=Pipeline,
)


def bundled_template_names() -> list[str]:
    return _TIERS.bundled_names()


def _is_pipeline_file(path: Path) -> bool:
    """True when the YAML is a pipeline (not a pre-redesign stack preset
    that ``fmriflow preproc migrate`` reads from the same folder)."""
    return _TIERS.is_graph_file(path)


def user_template_names() -> list[str]:
    return _TIERS.user_names()


def template_names() -> list[str]:
    return _TIERS.names()


def template_path(name: str) -> tuple[Path, Tier]:
    """Resolve ``name`` to ``(path, tier)``; ``KeyError`` when unknown."""
    return _TIERS.path(name)


def load_template(name: str) -> Pipeline:
    return _TIERS.load(name)


def list_templates() -> list[dict]:
    return _TIERS.list()


def save_user_template(name: str, pipeline: Pipeline) -> Path:
    """Write ``pipeline`` as the user template ``name`` (run panel dropped).

    ``ValueError`` for a bad slug or a bundled name.
    """
    return _TIERS.save_user(name, pipeline)


def delete_user_template(name: str) -> bool:
    """Remove a user template; ``False`` when absent, ``ValueError`` for bundled."""
    return _TIERS.delete_user(name)
