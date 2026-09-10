"""Import an existing nipype pipeline (.py) as a composite node.

Three shapes of file are understood:

1. A class already decorated with ``@preproc_node`` /
   ``@register_preproc_workflow`` — the file is copied into
   ``addons/nodes/`` as-is.
2. A module-level ``build(config)`` function (or ``create_workflow`` /
   ``make_workflow``) returning a nipype ``Workflow``.
3. A module-level ``Workflow`` object.

For 2 and 3 a scaffold class is written that wraps the original file:
``build`` imports the user's module by path and returns its workflow, and
the ports are read from the workflow's ``inputnode`` / ``outputnode``
(when it can be built without a real config); otherwise the scaffold
carries a ``TODO`` for the author to fill them in.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

BUILD_FUNCTION_NAMES = ("build", "create_workflow", "make_workflow", "init_workflow")
_SLUG_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


@dataclass
class ImportSpec:
    """What :func:`inspect_pipeline_file` found."""

    path: Path
    shape: str                        # "registered" | "build_function" | "workflow_object"
    symbol: str                       # class / function / variable name
    node_name: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _ProbeConfig(SimpleNamespace):
    """A config that answers "" / {} for anything a build() asks for."""

    def __getattr__(self, name: str) -> Any:  # pragma: no cover — trivial
        if name.startswith("__"):
            raise AttributeError(name)
        return {} if name in ("params", "backend_params") else ""


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_fmriflow_import_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_workflow(obj: Any) -> bool:
    try:
        from nipype.pipeline.engine import Workflow
    except ImportError:  # pragma: no cover
        return False
    return isinstance(obj, Workflow)


def _ports_of(wf: Any) -> tuple[list[str], list[str]]:
    from fmriflow.preproc.nipype_adapters import composite_ports
    return composite_ports(wf)


def inspect_pipeline_file(path: Path | str, *, node_name: str | None = None) -> ImportSpec:
    """Load ``path`` and work out how it can become a node."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    default_name = node_name or re.sub(r"[^a-zA-Z0-9_]", "_", path.stem)
    if not _SLUG_RE.match(default_name):
        raise ValueError(f"invalid node name {default_name!r}")

    from fmriflow.preproc.node_registry import registered_nodes
    before = dict(registered_nodes())
    module = _load_module(path)
    after = registered_nodes()

    # 1. Already a registered node class.
    for name, cls in after.items():
        if before.get(name) is cls:
            continue
        if getattr(cls, "__module__", "") == module.__name__:
            from fmriflow.preproc.node_registry import node_ports
            ins, outs = node_ports(cls)
            return ImportSpec(path=path, shape="registered", symbol=cls.__name__,
                              node_name=name, inputs=sorted(ins), outputs=sorted(outs))

    # 2. build() function.
    for fn_name in BUILD_FUNCTION_NAMES:
        fn = getattr(module, fn_name, None)
        if callable(fn):
            spec = ImportSpec(path=path, shape="build_function", symbol=fn_name, node_name=default_name)
            try:
                wf = fn(_ProbeConfig())
                if _is_workflow(wf):
                    spec.inputs, spec.outputs = _ports_of(wf)
                else:
                    spec.warnings.append(f"{fn_name}() did not return a nipype Workflow when probed")
            except Exception as e:  # the probe config is not a real one
                spec.warnings.append(f"could not probe {fn_name}() for ports: {e}")
            return spec

    # 3. Module-level Workflow object.
    for sym, obj in vars(module).items():
        if not sym.startswith("_") and _is_workflow(obj):
            ins, outs = _ports_of(obj)
            return ImportSpec(path=path, shape="workflow_object", symbol=sym,
                              node_name=default_name, inputs=ins, outputs=outs)

    raise ValueError(
        f"{path.name}: no registered node class, no {'/'.join(BUILD_FUNCTION_NAMES)} "
        f"function and no module-level nipype Workflow found"
    )


def _scaffold(spec: ImportSpec, source_path: Path) -> str:
    ports_in = ", ".join(f'"{p}"' for p in spec.inputs)
    ports_out = ", ".join(f'"{p}"' for p in spec.outputs)
    todo = "" if (spec.inputs or spec.outputs) else (
        "    # TODO: list the fields of the workflow's inputnode / outputnode here.\n"
    )
    if spec.shape == "build_function":
        build_body = f"        return _module().{spec.symbol}(config)"
    else:
        build_body = f"        return _module().{spec.symbol}"
    return textwrap.dedent(f'''\
        """Imported nipype pipeline: {source_path.name} -> composite node ``{spec.node_name}``.

        Generated by fmriflow's pipeline importer. ``build`` delegates to the
        original file, kept next to this one as ``{source_path.name}``.
        """

        from __future__ import annotations

        import importlib.util
        from pathlib import Path
        from typing import Any

        from fmriflow.preproc.node_registry import preproc_node

        _SOURCE = Path(__file__).with_name("{source_path.name}")


        def _module():
            spec = importlib.util.spec_from_file_location("_imported_{spec.node_name}", _SOURCE)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module


        @preproc_node("{spec.node_name}", kind="composite")
        class Imported_{spec.node_name}:
            name = "{spec.node_name}"
            version = "0.1.0"
            description = "Imported from {source_path.name}"
            REQUIRED_PYTHON: list[str] = ["nipype>=1.8"]
            REQUIRED_TOOLS: list[str] = []
            REQUIRED_ENV: list[str] = []
            CONTAINER: str | None = None
            PARAM_SCHEMA: dict[str, Any] = {{}}
        {todo}    INPUTS = [{ports_in}]
            OUTPUTS = [{ports_out}]

            def validate(self, config: Any) -> list[str]:
                return []

            def build(self, config: Any) -> Any:
        {build_body}

            def to_manifest(self, config: Any, wf_outputs: dict[str, Any]):
                return None
        ''')


def import_pipeline_file(
    path: Path | str,
    *,
    node_name: str | None = None,
    dest_dir: Path | str | None = None,
) -> tuple[Path, ImportSpec]:
    """Copy ``path`` into the user nodes dir and, when needed, write a scaffold.

    Returns ``(node_file, spec)``: the ``.py`` the registry will load.
    """
    spec = inspect_pipeline_file(path, node_name=node_name)
    if dest_dir is None:
        from fmriflow.core.paths import addons_dir
        dest_dir = addons_dir("nodes")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if spec.shape == "registered":
        target = dest_dir / f"{spec.node_name}.py"
        if Path(path).resolve() != target.resolve():
            shutil.copyfile(path, target)
        return target, spec

    source_copy = dest_dir / f"_{spec.node_name}_source.py"   # leading _ : not scanned as a node
    shutil.copyfile(path, source_copy)
    target = dest_dir / f"{spec.node_name}.py"
    target.write_text(_scaffold(spec, source_copy))
    compile(target.read_text(), str(target), "exec")
    return target, spec
