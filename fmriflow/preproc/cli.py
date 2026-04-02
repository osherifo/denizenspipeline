"""CLI subcommands for ``fmriflow preproc``.

Commands:
    fmriflow preproc run      — run preprocessing via a backend
    fmriflow preproc collect   — build manifest from existing outputs
    fmriflow preproc validate  — validate a manifest (optionally against a config)
    fmriflow preproc info      — display manifest details
    fmriflow preproc doctor    — check backend availability
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logger = logging.getLogger(__name__)


def add_preproc_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``fmriflow preproc`` and its sub-subcommands."""
    preproc_parser = subparsers.add_parser(
        "preproc", help="fMRI preprocessing tools",
    )
    preproc_subs = preproc_parser.add_subparsers(dest="preproc_command")

    # ── run ──
    run_p = preproc_subs.add_parser(
        "run", help="Run preprocessing via a backend",
    )
    run_p.add_argument(
        "--config", type=str, default=None,
        help="Path to a YAML config with a preproc: section",
    )
    run_p.add_argument("--backend", type=str, help="Backend name")
    run_p.add_argument("--bids-dir", type=str, help="BIDS dataset root")
    run_p.add_argument("--raw-dir", type=str, help="Raw data directory")
    run_p.add_argument("--output-dir", type=str, help="Output directory")
    run_p.add_argument("--work-dir", type=str, help="Work directory")
    run_p.add_argument("--subject", type=str, help="Subject ID")
    run_p.add_argument("--task", type=str, help="BIDS task label")
    run_p.add_argument("--sessions", type=str, nargs="*", help="Session labels")
    run_p.add_argument(
        "--run-map", type=str, default=None,
        help='JSON dict mapping backend run names to pipeline run names',
    )
    run_p.add_argument(
        "--command", type=str, default=None,
        help="Shell command template (for custom backend)",
    )
    run_p.add_argument(
        "--container", type=str, default=None,
        help="Container image (for fmriprep/bids_app backends)",
    )
    run_p.add_argument(
        "--container-type", type=str, default="singularity",
        choices=["singularity", "docker", "bare"],
    )
    run_p.add_argument("--fs-license-file", type=str, help="FreeSurfer license")
    run_p.add_argument(
        "--output-spaces", type=str, nargs="*",
        help="Output spaces (for fmriprep)",
    )
    run_p.add_argument(
        "--extra-args", type=str, default=None,
        help="Extra arguments passed directly to the backend, as a quoted string (e.g. '--fs-no-reconall --low-mem')",
    )

    # ── collect ──
    collect_p = preproc_subs.add_parser(
        "collect", help="Build manifest from existing outputs",
    )
    collect_p.add_argument("--backend", type=str, required=True)
    collect_p.add_argument("--output-dir", type=str, required=True)
    collect_p.add_argument("--subject", type=str, required=True)
    collect_p.add_argument("--task", type=str, default=None)
    collect_p.add_argument("--sessions", type=str, nargs="*")
    collect_p.add_argument("--bids-dir", type=str, default=None)
    collect_p.add_argument(
        "--run-map", type=str, default=None,
        help='JSON dict mapping backend run names to pipeline run names',
    )
    collect_p.add_argument("--file-pattern", type=str, default=None)

    # ── validate ──
    validate_p = preproc_subs.add_parser(
        "validate", help="Validate a preprocessing manifest",
    )
    validate_p.add_argument("manifest", help="Path to preproc_manifest.json")
    validate_p.add_argument(
        "--for-config", type=str, default=None,
        help="Also validate compatibility with this analysis config",
    )

    # ── info ──
    info_p = preproc_subs.add_parser(
        "info", help="Display manifest details",
    )
    info_p.add_argument("manifest", help="Path to preproc_manifest.json")

    # ── doctor ──
    preproc_subs.add_parser(
        "doctor", help="Check backend availability",
    )


def dispatch_preproc(args) -> int:
    """Dispatch to the appropriate preproc subcommand."""
    cmd = getattr(args, "preproc_command", None)
    if cmd == "run":
        return _preproc_run(args)
    elif cmd == "collect":
        return _preproc_collect(args)
    elif cmd == "validate":
        return _preproc_validate(args)
    elif cmd == "info":
        return _preproc_info(args)
    elif cmd == "doctor":
        return _preproc_doctor(args)
    else:
        print("Usage: fmriflow preproc {run|collect|validate|info|doctor}")
        return 1


