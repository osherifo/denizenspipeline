"""Backend-adapter workflows — wrap existing PreprocBackend adapters as workflows.

The pre-stack codebase shipped three working ``PreprocBackend``
implementations (``fmriprep`` / ``custom`` / ``bids_app``) plus a real
passthrough workflow (sibling ``passthrough.py``). The stack runner
unifies on the ``PreprocWorkflow`` Protocol so every bootstrap kind
flows through the same dispatch. Rather than rewriting the existing
backends, we wrap them here: each wrapper satisfies the workflow
Protocol and delegates the heavy lifting to the established
``PreprocBackend.run`` adapter.

Lives under ``fmriflow.preproc.backends.nipype_workflows`` so the
WorkflowRegistry's built-in scan picks these up and source-tags them
``built-in`` like any other shipped workflow.

The wrappers' ``build()`` returns a ``_BackendBuildSentinel``. The
StackRunner recognises that sentinel in ``_execute_workflow`` and
calls ``sentinel.backend.run(sentinel.preproc_config)``. The resulting
``PreprocManifest`` is handed back to ``to_manifest`` via the
``outputs["manifest"]`` slot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fmriflow.preproc.backends import get_backend
from fmriflow.preproc.manifest import PreprocConfig, PreprocManifest
from fmriflow.preproc.workflow_registry import register_preproc_workflow


@dataclass(frozen=True)
class _BackendBuildSentinel:
    """Marker the StackRunner recognises in ``_execute_workflow``.

    Carries the ``PreprocBackend`` instance to invoke + the
    ``PreprocConfig`` to invoke it with. The runner does:

        manifest = sentinel.backend.run(sentinel.preproc_config)
        return {"manifest": manifest}

    This keeps the StackRunner's ``_execute_workflow`` ignorant of
    individual backend semantics — it only knows "run() returns a
    manifest."
    """

    backend: Any              # PreprocBackend
    preproc_config: PreprocConfig


def _to_preproc_config(config: Any, backend_name: str) -> PreprocConfig:
    """Translate the runner's ``_WorkflowCallConfig`` into the
    legacy ``PreprocConfig`` shape the wrapped backends expect."""
    return PreprocConfig(
        subject=getattr(config, "subject", ""),
        backend=backend_name,
        output_dir=str(getattr(config, "output_dir", "")),
        bids_dir=str(getattr(config, "bids_dir", "") or "") or None,
        sessions=list(getattr(config, "sessions", []) or []),
        task=getattr(config, "task", None),
        backend_params=dict(getattr(config, "backend_params", {}) or {}),
    )


# ── fmriprep ──────────────────────────────────────────────────────


@register_preproc_workflow("fmriprep")
class FmriprepWorkflow:
    """Wraps the existing ``FmriprepBackend`` as a registered workflow.

    All fmriprep-specific configuration flows through
    ``bootstrap.params`` (which becomes ``PreprocConfig.backend_params``).
    The existing fmriprep adapter handles container resolution
    (singularity / docker / bare), CLI argument building, and
    manifest construction.
    """
    _NODE_REGISTRY_SKIP = True  # becomes a real container_app node

    name = "fmriprep"
    version = "wrapped"
    description = (
        "fmriprep — opinionated BIDS preprocessing. Wraps the existing "
        "FmriprepBackend adapter so the stack runner reaches it through "
        "the unified workflow Protocol."
    )

    PARAM_SCHEMA: dict = {}   # fmriprep's params are validated by FmriprepParams (legacy)
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []   # actual tool is whatever container_type resolves to
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None     # fmriprep manages its own containerisation

    def validate(self, config: Any) -> list[str]:
        return get_backend("fmriprep").validate(
            _to_preproc_config(config, "fmriprep")
        )

    def build(self, config: Any) -> Any:
        return _BackendBuildSentinel(
            backend=get_backend("fmriprep"),
            preproc_config=_to_preproc_config(config, "fmriprep"),
        )

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]) -> PreprocManifest:
        manifest = wf_outputs.get("manifest")
        if manifest is None:
            raise RuntimeError(
                "FmriprepWorkflow.to_manifest expected wf_outputs['manifest'] "
                "from the runner; got nothing. This is a runner/wrapper bug."
            )
        return manifest


# ── custom shell ──────────────────────────────────────────────────


@register_preproc_workflow("custom")
class CustomShellWorkflow:
    """Wraps the existing ``CustomBackend`` (shell-command template)."""
    _NODE_REGISTRY_SKIP = True  # becomes a real container_app node

    name = "custom"
    version = "wrapped"
    description = (
        "Custom shell-command backend. Wraps the existing CustomBackend "
        "adapter; the user supplies a shell template via "
        "``bootstrap.params['command']``."
    )

    PARAM_SCHEMA: dict = {}
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []   # entirely user-defined
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def validate(self, config: Any) -> list[str]:
        return get_backend("custom").validate(
            _to_preproc_config(config, "custom")
        )

    def build(self, config: Any) -> Any:
        return _BackendBuildSentinel(
            backend=get_backend("custom"),
            preproc_config=_to_preproc_config(config, "custom"),
        )

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]) -> PreprocManifest:
        manifest = wf_outputs.get("manifest")
        if manifest is None:
            raise RuntimeError(
                "CustomShellWorkflow.to_manifest expected wf_outputs['manifest'] "
                "from the runner."
            )
        return manifest


# ── BIDS-App generic ──────────────────────────────────────────────


@register_preproc_workflow("bids_app")
class BidsAppWorkflow:
    """Wraps the existing ``BidsAppBackend`` (any BIDS-App container)."""
    _NODE_REGISTRY_SKIP = True  # becomes a real container_app node

    name = "bids_app"
    version = "wrapped"
    description = (
        "Generic BIDS-App backend. Wraps the existing BidsAppBackend "
        "adapter; the user supplies the container image via "
        "``bootstrap.params['container']``."
    )

    PARAM_SCHEMA: dict = {}
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None     # user-supplied via backend_params

    def validate(self, config: Any) -> list[str]:
        return get_backend("bids_app").validate(
            _to_preproc_config(config, "bids_app")
        )

    def build(self, config: Any) -> Any:
        return _BackendBuildSentinel(
            backend=get_backend("bids_app"),
            preproc_config=_to_preproc_config(config, "bids_app"),
        )

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]) -> PreprocManifest:
        manifest = wf_outputs.get("manifest")
        if manifest is None:
            raise RuntimeError(
                "BidsAppWorkflow.to_manifest expected wf_outputs['manifest'] "
                "from the runner."
            )
        return manifest
