"""Manifest validation — checks that preprocessing outputs are complete and
compatible with an analysis config."""

from __future__ import annotations

import logging
from pathlib import Path

from denizenspipeline.preproc.manifest import PreprocManifest

logger = logging.getLogger(__name__)


def validate_manifest(
    manifest: PreprocManifest,
    config: dict | None = None,
) -> list[str]:
    """Validate a preprocessing manifest.

    Parameters
    ----------
    manifest
        The manifest to validate.
    config
        Optional analysis config dict.  If provided, also checks that
        the manifest is compatible with the analysis requirements
        (required runs, expected space, etc.).

    Returns
    -------
    List of error/warning strings.  Strings starting with ``"Warning:"``
    are non-fatal.  An empty list means the manifest is valid.
    """
    errors: list[str] = []

    # ── Basic integrity checks ───────────────────────────────────
    if not manifest.subject:
        errors.append("Manifest has no subject.")

    if not manifest.backend:
        errors.append("Manifest has no backend.")

    if not manifest.runs:
        errors.append("Manifest has no runs.")
        return errors  # nothing else to check

    # ── Output file existence ────────────────────────────────────
    output_dir = Path(manifest.output_dir) if manifest.output_dir else None

    for run in manifest.runs:
        if not run.output_file:
            errors.append(f"Run '{run.run_name}' has no output_file.")
            continue

        if output_dir:
            output_path = output_dir / run.output_file
            if not output_path.exists():
                errors.append(f"Output file not found: {output_path}")

    # ── TR/shape consistency ─────────────────────────────────────
    for run in manifest.runs:
        if run.shape:
            expected_trs = run.shape[-1] if len(run.shape) == 4 else run.shape[0]
            if run.n_trs != expected_trs:
                errors.append(
                    f"Run '{run.run_name}': n_trs={run.n_trs} does not match "
                    f"shape {run.shape} (expected {expected_trs})."
                )

    # ── QC checks (warnings) ────────────────────────────────────
    for run in manifest.runs:
        if run.qc and run.qc.mean_fd is not None and run.qc.mean_fd > 0.5:
            errors.append(
                f"Warning: run '{run.run_name}' has high mean FD "
                f"({run.qc.mean_fd:.2f}mm). Consider excluding or scrubbing."
            )

    # ── Config compatibility checks ──────────────────────────────
    if config is not None:
        _validate_against_config(manifest, config, errors)

    return errors


def _validate_against_config(
    manifest: PreprocManifest,
    config: dict,
    errors: list[str],
) -> None:
    """Check that a manifest is compatible with an analysis config."""

    # Check required runs
    required_runs = _get_required_runs(config)
    if required_runs:
        manifest_runs = {r.run_name for r in manifest.runs}
        missing = required_runs - manifest_runs
        if missing:
            errors.append(
                f"Runs missing from preprocessing: {sorted(missing)}"
            )

    # Check confounds file existence if config expects confound regression
    resp_cfg = config.get("response", {})
    if resp_cfg.get("confounds"):
        output_dir = Path(manifest.output_dir) if manifest.output_dir else None
        for run in manifest.runs:
            if not run.confounds_file:
                errors.append(
                    f"Warning: run '{run.run_name}' has no confounds file, "
                    f"but analysis config requests confound regression."
                )
            elif output_dir:
                cf_path = output_dir / run.confounds_file
                if not cf_path.exists():
                    errors.append(
                        f"Confounds file not found: {cf_path}"
                    )


def _get_required_runs(config: dict) -> set[str]:
    """Extract the set of run names required by an analysis config."""
    runs: set[str] = set()

    # Check preprocessing.test_run + all runs referenced in features
    preproc_cfg = config.get("preprocessing", {})
    test_run = preproc_cfg.get("test_run")
    if test_run:
        runs.add(test_run)

    # Check stimuli section for run names
    stim_cfg = config.get("stimulus", {})
    stim_runs = stim_cfg.get("runs", [])
    if isinstance(stim_runs, list):
        runs.update(stim_runs)

    return runs