# ── Subcommand implementations ──────────────────────────────────────────

def _preproc_run(args) -> int:
    from fmriflow.preproc.manifest import PreprocConfig, ConfoundsConfig
    from fmriflow.preproc.runner import run_preprocessing

    config = _build_config_from_args(args)
    if config is None:
        return 1

    try:
        manifest = run_preprocessing(config)
        print(f"\nPreprocessing complete.")
        print(f"  Subject:  {manifest.subject}")
        print(f"  Backend:  {manifest.backend} {manifest.backend_version}")
        print(f"  Runs:     {len(manifest.runs)}")
        print(f"  Manifest: {manifest.output_dir}/sub-{manifest.subject}/preproc_manifest.json")
        return 0
    except Exception as e:
        print(f"\nPreprocessing failed: {e}", file=sys.stderr)
        logger.error("Preprocessing failed", exc_info=True)
        return 1


def _preproc_collect(args) -> int:
    from fmriflow.preproc.manifest import PreprocConfig
    from fmriflow.preproc.runner import collect_outputs

    run_map = json.loads(args.run_map) if args.run_map else None
    backend_params = {}
    if args.file_pattern:
        backend_params["file_pattern"] = args.file_pattern

    config = PreprocConfig(
        subject=args.subject,
        backend=args.backend,
        output_dir=args.output_dir,
        bids_dir=args.bids_dir,
        task=args.task,
        sessions=args.sessions,
        run_map=run_map,
        backend_params=backend_params,
    )

    try:
        manifest = collect_outputs(config)
        print(f"\nManifest created.")
        print(f"  Subject:  {manifest.subject}")
        print(f"  Backend:  {manifest.backend} {manifest.backend_version}")
        print(f"  Runs:     {len(manifest.runs)}")
        for run in manifest.runs:
            qc_str = ""
            if run.qc and run.qc.mean_fd is not None:
                qc_str = f"  FD={run.qc.mean_fd:.2f}"
            print(f"    {run.run_name:30s} {run.n_trs:4d} TRs  {run.shape}{qc_str}")
        return 0
    except Exception as e:
        print(f"\nCollect failed: {e}", file=sys.stderr)
        logger.error("Collect failed", exc_info=True)
        return 1


def _preproc_validate(args) -> int:
    from fmriflow.preproc.manifest import PreprocManifest
    from fmriflow.preproc.validation import validate_manifest

    try:
        manifest = PreprocManifest.from_json(args.manifest)
    except Exception as e:
        print(f"Cannot load manifest: {e}", file=sys.stderr)
        return 1

    config = None
    if args.for_config:
        from fmriflow.config.loader import load_config
        try:
            config = load_config(args.for_config)
        except Exception as e:
            print(f"Cannot load config: {e}", file=sys.stderr)
            return 1

    print(f"\nManifest: {manifest.subject}, {manifest.backend} {manifest.backend_version}")
    print(f"Space: {manifest.space}, Format: {manifest.output_format}")
    print(f"Runs: {len(manifest.runs)}")

    errors = validate_manifest(manifest, config)
    warnings = [e for e in errors if e.startswith("Warning:")]
    hard_errors = [e for e in errors if not e.startswith("Warning:")]

    for w in warnings:
        print(f"  {w}")

    if hard_errors:
        for e in hard_errors:
            print(f"  ERROR: {e}")
        return 1

    if config:
        print(f"\nCompatibility with {args.for_config}: OK")

    print("\nAll checks passed.")
    return 0


