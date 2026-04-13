"""CLI subcommands for ``fmriflow autoflatten``.

Commands:
    fmriflow autoflatten run     — flatten surfaces (or skip if already done)
    fmriflow autoflatten import  — import pre-computed flat patches into pycortex
    fmriflow autoflatten status  — check what exists for a subject
    fmriflow autoflatten doctor  — check tool availability
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def add_autoflatten_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``fmriflow autoflatten`` and its sub-subcommands."""
    af_parser = subparsers.add_parser(
        "autoflatten", help="Cortical surface flattening tools",
    )
    af_subs = af_parser.add_subparsers(dest="autoflatten_command")

    # ── run ──
    run_p = af_subs.add_parser(
        "run", help="Flatten FreeSurfer surfaces (skip if already done)",
    )
    run_p.add_argument(
        "--subjects-dir", type=str, required=True,
        help="FreeSurfer subjects directory",
    )
    run_p.add_argument(
        "--subject", type=str, required=True,
        help="FreeSurfer subject ID (e.g. sub-sub01)",
    )
    run_p.add_argument(
        "--hemispheres", type=str, default="both",
        choices=["lh", "rh", "both"],
    )
    run_p.add_argument(
        "--backend", type=str, default="pyflatten",
        choices=["pyflatten", "freesurfer"],
    )
    run_p.add_argument("--parallel", action="store_true", default=True)
    run_p.add_argument("--no-parallel", action="store_true", default=False)
    run_p.add_argument("--overwrite", action="store_true", default=False)
    run_p.add_argument("--template-file", type=str, default=None)
    run_p.add_argument("--output-dir", type=str, default=None)
    run_p.add_argument(
        "--import-to-pycortex", action="store_true", default=False,
        help="Import surfaces + flatmap into pycortex after flattening",
    )
    run_p.add_argument(
        "--pycortex-surface", type=str, default=None,
        help="pycortex surface name (default: {subject}fs)",
    )

    # ── import ──
    import_p = af_subs.add_parser(
        "import", help="Import pre-computed flat patches into pycortex",
    )
    import_p.add_argument(
        "--subjects-dir", type=str, required=True,
        help="FreeSurfer subjects directory",
    )
    import_p.add_argument(
        "--subject", type=str, required=True,
        help="FreeSurfer subject ID",
    )
    import_p.add_argument(
        "--flat-patch-lh", type=str, required=True,
        help="Path to LH flat patch file",
    )
    import_p.add_argument(
        "--flat-patch-rh", type=str, required=True,
        help="Path to RH flat patch file",
    )
    import_p.add_argument(
        "--pycortex-surface", type=str, default=None,
        help="pycortex surface name (default: {subject}fs)",
    )

    # ── status ──
    status_p = af_subs.add_parser(
        "status", help="Check what exists for a subject",
    )
    status_p.add_argument(
        "--subjects-dir", type=str, required=True,
        help="FreeSurfer subjects directory",
    )
    status_p.add_argument(
        "--subject", type=str, required=True,
        help="FreeSurfer subject ID",
    )

    # ── doctor ──
    af_subs.add_parser(
        "doctor", help="Check tool availability",
    )


def dispatch_autoflatten(args) -> int:
    """Dispatch to the appropriate autoflatten subcommand."""
    cmd = getattr(args, "autoflatten_command", None)
    if cmd == "run":
        return _af_run(args)
    elif cmd == "import":
        return _af_import(args)
    elif cmd == "status":
        return _af_status(args)
    elif cmd == "doctor":
        return _af_doctor(args)
    else:
        print("Usage: fmriflow autoflatten {run|import|status|doctor}")
        return 1


# ── Subcommand implementations ──────────────────────────────────────────

def _af_run(args) -> int:
    from fmriflow.preproc.autoflatten import AutoflattenConfig, run_autoflatten

    config = AutoflattenConfig(
        subjects_dir=args.subjects_dir,
        subject=args.subject,
        hemispheres=args.hemispheres,
        parallel=args.parallel and not args.no_parallel,
        backend=args.backend,
        overwrite=args.overwrite,
        template_file=args.template_file,
        output_dir=args.output_dir,
        import_to_pycortex=args.import_to_pycortex,
        pycortex_surface_name=args.pycortex_surface,
    )

    errors = config.validate()
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1

    try:
        result = run_autoflatten(config)
        print(f"\nAutoflatten complete.")
        print(f"  Subject:      {result.subject}")
        print(f"  Source:        {result.source}")
        print(f"  Hemispheres:  {', '.join(result.hemispheres)}")
        for hemi, path in result.flat_patches.items():
            print(f"  {hemi} patch:    {path}")
        if result.pycortex_surface:
            print(f"  pycortex:     {result.pycortex_surface}")
        print(f"  Elapsed:      {result.elapsed_s:.1f}s")
        return 0
    except Exception as e:
        print(f"\nAutoflatten failed: {e}", file=sys.stderr)
        logger.error("Autoflatten failed", exc_info=True)
        return 1


