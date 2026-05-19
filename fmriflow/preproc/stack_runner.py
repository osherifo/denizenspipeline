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

from fmriflow.preproc.fingerprint import (
    bootstrap_fingerprint,
    transform_fingerprint,
)
from fmriflow.preproc.manifest import PreprocManifest, now_iso
from fmriflow.preproc.preflight import preflight
from fmriflow.preproc.stack import (
    BOOTSTRAP_KINDS,
    BootstrapStage,
    PreprocStack,
    StepRecord,
    TransformStage,
)
from fmriflow.preproc.stack_cache import StackCache
from fmriflow.preproc.stack_events import EventSink
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
    # Fingerprint of the bootstrap stage's manifest. Useful for tests
    # and for "stale badge" UI in Phase 6 — the transform fingerprints
    # already live on each StepRecord.
    bootstrap_fingerprint: str | None = None
    # True for each stage that was served from cache (skipped execution).
    # Indexed parallel to stage_manifests: index 0 = bootstrap, 1..N = transforms.
    stage_cache_hits: list[bool] = field(default_factory=list)


# ── Runner ────────────────────────────────────────────────────────


class StackRunner:
    """Executes a ``PreprocStack`` end-to-end.

    The runner is stateless across runs — call ``run()`` for each
    stack execution. The registries it depends on are passed in at
    construction so tests can inject isolated instances.
    """

    CACHE_DIR_NAME = ".preproc_stack_cache"

    def __init__(
        self,
        workflow_registry: WorkflowRegistry,
        transform_registry: TransformRegistry,
        *,
        use_cache: bool = True,
        event_sink: EventSink | None = None,
        force_from_stage: int | None = None,
    ) -> None:
        """``force_from_stage`` makes the runner ignore cache hits
        for any stage index >= the given value (i.e. those stages
        always re-execute). Stages before it still hit cache normally.
        ``None`` disables the override; ``0`` forces a full re-run of
        every stage."""
        self.workflow_registry = workflow_registry
        self.transform_registry = transform_registry
        self.use_cache = use_cache
        self.event_sink = event_sink
        self.force_from_stage = force_from_stage

    def _emit(self, event: dict) -> None:
        """Push an event to the sink if one is wired. No-op otherwise."""
        if self.event_sink is not None:
            try:
                self.event_sink(event)
            except Exception:
                logger.exception("event sink raised — ignoring")

    def _cache_for(self, config: StackRunConfig) -> StackCache | None:
        if not self.use_cache:
            return None
        return StackCache(root_dir=Path(config.output_dir) / self.CACHE_DIR_NAME)

    # ── Entry point ───────────────────────────────────────────────

    def run(self, stack: PreprocStack, config: StackRunConfig) -> StackRunResult:
        started = time.monotonic()

        errors = self._validate(stack)
        if errors:
            self._emit({"event": "failed", "errors": list(errors), "stage_index": None})
            return StackRunResult(
                status="failed",
                errors=errors,
                duration_s=time.monotonic() - started,
            )

        cache = self._cache_for(config)
        self._emit({
            "event": "started",
            "subject": config.subject,
            "n_stages": 1 + len(stack.transforms),
            "bootstrap_kind": stack.bootstrap.kind,
        })

        # ── Bootstrap ────────────────────────────────────────────
        workflow_name = self._resolve_workflow_name(stack.bootstrap)
        # _validate already guarantees this resolves cleanly.
        workflow = self.workflow_registry.get(workflow_name)  # type: ignore[arg-type]
        boot_fp = bootstrap_fingerprint(
            stack.bootstrap,
            workflow,
            bids_dir=config.bids_dir,
            derivatives_dir=config.derivatives_dir,
            subject=config.subject,
        )

        self._emit({
            "event": "stage_start",
            "stage_index": 0,
            "kind": "bootstrap",
            "stage_name": workflow_name,
            "fingerprint": boot_fp,
        })
        stage_started = time.monotonic()

        bootstrap_manifest: PreprocManifest | None = None
        bootstrap_from_cache = False
        # ``force_from_stage <= 0`` means "re-run bootstrap and
        # everything after"; skip the cache lookup in that case.
        bootstrap_forced = (
            self.force_from_stage is not None and self.force_from_stage <= 0
        )
        if cache is not None and not bootstrap_forced:
            bootstrap_manifest = cache.lookup(boot_fp)
            if bootstrap_manifest is not None:
                bootstrap_from_cache = True
                logger.info(
                    "Bootstrap cache hit (%s) — skipping execution.", boot_fp,
                )

        if bootstrap_manifest is None:
            try:
                bootstrap_manifest = self._run_bootstrap(stack.bootstrap, config)
            except NotImplementedError as e:
                self._emit({
                    "event": "stage_failed",
                    "stage_index": 0,
                    "stage_name": workflow_name,
                    "kind": "bootstrap",
                    "error": f"Bootstrap not implemented: {e}",
                })
                self._emit({"event": "failed", "errors": [f"Bootstrap not implemented: {e}"]})
                return StackRunResult(
                    status="failed",
                    errors=[f"Bootstrap not implemented: {e}"],
                    duration_s=time.monotonic() - started,
                    bootstrap_fingerprint=boot_fp,
                )
            except Exception as e:
                logger.exception("Bootstrap stage failed")
                self._emit({
                    "event": "stage_failed",
                    "stage_index": 0,
                    "stage_name": workflow_name,
                    "kind": "bootstrap",
                    "error": str(e),
                })
                self._emit({"event": "failed", "errors": [f"Bootstrap stage failed: {e}"]})
                return StackRunResult(
                    status="failed",
                    errors=[f"Bootstrap stage failed: {e}"],
                    duration_s=time.monotonic() - started,
                    bootstrap_fingerprint=boot_fp,
                )
            if cache is not None:
                cache.store(boot_fp, bootstrap_manifest)

        self._emit({
            "event": "stage_done",
            "stage_index": 0,
            "stage_name": workflow_name,
            "kind": "bootstrap",
            "cache_hit": bootstrap_from_cache,
            "fingerprint": boot_fp,
            "duration_s": time.monotonic() - stage_started,
        })

        stage_manifests: list[PreprocManifest] = [bootstrap_manifest]
        stage_cache_hits: list[bool] = [bootstrap_from_cache]
        current = bootstrap_manifest
        prior_fp = boot_fp

        # ── Transform stages ─────────────────────────────────────
        for index, transform_stage in enumerate(stack.transforms, start=1):
            transform = self.transform_registry.get(transform_stage.name)
            inputs = self._collect_inputs(current, transform)
            tx_fp = transform_fingerprint(
                transform_stage,
                transform,
                prior_fingerprint=prior_fp,
                inputs=inputs,
            )
            self._emit({
                "event": "stage_start",
                "stage_index": index,
                "kind": "transform",
                "stage_name": transform_stage.name,
                "fingerprint": tx_fp,
            })
            stage_started = time.monotonic()

            next_manifest: PreprocManifest | None = None
            from_cache = False
            # Skip the cache lookup when the user explicitly asked
            # to re-run this stage onwards.
            stage_forced = (
                self.force_from_stage is not None and index >= self.force_from_stage
            )
            if cache is not None and not stage_forced:
                next_manifest = cache.lookup(tx_fp)
                if next_manifest is not None:
                    from_cache = True
                    logger.info(
                        "Transform stage %d (%s) cache hit (%s) — skipping execution.",
                        index, transform_stage.name, tx_fp,
                    )

            if next_manifest is None:
                try:
                    next_manifest = self._run_transform(
                        transform_stage, current, config,
                        stage_index=index, fingerprint=tx_fp,
                        transform=transform, inputs=inputs,
                    )
                except Exception as e:
                    logger.exception(
                        "Transform stage %d (%s) failed", index, transform_stage.name,
                    )
                    self._emit({
                        "event": "stage_failed",
                        "stage_index": index,
                        "stage_name": transform_stage.name,
                        "kind": "transform",
                        "error": str(e),
                    })
                    self._emit({
                        "event": "failed",
                        "errors": [f"Stage {index} ({transform_stage.name}) failed: {e}"],
                    })
                    return StackRunResult(
                        status="failed",
                        manifest=current,
                        stage_manifests=stage_manifests,
                        stage_cache_hits=stage_cache_hits,
                        errors=[
                            f"Stage {index} ({transform_stage.name}) failed: {e}"
                        ],
                        duration_s=time.monotonic() - started,
                        bootstrap_fingerprint=boot_fp,
                    )
                if cache is not None:
                    cache.store(tx_fp, next_manifest)

            self._emit({
                "event": "stage_done",
                "stage_index": index,
                "stage_name": transform_stage.name,
                "kind": "transform",
                "cache_hit": from_cache,
                "fingerprint": tx_fp,
                "duration_s": time.monotonic() - stage_started,
            })

            stage_manifests.append(next_manifest)
            stage_cache_hits.append(from_cache)
            current = next_manifest
            prior_fp = tx_fp

        total_duration = time.monotonic() - started
        self._emit({
            "event": "completed",
            "n_stages": len(stage_manifests),
            "duration_s": total_duration,
        })
        return StackRunResult(
            status="completed",
            manifest=current,
            stage_manifests=stage_manifests,
            stage_cache_hits=stage_cache_hits,
            duration_s=total_duration,
            bootstrap_fingerprint=boot_fp,
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
        fingerprint: str,
        transform: Any,
        inputs: dict[str, Any],
    ) -> PreprocManifest:
        # ``out_dir`` includes the fingerprint prefix so distinct
        # configurations of the same stage index produce distinct
        # outputs — both can coexist on disk and the cache can hit
        # against either without one stomping the other.
        out_dir = (
            config.output_dir
            / f"stage_{stage_index:02d}_{stage.name}_{fingerprint[:8]}"
        )
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
            fingerprint=fingerprint,
        )

        return self._extend_manifest(prior_manifest, step, outputs, out_dir)

    def _collect_inputs(
        self, manifest: PreprocManifest, transform: Any,
    ) -> dict[str, Any]:
        """Build the ``inputs`` dict the transform's ``run`` expects.

        For each key in ``transform.INPUTS``, look up the path in
        the prior manifest's first ``RunRecord.output_file`` (the
        "preprocessed BOLD") and resolve relative paths against
        ``manifest.output_dir`` (the BIDS convention: RunRecord
        paths are relative to the manifest's root). If the manifest
        has no runs (e.g. identity bootstrap), inputs are ``None``
        — the identity transform tolerates that, real transforms
        wouldn't.
        """
        wanted = list(getattr(transform, "INPUTS", []) or [])
        if not wanted:
            return {}
        if not manifest.runs:
            return {key: None for key in wanted}
        first_run = manifest.runs[0]
        # Resolve relative → absolute against the manifest's output_dir.
        # Absolute paths pass through unchanged.
        raw = Path(first_run.output_file)
        if not raw.is_absolute() and manifest.output_dir:
            raw = Path(manifest.output_dir) / raw
        # Single input → first run output; multiple inputs → user-supplied
        # transforms need richer wiring (a separate stage on the roadmap).
        return {wanted[0]: raw}

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
