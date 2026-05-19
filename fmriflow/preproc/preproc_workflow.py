"""PreprocWorkflow — the contract a registered nipype bootstrap workflow satisfies.

A bootstrap workflow is one of several "kinds" of Stage 0 in the
preprocessing stack (others: fmriprep, custom, bids_app, passthrough).
Registered nipype workflows live in the WorkflowRegistry and are
picked by name (``bootstrap.kind == "nipype"``,
``bootstrap.workflow == "<name>"``).

The contract is intentionally minimal:

- ``build(config)`` is the only nipype-API-shaped method. Everything
  else (config, manifest, params, preflight) speaks fMRIflow's
  vocabulary so the workflow author writes nipype where it makes
  sense and stays out of the rest.
- ``to_manifest`` translates whatever the workflow's output node
  emitted into the backend-agnostic ``PreprocManifest`` contract.
  Without it, downstream consumers (analysis, autoflatten, QC)
  can't find anything — so it's the load-bearing piece.

See ``devdocs/proposals/data-processing/preprocessing-stack.md``
(Importing user nipype workflows) for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from fmriflow.modules._schema import ParamSchema


WorkflowSource = str  # "built-in" | "user" | "pip:<package-name>"


@dataclass(frozen=True)
class WorkflowInfo:
    """Externally-visible record of a registered workflow.

    Returned by ``WorkflowRegistry.list()`` so the frontend can
    render the workflow dropdown without instantiating each class.
    """

    name: str
    version: str
    description: str
    source: WorkflowSource
    container_bound: bool
    required_python: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)


@runtime_checkable
class PreprocWorkflow(Protocol):
    """Structural contract for a registered nipype bootstrap workflow.

    Implementations are classes decorated with
    ``@register_preproc_workflow("name")``. They satisfy this Protocol
    by declaring the class attributes below and implementing the
    three methods. The Protocol is ``runtime_checkable`` so the
    registry can guard against partial implementations on register.
    """

    # ── Class-level metadata (must be set; class-level attributes) ──

    name: str
    version: str
    description: str

    PARAM_SCHEMA: ParamSchema
    REQUIRED_PYTHON: list[str]   # PEP 508 requirement strings
    REQUIRED_TOOLS: list[str]    # executables that must be on PATH
    REQUIRED_ENV: list[str]      # env vars that must be set
    CONTAINER: str | None        # docker/singularity ref or None

    # ── Instance methods ──

    def validate(self, config: Any) -> list[str]:
        """Workflow-specific config checks beyond the backend's."""

    def build(self, config: Any) -> Any:
        """Return an unscheduled nipype Workflow ready for ``.run()``.

        Kept ``Any`` so the Protocol doesn't import nipype at type-check
        time — nipype is a heavy optional dep we only want loaded when
        actually building.
        """

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]) -> Any:
        """Translate the workflow's output-node values into a
        ``PreprocManifest``. Required — without it, downstream
        consumers can't find the preprocessed BOLDs.
        """
