"""Transform — the contract a registered Stage-N transform satisfies.

A transform is a single-purpose operation that runs *after* a
bootstrap stage in a preprocessing pipeline (smooth, mask, regress
confounds, …). It consumes the prior stage's manifest + outputs
and emits updated ones — the stack runner appends a ``StepRecord``
to ``PreprocManifest.additional_steps`` after each transform
completes.

The shape is intentionally close to the existing nipype-node
Protocol (``INPUTS`` / ``OUTPUTS`` / ``PARAM_SCHEMA`` / ``run``)
so a single class can satisfy both — useful when a node is useful
both inside the post-preproc DAG builder and as a transform in
the stack. The two registries are kept deliberately separate so
the surfaces don't collide.

See ``devdocs/proposals/data-processing/preprocessing-stack.md``
for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from fmriflow.modules._schema import ParamSchema


TransformSource = str  # "built-in" | "user" | "pip:<package-name>"


@dataclass(frozen=True)
class TransformInfo:
    """Externally-visible record of a registered transform.

    Returned by ``TransformRegistry.list()`` so the frontend can
    render the "+ Add transform" picker without instantiating each
    class.
    """

    name: str
    version: str
    description: str
    source: TransformSource
    container_bound: bool
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    required_python: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)


@runtime_checkable
class Transform(Protocol):
    """Structural contract for a registered Stage-N transform.

    Implementations are classes decorated with
    ``@register_transform("name")``. The Protocol is
    ``runtime_checkable`` so the registry can guard against partial
    implementations.

    Class-level metadata mirrors the existing nipype-node Protocol
    so a single class can serve as both a transform and a
    post-preproc DAG node.
    """

    # ── Class-level metadata ──

    name: str
    version: str
    description: str

    INPUTS: list[str]          # input keys (e.g. ["in_file"])
    OUTPUTS: list[str]         # output keys (e.g. ["out_file"])
    PARAM_SCHEMA: ParamSchema

    REQUIRED_PYTHON: list[str]
    REQUIRED_TOOLS: list[str]
    REQUIRED_ENV: list[str]
    CONTAINER: str | None

    # ── Instance methods ──

    def run(
        self,
        inputs: dict[str, Any],
        out_dir: Any,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the transform.

        ``inputs`` maps input keys (from ``INPUTS``) to the file
        paths the prior stage produced. ``out_dir`` is the
        per-stage working directory. ``params`` is the
        user-supplied parameter dict for this stage.

        Returns a dict mapping output keys (from ``OUTPUTS``) to
        the produced file paths.
        """
