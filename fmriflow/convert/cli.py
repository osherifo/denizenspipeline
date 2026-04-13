"""CLI subcommands for ``fmriflow convert``.

Commands:
    fmriflow convert run        — run DICOM-to-BIDS conversion via heudiconv
    fmriflow convert collect     — build manifest from existing BIDS dataset
    fmriflow convert validate    — validate a conversion manifest
    fmriflow convert scan        — list DICOM series in a directory
    fmriflow convert dry-run     — preview conversion mapping
    fmriflow convert batch       — run batch conversion from YAML config
    fmriflow convert heuristics  — manage heuristic registry
    fmriflow convert doctor      — check tool availability
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def add_convert_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``fmriflow convert`` and its sub-subcommands."""
    convert_parser = subparsers.add_parser(
        "convert", help="DICOM-to-BIDS conversion tools",
    )
    convert_subs = convert_parser.add_subparsers(dest="convert_command")

    # ── run ──
    run_p = convert_subs.add_parser(
        "run", help="Run DICOM-to-BIDS conversion via heudiconv",
    )
    run_p.add_argument("--source-dir", type=str, required=True,
                       help="Directory containing DICOMs")
    run_p.add_argument("--bids-dir", type=str, required=True,
                       help="Output BIDS dataset root")
    run_p.add_argument("--subject", type=str, required=True,
                       help="Subject ID")
    run_p.add_argument("--heuristic", type=str, required=True,
                       help="Heuristic name (from registry) or file path")
    run_p.add_argument("--sessions", type=str, nargs="*",
                       help="Session labels")
    run_p.add_argument("--dataset-name", type=str, default=None,
                       help="Dataset name for dataset_description.json")
    run_p.add_argument("--grouping", type=str, default=None,
                       help="Heudiconv grouping strategy")
    run_p.add_argument("--minmeta", action="store_true",
                       help="Minimize metadata in sidecars")
    run_p.add_argument("--no-overwrite", action="store_true",
                       help="Do not overwrite existing outputs")
    run_p.add_argument("--no-validate", action="store_true",
                       help="Skip BIDS validation after conversion")

    # ── collect ──
    collect_p = convert_subs.add_parser(
        "collect", help="Build manifest from existing BIDS dataset",
    )
    collect_p.add_argument("--bids-dir", type=str, required=True)
    collect_p.add_argument("--subject", type=str, required=True)
    collect_p.add_argument("--source-dir", type=str, default="")
    collect_p.add_argument("--heuristic", type=str, default=None)
    collect_p.add_argument("--sessions", type=str, nargs="*")
    collect_p.add_argument("--dataset-name", type=str, default=None)

    # ── validate ──
    validate_p = convert_subs.add_parser(
        "validate", help="Validate a conversion manifest",
    )
    validate_p.add_argument("manifest", help="Path to convert_manifest.json")
    validate_p.add_argument("--for-config", type=str, default=None,
                            help="Also validate against this analysis config")

    # ── scan ──
    scan_p = convert_subs.add_parser(
        "scan", help="List DICOM series in a directory",
    )
    scan_p.add_argument("source_dir", help="Directory containing DICOMs")

    # ── dry-run ──
    dryrun_p = convert_subs.add_parser(
        "dry-run", help="Preview conversion mapping without running",
    )
    dryrun_p.add_argument("--source-dir", type=str, required=True)
    dryrun_p.add_argument("--subject", type=str, required=True)
    dryrun_p.add_argument("--heuristic", type=str, required=True)

    # ── batch ──
    batch_p = convert_subs.add_parser(
        "batch", help="Run batch conversion from YAML config",
    )
    batch_p.add_argument("--config", type=str, required=True,
                         help="Path to batch YAML config file")
    batch_p.add_argument("--parallel", type=int, default=None,
                         help="Override max_workers from config")
    batch_p.add_argument("--dry-run", action="store_true", dest="batch_dry_run",
                         help="Print job table without running")

    # ── heuristics ──
    heur_p = convert_subs.add_parser(
        "heuristics", help="Manage heuristic registry",
    )
    heur_subs = heur_p.add_subparsers(dest="heuristics_command")

    # heuristics list (default)
    heur_subs.add_parser("list", help="List registered heuristics")

    # heuristics add
    heur_add = heur_subs.add_parser("add", help="Register a new heuristic")
    heur_add.add_argument("path", help="Path to the heuristic file")
    heur_add.add_argument("--name", type=str, default=None)
    heur_add.add_argument("--scanner-pattern", type=str, default=None)
    heur_add.add_argument("--description", type=str, default=None)
    heur_add.add_argument("--site", type=str, default=None)
    heur_add.add_argument("--author", type=str, default=None)
    heur_add.add_argument("--version", type=str, default=None)
    heur_add.add_argument("--tasks", type=str, nargs="*", default=None)

    # heuristics info
    heur_info = heur_subs.add_parser("info", help="Show heuristic details")
    heur_info.add_argument("name", help="Heuristic name")
    heur_info.add_argument("--code", action="store_true",
                           help="Print the heuristic Python source code")

    # heuristics create
    heur_create = heur_subs.add_parser(
        "create", help="Create a new heuristic from template",
    )
    heur_create.add_argument("name", help="Name for the new heuristic")
    heur_create.add_argument("--description", type=str, default=None)
    heur_create.add_argument("--scanner-pattern", type=str, default=None)
    heur_create.add_argument("--site", type=str, default=None)
    heur_create.add_argument("--author", type=str, default=None)
    heur_create.add_argument("--version", type=str, default=None)
    heur_create.add_argument("--tasks", type=str, nargs="*", default=None)

    # heuristics remove
    heur_rm = heur_subs.add_parser("remove", help="Remove a heuristic")
    heur_rm.add_argument("name", help="Heuristic name")

    # ── doctor ──
    convert_subs.add_parser(
        "doctor", help="Check tool availability",
    )