def _af_import(args) -> int:
    from fmriflow.preproc.autoflatten import import_flat_patches

    try:
        cx_name = import_flat_patches(
            subjects_dir=args.subjects_dir,
            subject=args.subject,
            flat_patch_lh=args.flat_patch_lh,
            flat_patch_rh=args.flat_patch_rh,
            pycortex_surface_name=args.pycortex_surface,
        )
        if cx_name:
            print(f"\nImport complete.")
            print(f"  pycortex surface: {cx_name}")
        else:
            print("\nImport failed — check logs for details.", file=sys.stderr)
            return 1
        return 0
    except Exception as e:
        print(f"\nImport failed: {e}", file=sys.stderr)
        logger.error("Import failed", exc_info=True)
        return 1


def _af_status(args) -> int:
    from fmriflow.preproc.autoflatten import (
        check_surfaces,
        detect_existing_flats,
        check_pycortex_available,
    )
    from pathlib import Path

    subjects_dir = args.subjects_dir
    subject = args.subject
    subject_dir = Path(subjects_dir) / subject

    print(f"\nSubject: {subject}")
    print(f"Path:    {subject_dir}")
    print()

    if not subject_dir.is_dir():
        print("  Subject directory: NOT FOUND")
        return 1

    # Check surfaces
    surfaces = check_surfaces(subjects_dir, subject)
    required = ["lh.inflated", "rh.inflated"]
    have_surfaces = all(surfaces.get(s, False) for s in required)
    if have_surfaces:
        present = [k for k, v in surfaces.items() if v]
        print(f"  FreeSurfer surfaces: OK ({', '.join(present[:4])}...)")
    else:
        missing = [k for k, v in surfaces.items() if not v]
        print(f"  FreeSurfer surfaces: MISSING ({', '.join(missing)})")

    # Check flat patches
    flats = detect_existing_flats(subjects_dir, subject)
    if flats:
        for hemi, path in flats.items():
            print(f"  Flat patch ({hemi}):     FOUND ({path.name})")
    else:
        print("  Flat patches:        NOT FOUND")

    # Check pycortex
    cx_available, _ = check_pycortex_available()
    if cx_available:
        try:
            import cortex
            existing = cortex.db.get_list()
            # Check common naming patterns
            candidates = [
                f"{subject}fs",
                subject,
                subject.replace("sub-", ""),
                f"{subject.replace('sub-', '')}fs",
            ]
            found_cx = [c for c in candidates if c in existing]
            if found_cx:
                print(f"  pycortex surface:    FOUND ({', '.join(found_cx)})")
            else:
                print("  pycortex surface:    NOT FOUND")
        except Exception:
            print("  pycortex surface:    ERROR checking")
    else:
        print("  pycortex:            NOT INSTALLED")

    # Recommendation
    print()
    if not have_surfaces:
        print("  -> Run FreeSurfer reconall first (fmriflow preproc run --mode anat_only)")
    elif not flats:
        print("  -> Ready for: fmriflow autoflatten run")
    elif not cx_available:
        print("  -> Install pycortex, then: fmriflow autoflatten import")
    elif not found_cx:
        print("  -> Ready for: fmriflow autoflatten import (or run with --import-to-pycortex)")
    else:
        print("  -> All set — surfaces, flatmaps, and pycortex registration are present")

    return 0


def _af_doctor(args) -> int:
    from fmriflow.preproc.autoflatten import (
        check_autoflatten_available,
        check_pycortex_available,
    )
    import shutil

    print("\nAutoflatten tool availability:\n")

    # autoflatten
    available, detail = check_autoflatten_available()
    status = "OK" if available else "NOT AVAILABLE"
    print(f"  {'autoflatten':20s} {status} — {detail}")

    # pycortex
    available, detail = check_pycortex_available()
    status = "OK" if available else "NOT AVAILABLE"
    print(f"  {'pycortex':20s} {status} — {detail}")

    # FreeSurfer
    fs_home = shutil.which("mri_label2label")
    if fs_home:
        print(f"  {'FreeSurfer':20s} OK — mri_label2label found")
    else:
        print(f"  {'FreeSurfer':20s} NOT FOUND — needed for projection step")

    return 0
