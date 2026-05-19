"""StackRunner — executes a PreprocStack end-to-end.

Phase 4a (this module): minimum viable runner.

- Validates the stack (bootstrap kind known, transforms registered,
  preflight passes).
- Runs the bootstrap stage. For ``nipype`` kind, looks the workflow
  up in the WorkflowRegistry; for ``passthrough`` kind, emits a
  stub manifest. Other kinds (``fmriprep`` / ``custom`` /
  ``bids_app``) raise NotImplementedError — they'll be wired in
  Phase 4b once their existing PreprocBackend adapters are
  adapted to the new contract.
- Runs each transform sequentially via the TransformRegistry,
  threads the manifest through stages, appends a ``StepRecord``
  after each transform.
- Returns the final manifest + per-stage manifest snapshots.

Phase 4b adds fingerprint caching and "run from stage N". Phase
4c adds resume-mid-stack. Phase 5 wires this into the server's
detached-subprocess + run-registry machinery.

See ``devdocs/proposals/data-processing/preprocessing-stack.md``
for the full design.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fmriflow.preproc.manifest import PreprocManifest, now_iso
from fmriflow.preproc.preflight import preflight
from fmriflow.preproc.stack import (
    BOOTSTRAP_KINDS,
    BootstrapStage,
    PreprocStack,
    StepRecord,
    TransformStage,
)
from fmriflow.preproc.transform_registry import TransformRegistry
from fmriflow.preproc.workflow_registry import WorkflowRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StackRunConfig:
    """Subject + paths binding for a single stack execution.

    The stack itself is a pure recipe; this config binds it to a
    specific subject + on-disk locations. Subsequent run-launch
    code (Phase 5) will wrap this in the existing run-registry
    machinery for detached subprocess + reattach support.
    """

    subject: str
    output_dir: Path
    bids_dir: Path | None = None
    derivatives_dir: Path | None = None  # for ``passthrough`` bootstrap
    dataset: str = "unknown"
    sessions: list[str] = field(default_factory=list)
    task: str | None = None


@dataclass(frozen=True)
class _WorkflowCallConfig:
    """The config object handed to a registered nipype workflow's
    validate / build / to_manifest methods.

    Combines the run binding (subject / paths / sessions / task)
    with the bootstrap stage's user-supplied params under
    ``backend_params``. Workflows duck-type on the attributes they
    need; the identity workflow only reads ``subject`` / ``task`` /
    ``sessions`` / ``output_dir``, while a real workflow reads
    ``backend_params["output_space"]`` etc.

    The passthrough workflow reads ``derivatives_dir``; the
    backend-wrapper workflows translate this whole object back into
    a legacy ``PreprocConfig``.
    """

    subject: str
    output_dir: str
    bids_dir: str | None
    derivatives_dir: str | None
    sessions: list[str]
    task: str | None
    dataset: str
    backend_params: dict[str, Any]


@dataclass
class StackRunResult:
    """Outcome of executing a ``PreprocStack``.

    ``stage_manifests`` is indexed parallel to the stack: index 0
    is the bootstrap output, indices 1..N are the manifest after
    each transform. ``manifest`` is the final stage's manifest —
    what downstream consumers (analysis, autoflatten, QC) read.
    """

    status: str  # "completed" | "failed"
    manifest: PreprocManifest | None = None
    stage_manifests: list[PreprocManifest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0


# ── Runner ────────────────────────────────────────────────────────


class StackRunner:
    """Executes a ``PreprocStack`` end-to-end.

    The runner is stateless across runs — call ``run()`` for each
    stack execution. The registries it depends on are passed in at
    construction so tests can inject isolated instances.
    """

    def __init__(
        self,
        workflow_registry: WorkflowRegistry,
        transform_registry: TransformRegistry,
    ) -> None:
        self.workflow_registry = workflow_registry
        self.transform_registry = transform_registry

    # ── Entry point ───────────────────────────────────────────────

    def run(self, stack: PreprocStack, config: StackRunConfig) -> StackRunResult:
        started = time.monotonic()

        errors = self._validate(stack)
        if errors:
            return StackRunResult(
                status="failed",
                errors=errors,
                duration_s=time.monotonic() - started,
            )

        try:
            bootstrap_manifest = self._run_bootstrap(stack.bootstrap, config)
        except NotImplementedError as e:
            return StackRunResult(
                status="failed",
                errors=[f"Bootstrap not implemented: {e}"],
                duration_s=time.monotonic() - started,
            )
        except Exception as e:
            logger.exception("Bootstrap stage failed")
            return StackRunResult(
                status="failed",
                errors=[f"Bootstrap stage failed: {e}"],
                duration_s=time.monotonic() - started,
            )

        stage_manifests: list[PreprocManifest] = [bootstrap_manifest]
        current = bootstrap_manifest

        for index, transform_stage in enumerate(stack.transforms, start=1):
            try:
                current = self._run_transform(
                    transform_stage, current, config, stage_index=index,
                )
            except Exception as e:
                logger.exception(
                    "Transform stage %d (%s) failed", index, transform_stage.name,
                )
                return StackRunResult(
                    status="failed",
                    manifest=current,
                    stage_manifests=stage_manifests,
                    errors=[
                        f"Stage {index} ({transform_stage.name}) failed: {e}"
                    ],
                    duration_s=time.monotonic() - started,
                )
            stage_manifests.append(current)

        return StackRunResult(
            status="completed",
            manifest=current,
            stage_manifests=stage_manifests,
            duration_s=time.monotonic() - started,
        )

    # ── Validation ────────────────────────────────────────────────

    def _resolve_workflow_name(self, bootstrap: BootstrapStage) -> str | None:
        """Map a BootstrapStage to its effective workflow-registry name.

        For ``kind == "nipype"``, the user-supplied
        ``bootstrap.workflow`` is the name. For other kinds, the kind
        itself is the workflow name (``fmriprep`` / ``custom`` /
        ``bids_app`` / ``passthrough``) — each of those is registered
        as a built-in workflow that wraps the corresponding adapter.

        Returns ``None`` if the kind requires a workflow name but none
        was supplied; the caller surfaces this as a validation error.
        """
        if bootstrap.kind == "nipype":
            return bootstrap.workflow or None
        return bootstrap.kind

    def _validate(self, stack: PreprocStack) -> list[str]:
        errors: list[str] = []

        kind = stack.bootstrap.kind
        if kind not in BOOTSTRAP_KINDS:
            errors.append(
                f"Unknown bootstrap kind: '{kind}'. "
                f"Known kinds: {', '.join(BOOTSTRAP_KINDS)}"
            )
        else:
            workflow_name = self._resolve_workflow_name(stack.bootstrap)
            if kind == "nipype" and not workflow_name:
                errors.append(
                    "Bootstrap kind 'nipype' requires a workflow name "
                    "(set BootstrapStage.workflow)."
                )
            elif workflow_name not in self.workflow_registry.names():
                errors.append(
                    f"Unknown workflow: '{workflow_name}'. "
                    f"Available: {', '.join(self.workflow_registry.names()) or '(none)'}"
                )
            else:
                wf = self.workflow_registry.get(workflow_name)
                pre = preflight(wf)
                if not pre.ok:
                    errors.extend(f"Workflow '{workflow_name}': {e}" for e in pre.errors)

        for index, transform_stage in enumerate(stack.transforms, start=1):
            name = transform_stage.name
            if name not in self.transform_registry.names():
                errors.append(
                    f"Stage {index}: unknown transform '{name}'. "
                    f"Available: {', '.join(self.transform_registry.names()) or '(none)'}"
                )
                continue
            transform = self.transform_registry.get(name)
            pre = preflight(transform)
            if not pre.ok:
                errors.extend(
                    f"Stage {index} ({name}): {e}" for e in pre.errors
                )

        return errors

    # ── Bootstrap dispatch ────────────────────────────────────────

    def _run_bootstrap(
        self, bootstrap: BootstrapStage, config: StackRunConfig,
    ) -> PreprocManifest:
        """Dispatch every bootstrap kind through the workflow registry.

        Built-in wrappers cover ``fmriprep`` / ``custom`` / ``bids_app``;
        ``passthrough`` is a built-in nipype-shaped workflow that
        scans derivatives. ``nipype`` kind uses the user-supplied
        ``bootstrap.workflow`` name. The dispatch is uniform from
        here on.
        """
        workflow_name = self._resolve_workflow_name(bootstrap)
        if workflow_name is None:
            # Defensive — _validate catches this; should never reach here.
            raise ValueError(
                "BootstrapStage.kind='nipype' without a workflow name "
                "should have been caught in validation."
            )
        workflow = self.workflow_registry.get(workflow_name)

        wf_config = _WorkflowCallConfig(
            subject=config.subject,
            output_dir=str(config.output_dir),
            bids_dir=str(config.bids_dir) if config.bids_dir else None,
            derivatives_dir=(
                str(config.derivatives_dir) if config.derivatives_dir else None
            ),
            sessions=list(config.sessions),
            task=config.task,
            dataset=config.dataset,
            backend_params=dict(bootstrap.params),
        )

        wf_errors = workflow.validate(wf_config)
        if wf_errors:
            raise ValueError(
                f"Workflow '{workflow_name}' rejected config: "
                + "; ".join(wf_errors)
            )

        built = workflow.build(wf_config)
        outputs = self._execute_workflow(built)
        return workflow.to_manifest(wf_config, outputs)

    def _execute_workflow(self, built: Any) -> dict[str, Any]:
        """Execute whatever ``workflow.build()`` returned.

        Three shapes are recognised:

        - ``None`` — nothing to execute (e.g. identity workflow,
          passthrough). Outputs are empty; ``to_manifest`` builds
          everything from config + the registry-side scan.
        - ``_BackendBuildSentinel`` — a legacy ``PreprocBackend`` adapter
          to invoke. The runner calls ``sentinel.backend.run`` and
          packages the resulting manifest into
          ``outputs["manifest"]`` so the workflow wrapper's
          ``to_manifest`` can return it.
        - anything else — a real nipype Workflow. Not wired yet; will
          land when the real reference workflow does.
        """
        if built is None:
            return {}

        # Import locally so this module doesn't pull the wrapper at
        # import time (avoids the slight circularity of
        # backend_adapters → workflow_registry → … → stack_runner).
        from fmriflow.preproc.backends.nipype_workflows.backend_adapters import (
            _BackendBuildSentinel,
        )

        if isinstance(built, _BackendBuildSentinel):
            manifest = built.backend.run(built.preproc_config)
            return {"manifest": manifest}

        raise NotImplementedError(
            "Real nipype workflow execution not yet wired — only the "
            "identity / passthrough placeholders and the backend-wrapper "
            "sentinels are supported in Phase 4b."
        )

    # ── Transform stage ───────────────────────────────────────────

    def _run_transform(
        self,
        stage: TransformStage,
        prior_manifest: PreprocManifest,
        config: StackRunConfig,
        *,
        stage_index: int,
    ) -> PreprocManifest:
        transform = self.transform_registry.get(stage.name)

        inputs = self._collect_inputs(prior_manifest, transform)

        out_dir = config.output_dir / f"stage_{stage_index:02d}_{stage.name}"
        out_dir.mkdir(parents=True, exist_ok=True)

        started = time.monotonic()
        outputs = transform.run(inputs, out_dir, dict(stage.params))
        duration = time.monotonic() - started

        step = StepRecord(
            name=stage.name,
            version=getattr(transform, "version", ""),
            params=dict(stage.params),
            input_stage=stage_index - 1,
            output_dir=str(out_dir),
            duration_s=duration,
            fingerprint="",  # Phase 4b adds fingerprinting
        )

        return self._extend_manifest(prior_manifest, step, outputs, out_dir)

    def _collect_inputs(
        self, manifest: PreprocManifest, transform: Any,
    ) -> dict[str, Any]:
        """Build the ``inputs`` dict the transform's ``run`` expects.

        Phase 4a: for each key in ``transform.INPUTS``, look up the
        path in the prior manifest's first ``RunRecord.output_file``
        (the "preprocessed BOLD"). If the manifest has no runs (e.g.
        identity bootstrap), inputs are empty paths — the identity
        transform tolerates that, real transforms wouldn't.
        """
        wanted = list(getattr(transform, "INPUTS", []) or [])
        if not wanted:
            return {}
        # For now, a naive mapping: first input key → first run's output file.
        if not manifest.runs:
            return {key: None for key in wanted}
        first_run = manifest.runs[0]
        # Single input → first run output; multiple inputs → user-supplied transforms
        # need richer wiring (Phase 4b/5 — wiring config in the stack).
        return {wanted[0]: Path(first_run.output_file)}

    def _extend_manifest(
        self,
        prior: PreprocManifest,
        step: StepRecord,
        outputs: dict[str, Any],
        out_dir: Path,
    ) -> PreprocManifest:
        """Build a new manifest extending ``prior`` with ``step``.

        ``output_dir`` updates to ``out_dir`` so downstream consumers
        always read the freshest stage. ``additional_steps`` gets the
        new ``StepRecord`` appended.
        """
        return PreprocManifest(
            subject=prior.subject,
            dataset=prior.dataset,
            sessions=list(prior.sessions),
            runs=list(prior.runs),
            backend=prior.backend,
            backend_version=prior.backend_version,
            parameters=dict(prior.parameters),
            space=prior.space,
            resolution=prior.resolution,
            confounds_applied=list(prior.confounds_applied),
            additional_steps=[*prior.additional_steps, step],
            output_dir=str(out_dir),
            output_format=prior.output_format,
            file_pattern=prior.file_pattern,
            created=now_iso(),
            pipeline_version=prior.pipeline_version,
            checksum=None,
            freesurfer_subjects_dir=prior.freesurfer_subjects_dir,
            autoflatten=prior.autoflatten,
            manifest_version=prior.manifest_version,
        )
