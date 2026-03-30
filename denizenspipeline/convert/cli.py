"""CLI subcommands for ``denizens convert``.

Commands:
    denizens convert run        — run DICOM-to-BIDS conversion via heudiconv
    denizens convert collect     — build manifest from existing BIDS dataset
    denizens convert validate    — validate a conversion manifest
    denizens convert scan        — list DICOM series in a directory
    denizens convert dry-run     — preview conversion mapping
    denizens convert heuristics  — manage heuristic registry
    denizens convert doctor      — check tool availability
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def add_convert_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``denizens convert`` and its sub-subcommands."""
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
    elif cmd == "heuristics":
        return _convert_heuristics(args)
    elif cmd == "doctor":
        return _convert_doctor(args)
    else:
        print("Usage: denizens convert {run|collect|validate|scan|dry-run|heuristics|doctor}")
        return 1


# ── Subcommand implementations ──────────────────────────────────────────

def _convert_run(args) -> int:
    from denizenspipeline.convert.manifest import ConvertConfig
    from denizenspipeline.convert.runner import run_conversion

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
    from denizenspipeline.convert.manifest import ConvertConfig
    from denizenspipeline.convert.runner import collect_bids, MANIFEST_FILENAME
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
    from denizenspipeline.convert.manifest import ConvertManifest
    from denizenspipeline.convert.validation import validate_manifest

    try:
        manifest = ConvertManifest.from_json(args.manifest)
    except Exception as e:
        print(f"Cannot load manifest: {e}", file=sys.stderr)
        return 1

    config = None
    if args.for_config:
        from denizenspipeline.config.loader import load_config
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
    from denizenspipeline.convert.dicom_utils import extract_scanner_info, list_series

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
        from denizenspipeline.convert.heuristics import match_heuristic
        match = match_heuristic(scanner)
        if match:
            version = f" (v{match.version})" if match.version else ""
            print(f"\nMatching heuristic: {match.name}{version}")

    return 0


def _convert_dry_run(args) -> int:
    from denizenspipeline.convert.manifest import ConvertConfig
    from denizenspipeline.convert.runner import dry_run

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


def _convert_heuristics(args) -> int:
    from denizenspipeline.convert.heuristics import (
        list_heuristics, register_heuristic, remove_heuristic, _load_heuristic_info,
        get_heuristic,
    )

    heur_cmd = getattr(args, "heuristics_command", None)

    if heur_cmd is None or heur_cmd == "list":
        heuristics = list_heuristics()
        if not heuristics:
            print("\nNo heuristics registered.")
            print("Register one with: denizens convert heuristics add <path>")
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
            return 0
        except Exception as e:
            print(f"\n{e}", file=sys.stderr)
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
        print("Usage: denizens convert heuristics {list|add|info|remove}")
        return 1


def _convert_doctor(args) -> int:
    import shutil

    print("\nTool availability:\n")

    # heudiconv
    heudiconv_path = shutil.which("heudiconv")
    if heudiconv_path:
        from denizenspipeline.convert.runner import _get_heudiconv_version
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