def _preproc_info(args) -> int:
    from fmriflow.preproc.manifest import PreprocManifest

    try:
        manifest = PreprocManifest.from_json(args.manifest)
    except Exception as e:
        print(f"Cannot load manifest: {e}", file=sys.stderr)
        return 1

    print(f"\n{'Subject:':<16}{manifest.subject}")
    print(f"{'Dataset:':<16}{manifest.dataset}")
    print(f"{'Backend:':<16}{manifest.backend} {manifest.backend_version}")
    print(f"{'Space:':<16}{manifest.space} ({manifest.resolution or 'native'})")
    if manifest.confounds_applied:
        print(f"{'Confounds:':<16}{', '.join(manifest.confounds_applied)}")
    if manifest.additional_steps:
        print(f"{'Steps:':<16}{', '.join(manifest.additional_steps)}")
    print(f"{'Format:':<16}{manifest.output_format}")
    print(f"{'Created:':<16}{manifest.created}")
    print(f"{'Runs:':<16}{len(manifest.runs)}")

    for run in manifest.runs:
        qc_parts = []
        if run.qc:
            if run.qc.mean_fd is not None:
                qc_parts.append(f"FD={run.qc.mean_fd:.2f}")
            if run.qc.tsnr_median is not None:
                qc_parts.append(f"tSNR={run.qc.tsnr_median:.1f}")
        qc_str = f"  {' '.join(qc_parts)}" if qc_parts else ""
        print(f"  {run.run_name:30s} {run.n_trs:4d} TRs  {run.shape}{qc_str}")

    return 0


def _preproc_doctor(args) -> int:
    from fmriflow.preproc.backends import list_backends, get_backend
    from fmriflow.preproc.manifest import PreprocConfig

    print("\nBackend availability:\n")

    # Create a minimal config for checking
    dummy_config = PreprocConfig(
        subject="test", backend="custom", output_dir="/tmp",
    )

    backends = list_backends()
    for name in backends:
        backend = get_backend(name)
        if name == "custom":
            print(f"  {name:15s} (always available)")
            continue

        # Run validate with empty config to see what's missing
        try:
            cfg = PreprocConfig(
                subject="test", backend=name, output_dir="/tmp",
                backend_params={},
            )
            errors = backend.validate(cfg)
            if errors:
                # Check if it's just missing config vs missing tool
                tool_errors = [
                    e for e in errors
                    if "not found" in e.lower() or "not installed" in e.lower()
                ]
                if tool_errors:
                    print(f"  {name:15s} NOT AVAILABLE — {tool_errors[0]}")
                else:
                    print(f"  {name:15s} available (config needed)")
            else:
                print(f"  {name:15s} OK")
        except Exception as e:
            print(f"  {name:15s} ERROR — {e}")

    return 0


# ── Config building ──────────────────────────────────────────────────────

def _build_config_from_args(args) -> "PreprocConfig | None":
    """Build a PreprocConfig from CLI args or a YAML config file."""
    from fmriflow.preproc.manifest import PreprocConfig, ConfoundsConfig

    if args.config:
        return _load_preproc_config(args.config)

    if not args.backend:
        print("Error: --backend is required (or use --config).", file=sys.stderr)
        return None
    if not args.subject:
        print("Error: --subject is required.", file=sys.stderr)
        return None
    if not args.output_dir:
        print("Error: --output-dir is required.", file=sys.stderr)
        return None

    run_map = json.loads(args.run_map) if args.run_map else None

    backend_params = {}
    if args.command:
        backend_params["command"] = args.command
    if args.container:
        backend_params["container"] = args.container
        backend_params["container_type"] = args.container_type
    if args.fs_license_file:
        backend_params["fs_license_file"] = args.fs_license_file
    if args.output_spaces:
        backend_params["output_spaces"] = args.output_spaces
    if args.extra_args:
        backend_params["extra_args"] = args.extra_args.split()

    return PreprocConfig(
        subject=args.subject,
        backend=args.backend,
        output_dir=args.output_dir,
        bids_dir=args.bids_dir,
        raw_dir=args.raw_dir,
        work_dir=args.work_dir,
        task=args.task,
        sessions=args.sessions,
        run_map=run_map,
        backend_params=backend_params,
    )


def _load_preproc_config(yaml_path: str) -> "PreprocConfig | None":
    """Load a PreprocConfig from a YAML file's ``preproc:`` section."""
    from pathlib import Path
    import yaml

    path = Path(yaml_path)
    if not path.exists():
        print(f"Config file not found: {path}", file=sys.stderr)
        return None

    with open(path) as f:
        data = yaml.safe_load(f)

    preproc_section = data.get("preproc")
    if not preproc_section:
        print(f"No 'preproc:' section found in {path}", file=sys.stderr)
        return None

    from fmriflow.preproc.manifest import PreprocConfig
    return PreprocConfig.from_dict(preproc_section)
