"""Built-in pipeline templates (``fmriflow/preproc/templates/*.yaml``).

A template is a complete :class:`~fmriflow.preproc.graph.Pipeline` the
Build tab offers as a starting point. Saving one under a new name in
``$FMRIFLOW_HOME/configs/preproc/`` makes it the user's own pipeline.
"""

from __future__ import annotations

from pathlib import Path

from fmriflow.preproc.graph import Pipeline

TEMPLATES_DIR = Path(__file__).parent / "templates"


def template_names() -> list[str]:
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.yaml"))


def load_template(name: str) -> Pipeline:
    path = TEMPLATES_DIR / f"{name}.yaml"
    if not path.exists():
        raise KeyError(f"unknown template {name!r}; available: {', '.join(template_names())}")
    return Pipeline.load(path)


def list_templates() -> list[dict]:
    out = []
    for name in template_names():
        p = load_template(name)
        out.append({
            "name": p.name,
            "description": p.description,
            "n_nodes": len(p.nodes),
            "node_types": [n.type for n in p.nodes],
            "inputs": p.inputs,
        })
    return out
