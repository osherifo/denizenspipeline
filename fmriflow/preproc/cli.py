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

    # Container
    run_p.add_argument(
        "--container", type=str, default=None,
        help="Container image (for fmriprep/bids_app backends)",
    )
    run_p.add_argument(
        "--container-type", type=str, default=None,
        choices=["singularity", "docker", "bare"],
    )

    # Mode
    run_p.add_argument(
        "--mode", type=str, default=None,
        choices=["full", "anat_only", "func_only", "func_precomputed_anat"],
        help="Preprocessing mode",
    )
    run_p.add_argument(
        "--anat-only", action="store_true", default=False,
        help="Shortcut for --mode anat_only",
    )
    run_p.add_argument(
        "--fs-no-reconall", action="store_true", default=False,
        help="Shortcut for --mode func_only",
    )

    # Anatomical options
    run_p.add_argument(
        "--skull-strip", type=str, default=None,
        choices=["auto", "force", "skip"],
        help="Skull stripping mode (default: auto)",
    )
    run_p.add_argument("--skull-strip-template", type=str, default=None)
    run_p.add_argument(
        "--no-submm-recon", action="store_true", default=False,
        help="Disable sub-millimeter reconstruction",
    )
    run_p.add_argument(
        "--fs-subjects-dir", type=str, default=None,
        help="Path to existing FreeSurfer subjects directory",
    )
    run_p.add_argument("--fs-license-file", type=str, help="FreeSurfer license")

    # Functional options
    run_p.add_argument(
        "--bold2t1w-init", type=str, default=None,
        choices=["register", "header"],
    )
    run_p.add_argument(
        "--bold2t1w-dof", type=int, default=None,
        choices=[6, 9, 12],
    )
    run_p.add_argument(
        "--dummy-scans", type=int, default=None,
        help="Number of non-steady-state volumes to discard",
    )
    run_p.add_argument(
        "--ignore", type=str, nargs="*", default=None,
        choices=["fieldmaps", "slicetiming", "sbref"],
        help="Corrections to skip",
    )
    run_p.add_argument(
        "--task-id", type=str, default=None,
        help="Filter to specific BIDS task (fmriprep --task-id)",
    )

    # Fieldmaps
    run_p.add_argument(
        "--use-syn-sdc", action="store_true", default=False,
        help="Use fieldmap-less distortion correction (SyN)",
    )
    run_p.add_argument(
        "--force-syn", action="store_true", default=False,
        help="Force SyN SDC even if fieldmaps exist",
    )

    # Output
    run_p.add_argument(
        "--output-spaces", type=str, nargs="*",
        help="Output spaces (e.g. T1w MNI152NLin2009cAsym:res-2)",
    )
    run_p.add_argument(
        "--cifti-output", type=str, default=None,
        choices=["91k", "170k"],
    )

    # Denoising
    run_p.add_argument(
        "--use-aroma", action="store_true", default=False,
        help="Enable ICA-AROMA denoising",
    )
    run_p.add_argument(
        "--aroma-melodic-dim", type=int, default=None,
        help="MELODIC dimensionality for ICA-AROMA (default: -200)",
    )

    # Resources
    run_p.add_argument("--nthreads", type=int, default=None)
    run_p.add_argument("--omp-nthreads", type=int, default=None)
    run_p.add_argument("--mem-mb", type=int, default=None)
    run_p.add_argument(
        "--low-mem", action="store_true", default=False,
        help="Enable low-memory mode",
    )
    run_p.add_argument(
        "--stop-on-first-crash", action="store_true", default=False,
    )

    # Custom backend
    run_p.add_argument(
        "--command", type=str, default=None,
        help="Shell command template (for custom backend)",
    )

    # Escape hatch
    run_p.add_argument(
        "--extra-args", type=str, default=None,
        help="Extra arguments passed directly to the backend, as a quoted string",
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

    backends = list_backends()
    for name in backends:
        backend = get_backend(name)
        if name == "custom":
            print(f"  {name:15s} (always available)")
            continue

        try:
            cfg = PreprocConfig(
                subject="test", backend=name, output_dir="/tmp",
                backend_params={},
            )
            errors = backend.validate(cfg)
            if errors:
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
    from fmriflow.preproc.manifest import PreprocConfig

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

    backend_params: dict = {}

    # Mode: explicit --mode takes precedence, then shortcut flags
    if args.mode:
        backend_params["mode"] = args.mode
    elif args.anat_only:
        backend_params["mode"] = "anat_only"
    elif args.fs_no_reconall:
        backend_params["mode"] = "func_only"

    # Container
    if args.container:
        backend_params["container"] = args.container
    if args.container_type:
        backend_params["container_type"] = args.container_type

    # Anatomical
    if args.skull_strip:
        backend_params["skull_strip"] = args.skull_strip
    if args.skull_strip_template:
        backend_params["skull_strip_template"] = args.skull_strip_template
    if args.no_submm_recon:
        backend_params["no_submm_recon"] = True
    if args.fs_subjects_dir:
        backend_params["fs_subjects_dir"] = args.fs_subjects_dir
    if args.fs_license_file:
        backend_params["fs_license_file"] = args.fs_license_file

    # Functional
    if args.bold2t1w_init:
        backend_params["bold2t1w_init"] = args.bold2t1w_init
    if args.bold2t1w_dof is not None:
        backend_params["bold2t1w_dof"] = args.bold2t1w_dof
    if args.dummy_scans is not None:
        backend_params["dummy_scans"] = args.dummy_scans
    if args.ignore:
        backend_params["ignore"] = args.ignore
    if args.task_id:
        backend_params["task_id"] = args.task_id

    # Fieldmaps
    if args.use_syn_sdc:
        backend_params["use_syn_sdc"] = True
    if args.force_syn:
        backend_params["force_syn"] = True

    # Output
    if args.output_spaces:
        backend_params["output_spaces"] = args.output_spaces
    if args.cifti_output:
        backend_params["cifti_output"] = args.cifti_output

    # Denoising
    if args.use_aroma:
        backend_params["use_aroma"] = True
    if args.aroma_melodic_dim is not None:
        backend_params["aroma_melodic_dim"] = args.aroma_melodic_dim

    # Resources
    if args.nthreads is not None:
        backend_params["nthreads"] = args.nthreads
    if args.omp_nthreads is not None:
        backend_params["omp_nthreads"] = args.omp_nthreads
    if args.mem_mb is not None:
        backend_params["mem_mb"] = args.mem_mb
    if args.low_mem:
        backend_params["low_mem"] = True
    if args.stop_on_first_crash:
        backend_params["stop_on_first_crash"] = True

    # Custom backend
    if args.command:
        backend_params["command"] = args.command

    # Escape hatch
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
