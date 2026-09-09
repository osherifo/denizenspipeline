"""Identity — the minimal nipype workflow.

Does not actually run nipype. Validates and emits a manifest whose
``runs`` list is empty (or a single placeholder). Its purpose is
two-fold:

1. **Smoke test for the registry + Protocol contract.** Exercises
   ``@register_preproc_workflow`` end-to-end without depending on
   FSL / ANTs / nipype actually being installed.
2. **A reference example.** Anyone writing their own workflow can
   copy this file as a starting point — the class shape is the
   contract, even when the body is a no-op.

The real ``reference`` workflow (MCFLIRT + BET + BBR + ANTs SyN +
confounds) lives in a separate file and depends on nipype + FSL +
ANTs being present.
"""

from __future__ import annotations

from typing import Any

from fmriflow.preproc.manifest import PreprocManifest, now_iso
from fmriflow.preproc.workflow_registry import register_preproc_workflow


@register_preproc_workflow("identity")
class IdentityWorkflow:
    """No-op workflow that emits an empty manifest.

    Useful for testing the stack contract without a real
    preprocessing run. Don't use this in production — the manifest
    it emits has no runs, so the analysis stage will reject it.
    """
    _NODE_REGISTRY_SKIP = True  # superseded by the identity / derivatives_source nodes

    name = "identity"
    version = "0.1.0"
    description = (
        "No-op workflow that emits an empty manifest. For testing "
        "the registry + stack contract without running real preproc."
    )

    PARAM_SCHEMA: dict = {}
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def validate(self, config: Any) -> list[str]:
        return []

    def build(self, config: Any) -> Any:
        # No real nipype work — return a sentinel the stack runner
        # can recognise as "nothing to execute."
        return None

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]) -> PreprocManifest:
        subject = getattr(config, "subject", "unknown")
        return PreprocManifest(
            subject=subject,
            # ``StackRunConfig`` carries the dataset / run-group label
            # under ``dataset`` (default "unknown"); ``task`` is a
            # separate optional BIDS task filter and must not be used
            # here — it would mislabel manifests for any code that
            # queries ``manifest.dataset``.
            dataset=getattr(config, "dataset", None) or "unknown",
            sessions=getattr(config, "sessions", None) or [],
            runs=[],
            backend="nipype",
            backend_version=self.version,
            parameters={"workflow": self.name},
            space="native",
            additional_steps=[],
            output_dir=str(getattr(config, "output_dir", "")),
            created=now_iso(),
        )