def dispatch_convert(args) -> int:
    """Dispatch to the appropriate convert subcommand."""
    cmd = getattr(args, "convert_command", None)
    if cmd == "run":
        return _convert_run(args)
    elif cmd == "collect":
        return _convert_collect(args)
    elif cmd == "validate":
        return _convert_validate(args)
    elif cmd == "scan":
        return _convert_scan(args)
    elif cmd == "dry-run":
        return _convert_dry_run(args)
    elif cmd == "batch":
        return _convert_batch(args)
    elif cmd == "heuristics":
        return _convert_heuristics(args)
    elif cmd == "doctor":
        return _convert_doctor(args)
    else:
        print("Usage: fmriflow convert {run|collect|validate|scan|dry-run|batch|heuristics|doctor}")
        return 1


# ── Subcommand implementations ──────────────────────────────────────────

def _convert_run(args) -> int:
    from fmriflow.convert.manifest import ConvertConfig
    from fmriflow.convert.runner import run_conversion

    config = ConvertConfig(
        source_dir=args.source_dir,
        subject=args.subject,
        bids_dir=args.bids_dir,
        heuristic=args.heuristic,
        sessions=args.sessions,
        dataset_name=args.dataset_name,
        grouping=args.grouping,
        minmeta=args.minmeta,
        overwrite=not args.no_overwrite,
        validate_bids=not args.no_validate,
    )

    try:
        manifest = run_conversion(config)
        print(f"\nConversion complete.")
        print(f"  Subject:    {manifest.subject}")
        print(f"  Heudiconv:  {manifest.heudiconv_version}")
        print(f"  BIDS dir:   {manifest.bids_dir}")
        print(f"  Runs:       {len(manifest.runs)}")
        for run in manifest.runs:
            tr_str = f"  TR={run.tr}s" if run.tr else ""
            print(f"    {run.modality:6s} {run.output_file}{tr_str}")
        if manifest.bids_valid is not None:
            status = "PASSED" if manifest.bids_valid else "FAILED"
            print(f"  BIDS valid: {status}")
            for e in manifest.bids_errors:
                print(f"    ERROR: {e}")
            for w in manifest.bids_warnings:
                print(f"    WARNING: {w}")
        return 0
    except Exception as e:
        print(f"\nConversion failed: {e}", file=sys.stderr)
        logger.error("Conversion failed", exc_info=True)
        return 1


