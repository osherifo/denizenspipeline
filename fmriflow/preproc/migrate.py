"""``fmriflow preproc migrate`` — convert pre-redesign preprocessing files.

Three shapes are converted into pipelines under ``$FMRIFLOW_HOME/configs/preproc/``:

1. **Stack presets** (``addons/pipelines/*.yaml``: one bootstrap + N
   transforms) become a linear pipeline.
2. **Post-preproc graphs** (``stores/post_preproc_workflows/*.yaml``:
   ReactFlow nodes/edges over ``run()`` nodes with ``preproc_run`` sources,
   ``_inputs`` literals, ``_iter`` iteration and ``subworkflow`` refs)
   become a pipeline with a ``manifest_source``.
3. **Stage configs** (``configs/preproc/*.yaml`` with ``backend`` /
   ``backend_params``) become a single-node pipeline; the original file is
   rewritten to reference it (``preproc: {pipeline: <name>, ...}``).

Originals are kept next to the converted file with a ``.migrated`` suffix.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from fmriflow.preproc.graph import Pipeline, PipelineEdge, PipelineNode

logger = logging.getLogger(__name__)

# bootstrap kind -> (node type, node kind)
BOOTSTRAP_TO_NODE: dict[str, tuple[str, str]] = {
    "fmriprep": ("fmriprep", "container_app"),
    "bids_app": ("bids_app", "container_app"),
    "custom": ("custom_shell", "container_app"),
    "passthrough": ("derivatives_source", "source"),
}
BACKEND_TO_NODE = BOOTSTRAP_TO_NODE
LEGACY_KEYS = ("backend", "backend_params")


@dataclass
class MigrationReport:
    converted: list[tuple[str, str]] = field(default_factory=list)   # (source, target)
    skipped: list[tuple[str, str]] = field(default_factory=list)     # (source, reason)

    def summary(self) -> str:
        lines = [f"converted {len(self.converted)} file(s), skipped {len(self.skipped)}"]
        lines += [f"  {s} -> {t}" for s, t in self.converted]
        lines += [f"  skipped {s}: {r}" for s, r in self.skipped]
        return "\n".join(lines)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name).strip("_") or "pipeline"


def _bindings_for(node_type: str) -> dict[str, str]:
    if node_type in ("fmriprep", "bids_app"):
        return {"bids_dir": "$inputs.bids_dir", "subject": "$inputs.subject", "output_dir": "$inputs.output_dir"}
    if node_type == "custom_shell":
        return {"input_dir": "$inputs.bids_dir", "subject": "$inputs.subject", "output_dir": "$inputs.output_dir"}
    if node_type == "derivatives_source":
        return {"derivatives_dir": "$inputs.derivatives_dir", "subject": "$inputs.subject"}
    return {"subject": "$inputs.subject"}


def _inputs_for(node_type: str) -> dict[str, dict[str, Any]]:
    common = {"subject": {"kind": "str", "description": "participant label"}}
    if node_type == "derivatives_source":
        return {**common, "derivatives_dir": {"kind": "dir", "description": "existing preprocessed derivatives"}}
    return {**common, "bids_dir": {"kind": "dir", "description": "BIDS root"}, "output_dir": {"kind": "dir", "description": "derivatives root"}}


def _first_file_output(node_type: str) -> str:
    return {
        "fmriprep": "bold_preproc", "bids_app": "files", "custom_shell": "files",
        "derivatives_source": "bold", "manifest_source": "bold",
    }.get(node_type, "out_file")


# ── 1. stack presets ──────────────────────────────────────────────

def stack_to_pipeline(data: dict[str, Any], name: str) -> Pipeline:
    """A stack preset dict (``{name, description, stack: {bootstrap, transforms}}``) -> Pipeline."""
    stack = data.get("stack") or data
    boot = stack.get("bootstrap") or {}
    kind = str(boot.get("kind") or "fmriprep")
    params = dict(boot.get("params") or {})
    if kind == "nipype":
        node_type, node_kind = str(boot.get("workflow") or "identity"), "composite"
        bindings = {"subject": "$inputs.subject"}
    else:
        node_type, node_kind = BOOTSTRAP_TO_NODE.get(kind, ("custom_shell", "container_app"))
        bindings = _bindings_for(node_type)
    nodes = [PipelineNode(id="bootstrap", type=node_type, kind=node_kind, params=params, bindings=bindings,
                          position={"x": 0, "y": 0})]
    edges: list[PipelineEdge] = []
    prev_id, prev_port = "bootstrap", _first_file_output(node_type)
    for i, t in enumerate(stack.get("transforms") or []):
        tid = f"{t['name']}_{i + 1}" if any(n.id == t["name"] for n in nodes) else str(t["name"])
        nodes.append(PipelineNode(id=tid, type=str(t["name"]), kind="interface", params=dict(t.get("params") or {}),
                                  iter={"handle": "in_file"}, position={"x": 300 * (i + 1), "y": 0}))
        edges.append(PipelineEdge(id=f"e{i + 1}", source=prev_id, target=tid, source_handle=prev_port, target_handle="in_file"))
        prev_id, prev_port = tid, "out_file"
    manifest: dict[str, Any] = {"backend_node": "bootstrap"}
    if prev_id != "bootstrap":
        manifest["bold_from"] = f"{prev_id}.{prev_port}"
    return Pipeline(name=_slug(name), description=str(data.get("description") or f"migrated stack preset {name}"),
                    inputs=_inputs_for(node_type), nodes=nodes, edges=edges, manifest=manifest)


# ── 2. post-preproc graphs ────────────────────────────────────────

def post_preproc_to_pipeline(data: dict[str, Any], name: str) -> Pipeline:
    """A saved post-preproc workflow (``{inputs, outputs, graph: {nodes, edges}}``) -> Pipeline."""
    graph = data.get("graph") or data
    nodes: list[PipelineNode] = []
    edges: list[PipelineEdge] = []
    for n in graph.get("nodes") or []:
        d = n.get("data") or {}
        params = dict(d.get("params") or {})
        ntype = str(n["type"])
        literal = {k: v for k, v in (params.pop("_inputs", {}) or {}).items()}
        it = params.pop("_iter", None)
        if ntype == "preproc_run":
            run_name = params.pop("run_name", "")
            nodes.append(PipelineNode(id=str(n["id"]), type="manifest_source", kind="source",
                                      params={"run_name": run_name}, bindings={"manifest": "$inputs.manifest"},
                                      position=dict(n.get("position") or {})))
            continue
        if ntype == "subworkflow":
            wf_name = str(params.pop("workflow_name", "") or "subworkflow")
            nodes.append(PipelineNode(id=str(n["id"]), type=_slug(wf_name), kind="composite", params=params,
                                      literal_inputs=literal, position=dict(n.get("position") or {})))
            continue
        nodes.append(PipelineNode(
            id=str(n["id"]), type=ntype, kind="interface", params=params, literal_inputs=literal,
            iter={"handle": str(it["handle"])} if isinstance(it, dict) and it.get("handle") else None,
            position=dict(n.get("position") or {}),
        ))
    for e in graph.get("edges") or []:
        src_handle = str(e.get("sourceHandle") or "out_file")
        src = next((x for x in nodes if x.id == e["source"]), None)
        if src is not None and src.type == "manifest_source" and src_handle == "out_file":
            src_handle = "bold"
        edges.append(PipelineEdge(id=str(e["id"]), source=str(e["source"]), target=str(e["target"]),
                                  source_handle=src_handle, target_handle=str(e.get("targetHandle") or "in_file")))
    sources = [n for n in nodes if n.type == "manifest_source"]
    manifest: dict[str, Any] = {}
    if sources:
        manifest["backend_node"] = sources[0].id
    outs = data.get("outputs") or {}
    for _, spec in outs.items():
        ref = str((spec or {}).get("from") or "")
        if ref:
            manifest["bold_from"] = ref
            break
    return Pipeline(name=_slug(name), description=str(data.get("description") or f"migrated post-preproc workflow {name}"),
                    inputs={"manifest": {"kind": "file", "description": "preproc_manifest.json to post-process"},
                            "subject": {"kind": "str"}},
                    nodes=nodes, edges=edges, manifest=manifest)


# ── 3. legacy stage configs ───────────────────────────────────────

def legacy_config_to_pipeline(section: dict[str, Any], name: str) -> tuple[Pipeline, dict[str, Any]]:
    """A ``preproc: {backend, backend_params, ...}`` section -> (Pipeline, new preproc section)."""
    backend = str(section.get("backend") or "fmriprep")
    if backend == "nipype":
        node_type, node_kind = str((section.get("backend_params") or {}).get("workflow") or "identity"), "composite"
        params = {k: v for k, v in (section.get("backend_params") or {}).items() if k != "workflow"}
        bindings = {"subject": "$inputs.subject"}
    else:
        node_type, node_kind = BACKEND_TO_NODE.get(backend, ("custom_shell", "container_app"))
        params = dict(section.get("backend_params") or {})
        bindings = _bindings_for(node_type)
    pipeline = Pipeline(
        name=_slug(name), description=f"migrated from {name} ({backend})",
        inputs=_inputs_for(node_type),
        nodes=[PipelineNode(id=backend if backend != "custom" else "custom_shell", type=node_type, kind=node_kind,
                            params=params, bindings=bindings, position={"x": 0, "y": 0})],
        edges=[], manifest={"backend_node": backend if backend != "custom" else "custom_shell"},
    )
    new_section: dict[str, Any] = {"pipeline": pipeline.name}
    for key in ("subject", "output_dir", "bids_dir", "derivatives_dir", "work_dir", "task", "sessions", "dataset"):
        if section.get(key) not in (None, ""):
            new_section[key] = section[key]
    if backend == "passthrough" and section.get("output_dir") and "derivatives_dir" not in new_section:
        new_section["derivatives_dir"] = section["output_dir"]
    return pipeline, new_section


# ── driver ────────────────────────────────────────────────────────

def migrate_all(
    *,
    presets_dir: Path | None = None,
    post_preproc_dir: Path | None = None,
    configs_dir: Path | None = None,
    workflow_dirs: list[Path] | None = None,
    dry_run: bool = False,
) -> MigrationReport:
    from fmriflow.core import paths

    presets_dir = presets_dir if presets_dir is not None else paths.addons_dir("pipelines")
    post_preproc_dir = post_preproc_dir if post_preproc_dir is not None else paths.store_dir("post_preproc_workflows")
    configs_dir = configs_dir if configs_dir is not None else paths.config_dir("preproc")
    configs_dir.mkdir(parents=True, exist_ok=True)
    report = MigrationReport()

    def _write(pipeline: Pipeline, source: Path) -> Path:
        target = configs_dir / f"{pipeline.name}.yaml"
        if target.exists() and target.resolve() != source.resolve():
            i = 2
            while (configs_dir / f"{pipeline.name}_{i}.yaml").exists():
                i += 1
            pipeline.name = f"{pipeline.name}_{i}"
            target = configs_dir / f"{pipeline.name}.yaml"
        if not dry_run:
            target.write_text(pipeline.to_yaml())
        return target

    def _retire(source: Path) -> None:
        if not dry_run:
            source.rename(source.with_name(source.name + ".migrated"))

    for f in sorted(presets_dir.glob("*.yaml")) if presets_dir.is_dir() else []:
        try:
            data = yaml.safe_load(f.read_text()) or {}
            p = stack_to_pipeline(data, str(data.get("name") or f.stem))
            t = _write(p, f)
            _retire(f)
            report.converted.append((str(f), str(t)))
        except Exception as e:
            report.skipped.append((str(f), f"{type(e).__name__}: {e}"))

    for f in sorted(post_preproc_dir.glob("*.yaml")) if post_preproc_dir.is_dir() else []:
        try:
            data = yaml.safe_load(f.read_text()) or {}
            p = post_preproc_to_pipeline(data, str(data.get("name") or f.stem))
            t = _write(p, f)
            _retire(f)
            report.converted.append((str(f), str(t)))
        except Exception as e:
            report.skipped.append((str(f), f"{type(e).__name__}: {e}"))

    for f in sorted(configs_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text()) or {}
        except Exception as e:
            report.skipped.append((str(f), f"YAML error: {e}"))
            continue
        section = data.get("preproc") if isinstance(data.get("preproc"), dict) else data
        if not isinstance(section, dict) or "nodes" in section or not any(k in section for k in LEGACY_KEYS):
            continue
        try:
            pipeline, new_section = legacy_config_to_pipeline(section, f.stem)
            pipeline.name = _slug(f.stem) + "_pipeline"
            t = _write(pipeline, f)
            new_section["pipeline"] = pipeline.name
            if not dry_run:
                f.with_name(f.name + ".migrated").write_text(f.read_text())
                f.write_text(yaml.safe_dump({"preproc": new_section}, sort_keys=False))
            report.converted.append((str(f), str(t)))
        except Exception as e:
            report.skipped.append((str(f), f"{type(e).__name__}: {e}"))

    for wdir in workflow_dirs or []:
        for f in sorted(wdir.glob("*.yaml")) if wdir.is_dir() else []:
            try:
                data = yaml.safe_load(f.read_text()) or {}
            except Exception:
                continue
            section = data.get("preproc") if isinstance(data.get("preproc"), dict) else None
            if not section or "nodes" in section or not any(k in section for k in LEGACY_KEYS):
                continue
            try:
                pipeline, new_section = legacy_config_to_pipeline(section, f.stem)
                pipeline.name = _slug(f.stem) + "_pipeline"
                t = _write(pipeline, f)
                new_section["pipeline"] = pipeline.name
                data["preproc"] = new_section
                if not dry_run:
                    f.with_name(f.name + ".migrated").write_text(f.read_text())
                    f.write_text(yaml.safe_dump(data, sort_keys=False))
                report.converted.append((str(f), str(t)))
            except Exception as e:
                report.skipped.append((str(f), f"{type(e).__name__}: {e}"))

    return report
