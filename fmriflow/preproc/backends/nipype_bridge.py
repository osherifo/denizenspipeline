"""`nipype` backend — run a registered nipype workflow as a preproc stage.

The registry of nipype bootstrap workflows was only reachable through the
PreprocStack API (``POST /api/preproc/stack/run``). Workflow *stages*, by
contrast, dispatch on ``preproc.backend`` through the legacy backend
registry — so ``bootstrap.kind: nipype`` could not be used from a workflow
YAML at all, and any registered nipype workflow was invisible to the
convert → preproc → autoflatten chain.

This is the mirror image of ``nipype_workflows/backend_adapters.py``, which
exposes legacy backends *as* workflows. This exposes workflows *as* a
backend, so a workflow stage can say:

    preproc:
      subject: "01"
      backend: nipype
      bids_dir: ...
      output_dir: ...
      backend_params:
        workflow: mp2rage_background_clean
        method: soft

Every workflow in the registry becomes usable from a workflow YAML, not
just the one this was written for.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fmriflow.preproc.backends import register_backend
from fmriflow.preproc.errors import BackendRunError
from fmriflow.preproc.manifest import PreprocConfig, PreprocManifest, PreprocStatus

logger = logging.getLogger(__name__)


class _WorkflowCallConfig:
    """The shape registered workflows expect.

    Mirrors the dataclass the stack runner passes, so a workflow behaves
    identically whether it was launched from the stack or from a
    workflow stage.
    """

    def __init__(self, config: PreprocConfig, params: dict):
        self.subject = config.subject
        self.output_dir = str(config.output_dir)
        self.bids_dir = str(config.bids_dir) if config.bids_dir else None
        self.derivatives_dir = str(config.raw_dir) if config.raw_dir else None
        self.sessions = list(config.sessions or [])
        self.task = config.task
        # NOT config.task. `task` is a BIDS task filter; `dataset` is the
        # run-group label that lands in manifest.dataset, and conflating them
        # mislabels the manifest for anything that queries it. identity.py
        # carries the same warning. PreprocConfig has no dataset field, so it
        # comes from backend_params or falls back.
        # Copy before consuming, so the caller's dict is never mutated.
        remaining = dict(params)
        self.dataset = str(remaining.pop("dataset", "") or "unknown")
        self.backend_params = remaining


def _registry():
    from fmriflow.preproc.workflow_registry import WorkflowRegistry

    reg = WorkflowRegistry()
    reg.discover()
    return reg


def _resolve(config: PreprocConfig):
    """Return (workflow_instance, params) or raise ValueError."""
    params = dict(config.backend_params or {})
    name = params.pop("workflow", None)
    if not name:
        raise ValueError(
            "backend 'nipype' requires backend_params.workflow — the name of a "
            "registered workflow. Available: "
            + ", ".join(sorted(w.name for w in _registry().list()))
        )
    reg = _registry()
    known = {w.name for w in reg.list()}
    if name not in known:
        raise ValueError(
            f"unknown nipype workflow {name!r}. Available: {', '.join(sorted(known))}"
        )
    return reg.get(name), params


@register_backend("nipype")
class NipypeWorkflowBackend:
    """Bridge the nipype workflow registry into the preproc backend registry."""

    name = "nipype"

    def validate(self, config: PreprocConfig) -> list[str]:
        try:
            workflow, params = _resolve(config)
        except ValueError as e:
            return [str(e)]
        return list(workflow.validate(_WorkflowCallConfig(config, params)))

    def run(self, config: PreprocConfig) -> PreprocManifest:
        workflow, params = _resolve(config)
        call_config = _WorkflowCallConfig(config, params)

        errors = workflow.validate(call_config)
        if errors:
            raise BackendRunError(
                f"workflow '{workflow.name}' rejected the config: " + "; ".join(errors),
                backend="nipype",
                subject=config.subject,
            )

        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
        built = workflow.build(call_config)

        outputs: dict[str, Any] = {}
        if built is not None:
            run_method = getattr(built, "run", None)
            if not callable(run_method):
                raise BackendRunError(
                    f"workflow '{workflow.name}'.build() returned "
                    f"{type(built).__name__}, which is not runnable",
                    backend="nipype",
                    subject=config.subject,
                )
            logger.info("Executing nipype workflow %r", workflow.name)
            # Linear: this already runs inside a job sized by the caller.
            outputs = {"nipype_result": run_method(plugin="Linear")}

        return workflow.to_manifest(call_config, outputs)

    def status(self, config: PreprocConfig) -> PreprocStatus:
        """Completion means outputs exist, not that the directory does.

        ``run()`` creates ``output_dir`` before executing the workflow, so
        treating its existence as success reports a run complete while it is
        still going — or after it has failed early. Mirrors the `custom`
        backend: pending, then running, then completed once something is
        actually there.
        """
        out = Path(config.output_dir)
        if not out.exists():
            return PreprocStatus(status="pending")

        pattern = (config.backend_params or {}).get("file_pattern", "*.nii*")
        produced = [p for p in out.rglob(pattern) if p.is_file()]
        if produced:
            return PreprocStatus(
                status="completed",
                detail=f"{len(produced)} output file(s) found",
            )
        return PreprocStatus(status="running")

    def collect(self, config: PreprocConfig) -> PreprocManifest:
        """Rebuild the manifest from existing outputs without re-running."""
        workflow, params = _resolve(config)
        return workflow.to_manifest(_WorkflowCallConfig(config, params), {})