def _convert_collect(args) -> int:
    from fmriflow.convert.manifest import ConvertConfig
    from fmriflow.convert.runner import collect_bids, MANIFEST_FILENAME
    from pathlib import Path

    config = ConvertConfig(
        source_dir=args.source_dir or "",
        subject=args.subject,
        bids_dir=args.bids_dir,
        heuristic=args.heuristic or "",
        sessions=args.sessions,
        dataset_name=args.dataset_name,
    )

    try:
        manifest = collect_bids(config)
        manifest_path = Path(config.bids_dir) / MANIFEST_FILENAME
        manifest.save(manifest_path)

        print(f"\nManifest created.")
        print(f"  Subject:  {manifest.subject}")
        print(f"  Runs:     {len(manifest.runs)}")
        for run in manifest.runs:
            tr_str = f"  TR={run.tr}s" if run.tr else ""
            print(f"    {run.modality:6s} {run.output_file}{tr_str}")
        print(f"  Manifest: {manifest_path}")
        return 0
    except Exception as e:
        print(f"\nCollect failed: {e}", file=sys.stderr)
        logger.error("Collect failed", exc_info=True)
        return 1


def _convert_validate(args) -> int:
    from fmriflow.convert.manifest import ConvertManifest
    from fmriflow.convert.validation import validate_manifest

    try:
        manifest = ConvertManifest.from_json(args.manifest)
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

    print(f"\nManifest: sub-{manifest.subject}, heudiconv {manifest.heudiconv_version}")
    print(f"BIDS dir: {manifest.bids_dir}")
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


def _convert_scan(args) -> int:
    from fmriflow.convert.dicom_utils import extract_scanner_info, list_series

    source_dir = args.source_dir

    print(f"\nSource: {source_dir}")

    scanner = extract_scanner_info(source_dir)
    if scanner:
        parts = []
        if scanner.manufacturer:
            parts.append(scanner.manufacturer)
        if scanner.model:
            parts.append(scanner.model)
        if scanner.field_strength:
            parts.append(f"({scanner.field_strength}T)")
        if scanner.software_version:
            parts.append(f"— {scanner.software_version}")
        if parts:
            print(f"Scanner: {' '.join(parts)}")
        if scanner.institution:
            print(f"Institution: {scanner.institution}")
    else:
        print("Scanner: (could not extract — pydicom installed?)")

    series = list_series(source_dir)
    if series:
        print(f"\nSeries:")
        for s in series:
            print(f"  {s.number:03d}  {s.description:40s} {s.n_images:5d} images  {s.modality_guess}")
    else:
        print("\nNo DICOM series found.")

    # Check for matching heuristics
    if scanner:
        from fmriflow.convert.heuristics import match_heuristic
        match = match_heuristic(scanner)
        if match:
            version = f" (v{match.version})" if match.version else ""
            print(f"\nMatching heuristic: {match.name}{version}")

    return 0


def _convert_dry_run(args) -> int:
    from fmriflow.convert.manifest import ConvertConfig
    from fmriflow.convert.runner import dry_run

    config = ConvertConfig(
        source_dir=args.source_dir,
        subject=args.subject,
        bids_dir="",
        heuristic=args.heuristic,
    )

    try:
        output = dry_run(config)
        print(output)
        return 0
    except Exception as e:
        print(f"\nDry run failed: {e}", file=sys.stderr)
        return 1


