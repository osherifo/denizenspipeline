"""The node library: list, detail, preflight, author a node, import a pipeline .py, rescan."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["preproc-nodes"])

_SLUG_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


class NewNodeBody(BaseModel):
    name: str
    code: str


class ImportBody(BaseModel):
    path: str
    name: str | None = None


def _registry(request: Request):
    return request.app.state.node_registry


@router.get("/preproc/nodes")
async def list_nodes(request: Request, kind: str | None = None):
    reg = _registry(request)
    return {
        "nodes": [i.to_dict() for i in reg.list(kind=kind)],
        "shadowed": [{"name": n, "shadowed_source": s} for n, s in reg.shadowed()],
    }


@router.get("/preproc/nodes/scaffold/{kind}")
async def node_scaffold(kind: str):
    """Starter code for a new node of ``kind`` (interface | composite | container_app)."""
    if kind not in SCAFFOLDS:
        raise HTTPException(404, detail=f"no scaffold for kind {kind!r}")
    return {"kind": kind, "code": SCAFFOLDS[kind]}


@router.get("/preproc/nodes/{name}")
async def get_node(request: Request, name: str):
    reg = _registry(request)
    if not reg.has(name):
        raise HTTPException(404, detail=f"unknown node {name!r}")
    info = reg.info(name).to_dict()
    cls = reg.cls(name)
    src = None
    try:
        import inspect
        src = inspect.getsource(cls)
    except Exception:
        pass
    info["source_code"] = src
    info["module"] = getattr(cls, "__module__", None)
    return info


@router.get("/preproc/nodes/{name}/preflight")
async def node_preflight(request: Request, name: str):
    reg = _registry(request)
    if not reg.has(name):
        raise HTTPException(404, detail=f"unknown node {name!r}")
    result = reg.preflight(name)
    return {"ok": result.ok, "errors": list(result.errors), "warnings": list(result.warnings)}


@router.post("/preproc/nodes")
async def save_node(request: Request, body: NewNodeBody):
    """Write ``code`` to ``$FMRIFLOW_HOME/addons/nodes/<name>.py`` and rescan."""
    from fmriflow.core import paths

    if not _SLUG_RE.match(body.name):
        raise HTTPException(400, detail="name must start with a letter and use letters / digits / underscores")
    if not body.code.strip():
        raise HTTPException(400, detail="code is empty")
    try:
        compile(body.code, f"<nodes/{body.name}.py>", "exec")
    except SyntaxError as e:
        raise HTTPException(400, detail=f"Python syntax error: {e}")
    target = paths.addons_dir("nodes") / f"{body.name}.py"
    target.write_text(body.code)
    _registry(request).discover()
    return {"saved": True, "path": str(target)}


@router.post("/preproc/nodes/import")
async def import_node(request: Request, body: ImportBody):
    """Import an existing nipype pipeline ``.py`` as a composite node."""
    from fmriflow.preproc.importer import import_pipeline_file

    path = Path(body.path).expanduser()
    if not path.is_file():
        raise HTTPException(404, detail=f"no such file: {path}")
    try:
        node_file, spec = import_pipeline_file(path, node_name=body.name)
    except (ValueError, ImportError) as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(400, detail=f"import failed: {type(e).__name__}: {e}")
    _registry(request).discover()
    return {
        "imported": True, "node": spec.node_name, "shape": spec.shape, "path": str(node_file),
        "inputs": spec.inputs, "outputs": spec.outputs, "warnings": spec.warnings,
    }


@router.post("/preproc/nodes/rescan")
async def rescan_nodes(request: Request):
    reg = _registry(request)
    reg.discover()
    return {"n_nodes": len(reg.names()), "shadowed": len(reg.shadowed())}


SCAFFOLDS = {
    "interface": '''"""A plain-Python preprocessing node: read inputs, write outputs into out_dir."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.preproc.node_registry import preproc_node


@preproc_node("my_node")
class MyNode:
    name = "my_node"
    version = "0.1.0"
    description = "What this node does, in one line."
    INPUTS = {"in_file": {"kind": "nifti", "required": True}}
    OUTPUTS = {"out_file": {"kind": "nifti"}}
    PARAM_SCHEMA: dict[str, Any] = {
        "strength": {"type": "float", "default": 1.0, "description": "Example parameter."},
    }
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def run(self, inputs: dict[str, Any], out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
        in_file = Path(inputs["in_file"])
        out_file = out_dir / f"{in_file.name.split('.')[0]}_my_node.nii.gz"
        # ... do the work ...
        return {"out_file": out_file}
''',
    "composite": '''"""A nipype sub-workflow as one node. Ports = fields of inputnode / outputnode."""

from __future__ import annotations

from typing import Any

from fmriflow.preproc.node_registry import preproc_node


@preproc_node("my_workflow", kind="composite")
class MyWorkflow:
    name = "my_workflow"
    version = "0.1.0"
    description = "What this workflow does, in one line."
    INPUTS = {"in_file": {"kind": "nifti", "required": True}}
    OUTPUTS = {"out_file": {"kind": "nifti"}}
    PARAM_SCHEMA: dict[str, Any] = {}
    REQUIRED_PYTHON: list[str] = ["nipype>=1.8"]
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def validate(self, config: Any) -> list[str]:
        return []

    def build(self, config: Any):
        from nipype import Node, Workflow
        from nipype.interfaces.utility import IdentityInterface

        wf = Workflow(name="my_workflow")
        inputnode = Node(IdentityInterface(fields=["in_file"]), name="inputnode")
        outputnode = Node(IdentityInterface(fields=["out_file"]), name="outputnode")
        # ... add real nodes between inputnode and outputnode ...
        wf.connect(inputnode, "in_file", outputnode, "out_file")
        return wf

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]):
        return None
''',
    "container_app": '''"""A command-line / containerised app as one node."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.preproc.node_registry import preproc_node


@preproc_node("my_app", kind="container_app")
class MyApp:
    name = "my_app"
    version = "0.1.0"
    description = "What this app does, in one line."
    INNER_NIPYPE_LOG = False
    # Optional: opt into built-in run views, e.g. {"report": "report_html"}.
    UI: dict = {}
    INPUTS = {"in_file": {"kind": "nifti", "required": True}}
    OUTPUTS = {"out_file": {"kind": "nifti"}}
    PARAM_SCHEMA: dict[str, Any] = {}
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = ["mytool"]
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        return []

    def build_command(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> list[str]:
        return ["mytool", str(inputs["in_file"]), str(out_dir / "result.nii.gz")]

    def collect(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> dict[str, Any]:
        return {"out_file": out_dir / "result.nii.gz"}
''',
}
