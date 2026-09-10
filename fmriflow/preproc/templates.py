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
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from fmriflow.core import paths
from fmriflow.preproc.graph import Pipeline

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*$")


def validate_slug(name: str) -> str:
    if not name or not _SLUG_RE.match(name):
        raise ValueError(f"invalid template name {name!r}: letters, digits, '_' and '-' only")
    return name

Tier = str  # "bundled" | "user"


def user_templates_dir() -> Path:
    return paths.addons_dir("pipelines")


def bundled_template_names() -> list[str]:
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.yaml"))


def _is_pipeline_file(path: Path) -> bool:
    """True when the YAML is a pipeline (not a pre-redesign stack preset
    that ``fmriflow preproc migrate`` reads from the same folder)."""
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    if "pipeline" in data and isinstance(data["pipeline"], dict) and "nodes" not in data:
        data = data["pipeline"]
    return "nodes" in data


def user_template_names() -> list[str]:
    root = user_templates_dir()
    files = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml"))
    return sorted({p.stem for p in files if _is_pipeline_file(p)})


def template_names() -> list[str]:
    return sorted(set(bundled_template_names()) | set(user_template_names()))


def template_path(name: str) -> tuple[Path, Tier]:
    """Resolve ``name`` to ``(path, tier)``; ``KeyError`` when unknown."""
    bundled = TEMPLATES_DIR / f"{name}.yaml"
    if bundled.exists():
        return bundled, "bundled"
    root = user_templates_dir()
    for cand in (root / f"{name}.yaml", root / f"{name}.yml"):
        if cand.exists() and _is_pipeline_file(cand):
            return cand, "user"
    raise KeyError(f"unknown template {name!r}; available: {', '.join(template_names())}")


def load_template(name: str) -> Pipeline:
    path, _ = template_path(name)
    p = Pipeline.load(path)
    if p.name == "untitled":
        p.name = name
    return p


def list_templates() -> list[dict]:
    out = []
    for name in template_names():
        path, tier = template_path(name)
        try:
            p = load_template(name)
        except Exception as e:  # a hand-edited user file that no longer parses
            logger.warning("template %s unreadable: %s", path, e)
            out.append({"name": name, "tier": tier, "description": "", "n_nodes": 0,
                        "node_types": [], "inputs": {}, "error": str(e)})
            continue
        out.append({
            "name": name,
            "tier": tier,
            "description": p.description,
            "n_nodes": len(p.nodes),
            "node_types": [n.type for n in p.nodes],
            "inputs": p.inputs,
            "error": None,
        })
    return out


# ── user tier ────────────────────────────────────────────────────────


def concrete_path_warnings(pipeline: Pipeline) -> list[str]:
    """Node params / literal inputs holding an absolute path.

    A template should take its paths from pipeline inputs (bound at run
    time); a literal ``/data/...`` typed into a node only works on the
    machine and dataset it was typed for.
    """
    def looks_like_path(v: Any) -> bool:
        return isinstance(v, str) and (v.startswith("/") or v.startswith("~"))

    out: list[str] = []
    for node in pipeline.nodes:
        for where, values in (("param", node.params), ("literal input", node.literal_inputs)):
            for key, v in values.items():
                candidates = v if isinstance(v, list) else [v]
                hits = [x for x in candidates if looks_like_path(x)]
                if hits:
                    out.append(f"{node.id}.{key} ({where}) holds a concrete path: {hits[0]}")
    return out


def save_user_template(name: str, pipeline: Pipeline) -> Path:
    """Write ``pipeline`` as the user template ``name`` (run panel dropped).

    ``ValueError`` for a bad slug or a bundled name.
    """
    validate_slug(name)
    if name in bundled_template_names():
        raise ValueError(f"{name!r} is a bundled template; pick another name")
    pipeline.name = name
    pipeline.run_defaults = {}
    root = user_templates_dir()
    path = root / f"{name}.yaml"
    path.write_text(pipeline.to_yaml())
    return path


def delete_user_template(name: str) -> bool:
    """Remove a user template; ``False`` when absent, ``ValueError`` for bundled."""
    validate_slug(name)
    if name in bundled_template_names():
        raise ValueError(f"{name!r} is a bundled template and cannot be deleted")
    root = user_templates_dir()
    for cand in (root / f"{name}.yaml", root / f"{name}.yml"):
        if cand.exists():
            cand.unlink()
            return True
    return False