def _convert_batch(args) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path
    from fmriflow.convert.batch import parse_batch_yaml
    from fmriflow.convert.manifest import ConvertConfig
    from fmriflow.convert.runner import run_conversion
    import time

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        batch_config = parse_batch_yaml(config_path.read_text())
    except Exception as e:
        print(f"Failed to parse batch config: {e}", file=sys.stderr)
        return 1

    if args.parallel is not None:
        batch_config.max_workers = args.parallel

    # Print job table
    print(f"\nBatch conversion: {len(batch_config.jobs)} jobs")
    print(f"  Heuristic:   {batch_config.heuristic}")
    print(f"  BIDS dir:    {batch_config.bids_dir}")
    if batch_config.source_root:
        print(f"  Source root: {batch_config.source_root}")
    print(f"  Workers:     {batch_config.max_workers}")
    print()
    print(f"  {'#':<4s} {'Subject':<12s} {'Session':<10s} {'Source Dir'}")
    print(f"  {'-'*4} {'-'*12} {'-'*10} {'-'*40}")
    for i, job in enumerate(batch_config.jobs, 1):
        print(f"  {i:<4d} {job.subject:<12s} {job.session or '-':<10s} {job.source_dir}")
    print()

    if args.batch_dry_run:
        print("Dry run — no conversions executed.")
        return 0

    # Execute
    results: dict[int, dict] = {}
    start_time = time.time()

    max_workers = min(batch_config.max_workers, len(batch_config.jobs))

    def run_job(idx: int, job):
        params = batch_config.to_convert_params(job)
        config = ConvertConfig(
            source_dir=params["source_dir"],
            subject=params["subject"],
            bids_dir=params["bids_dir"],
            heuristic=params["heuristic"],
            sessions=params.get("sessions"),
            dataset_name=params.get("dataset_name"),
            grouping=params.get("grouping"),
            minmeta=params.get("minmeta", False),
            overwrite=params.get("overwrite", True),
            validate_bids=params.get("validate_bids", True),
        )
        job_start = time.time()
        try:
            manifest = run_conversion(config)
            return {
                "status": "done",
                "n_runs": len(manifest.runs),
                "elapsed": time.time() - job_start,
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "elapsed": time.time() - job_start,
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for i, job in enumerate(batch_config.jobs):
            futures[executor.submit(run_job, i, job)] = i

        for future in as_completed(futures):
            idx = futures[future]
            job = batch_config.jobs[idx]
            result = future.result()
            results[idx] = result
            status_icon = "OK" if result["status"] == "done" else "FAIL"
            elapsed = f"{result['elapsed']:.1f}s"
            print(f"  [{status_icon}] sub-{job.subject}"
                  f"{f' ses-{job.session}' if job.session else ''}"
                  f"  {elapsed}"
                  f"{'  ' + result.get('error', '') if result['status'] == 'failed' else ''}")

    total_elapsed = time.time() - start_time
    n_done = sum(1 for r in results.values() if r["status"] == "done")
    n_failed = sum(1 for r in results.values() if r["status"] == "failed")

    print(f"\nBatch complete: {n_done} succeeded, {n_failed} failed, {total_elapsed:.1f}s total")
    return 1 if n_failed > 0 else 0


def _convert_heuristics(args) -> int:
    from fmriflow.convert.heuristics import (
        list_heuristics, register_heuristic, remove_heuristic, _load_heuristic_info,
        get_heuristic, read_heuristic_source, get_heuristic_template,
        save_heuristic_code,
    )

    heur_cmd = getattr(args, "heuristics_command", None)

    if heur_cmd is None or heur_cmd == "list":
        heuristics = list_heuristics()
        if not heuristics:
            print("\nNo heuristics registered.")
            print("Register one with: fmriflow convert heuristics add <path>")
            return 0

        print(f"\n{'Name':<25s} {'Scanner':<25s} {'Tasks'}")
        print("-" * 70)
        for h in heuristics:
            tasks = ", ".join(h.tasks) if h.tasks else ""
            scanner = h.scanner_pattern or "*"
            print(f"  {h.name:<23s} {scanner:<25s} {tasks}")
        return 0

    elif heur_cmd == "add":
        kwargs = {}
        if args.site:
            kwargs["site"] = args.site
        if args.author:
            kwargs["author"] = args.author
        if args.version:
            kwargs["version"] = args.version
        if args.tasks:
            kwargs["tasks"] = args.tasks

        try:
            info = register_heuristic(
                args.path,
                name=args.name,
                scanner_pattern=args.scanner_pattern,
                description=args.description,
                **kwargs,
            )
            print(f"\nRegistered heuristic: {info.name}")
            print(f"  Path: {info.path}")
            return 0
        except Exception as e:
            print(f"\nFailed to register: {e}", file=sys.stderr)
            return 1

    elif heur_cmd == "info":
        try:
            path = get_heuristic(args.name)
            info = _load_heuristic_info(path)
            print(f"\n{'Name:':<16}{info.name}")
            print(f"{'Path:':<16}{info.path}")
            if info.description:
                print(f"{'Description:':<16}{info.description}")
            if info.scanner_pattern:
                print(f"{'Scanner:':<16}{info.scanner_pattern}")
            if info.site:
                print(f"{'Site:':<16}{info.site}")
            if info.author:
                print(f"{'Author:':<16}{info.author}")
            if info.version:
                print(f"{'Version:':<16}{info.version}")
            if info.tasks:
                print(f"{'Tasks:':<16}{', '.join(info.tasks)}")
            if info.notes:
                print(f"{'Notes:':<16}{info.notes}")
            if getattr(args, "code", False):
                code = read_heuristic_source(args.name)
                print(f"\n{'─' * 60}")
                print(code)
            return 0
        except Exception as e:
            print(f"\n{e}", file=sys.stderr)
            return 1

    elif heur_cmd == "create":
        try:
            try:
                existing_path = get_heuristic(args.name)
            except Exception:
                existing_path = None

            if existing_path is not None:
                raise FileExistsError(
                    f"Heuristic '{args.name}' already exists at {existing_path}. "
                    "Refusing to overwrite an existing heuristic with 'create'."
                )
            code = get_heuristic_template(name=args.name)
            info = save_heuristic_code(args.name, code)

            # Write sidecar with metadata
            import yaml
            sidecar_data: dict = {"name": args.name}
            if args.description:
                sidecar_data["description"] = args.description
            if args.scanner_pattern:
                sidecar_data["scanner_pattern"] = args.scanner_pattern
            if args.tasks:
                sidecar_data["tasks"] = args.tasks
            if getattr(args, "site", None):
                sidecar_data["site"] = args.site
            if getattr(args, "author", None):
                sidecar_data["author"] = args.author
            if getattr(args, "version", None):
                sidecar_data["version"] = args.version

            sidecar_path = info.path.with_suffix(".yaml")
            sidecar_path.write_text(yaml.dump(sidecar_data, default_flow_style=False))

            print(f"\nCreated heuristic: {info.name}")
            print(f"  Path: {info.path}")
            print(f"\nEdit the file to customize classification and BIDS mapping logic.")
            return 0
        except Exception as e:
            print(f"\nFailed to create heuristic: {e}", file=sys.stderr)
            return 1

    elif heur_cmd == "remove":
        try:
            remove_heuristic(args.name)
            print(f"\nRemoved heuristic: {args.name}")
            return 0
        except Exception as e:
            print(f"\n{e}", file=sys.stderr)
            return 1

    else:
        print("Usage: fmriflow convert heuristics {list|add|create|info|remove}")
        return 1


def _convert_doctor(args) -> int:
    import shutil

    print("\nTool availability:\n")

    # heudiconv
    heudiconv_path = shutil.which("heudiconv")
    if heudiconv_path:
        from fmriflow.convert.runner import _get_heudiconv_version
        version = _get_heudiconv_version()
        print(f"  {'heudiconv:':<20s} v{version}  OK")
    else:
        print(f"  {'heudiconv:':<20s} NOT FOUND — pip install heudiconv")

    # dcm2niix (runtime dependency of heudiconv)
    dcm2niix_path = shutil.which("dcm2niix")
    if dcm2niix_path:
        try:
            import subprocess
            result = subprocess.run(
                ["dcm2niix", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            version = (result.stdout.strip().split("\n")[0] or
                       result.stderr.strip().split("\n")[0] or "unknown")
            print(f"  {'dcm2niix:':<20s} {version}  OK (used by heudiconv)")
        except Exception:
            print(f"  {'dcm2niix:':<20s} OK (used by heudiconv)")
    else:
        print(f"  {'dcm2niix:':<20s} NOT FOUND — conda install -c conda-forge dcm2niix")

    # pydicom
    try:
        import pydicom
        print(f"  {'pydicom:':<20s} v{pydicom.__version__}  OK (DICOM reading)")
    except ImportError:
        print(f"  {'pydicom:':<20s} NOT FOUND — pip install pydicom")

    # nibabel
    try:
        import nibabel as nib
        print(f"  {'nibabel:':<20s} v{nib.__version__}  OK (NIfTI reading)")
    except ImportError:
        print(f"  {'nibabel:':<20s} NOT FOUND — pip install nibabel")

    # bids-validator
    bids_val = shutil.which("bids-validator")
    if bids_val:
        print(f"  {'bids-validator:':<20s} OK")
    else:
        print(f"  {'bids-validator:':<20s} NOT FOUND (optional — npm install -g bids-validator)")

    return 0
