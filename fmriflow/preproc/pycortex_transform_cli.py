"""CLI for the pycortex-transform step: ``fmriflow pycortex-transform ...``."""

from __future__ import annotations

import argparse
import logging

logger = logging.getLogger(__name__)


def add_pycortex_transform_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``pycortex-transform`` command group."""
    px = subparsers.add_parser(
        "pycortex-transform",
        help="Create a pycortex transform (EPI→surface alignment) for a subject",
    )
    sub = px.add_subparsers(dest="pycortex_transform_command")

    create_p = sub.add_parser("create", help="Create/align a pycortex transform")
    create_p.add_argument("cx_subject", help="Pycortex subject name (e.g. sub01fs)")
    create_p.add_argument("reference", help="Path to the functional reference volume (NIfTI)")
    create_p.add_argument("--xfmname", default="fmriflow", help="Transform name (default: fmriflow)")
    create_p.add_argument(
        "--method",
        choices=("automatic", "automatic_fsl", "manual"),
        default="automatic",
        help=(
            "automatic = FreeSurfer bbregister + mri_coreg (needs $SUBJECTS_DIR + "
            "FreeSurfer on PATH); automatic_fsl = FSL FLIRT BBR (needs FSL on PATH); "
            "manual = interactive aligner."
        ),
    )
    create_p.add_argument("--overwrite", action="store_true", help="Redo if the transform exists")

    status_p = sub.add_parser("status", help="Show a transform's cortical-mask voxel count")
    status_p.add_argument("cx_subject", help="Pycortex subject name")
    status_p.add_argument("--xfmname", default="fmriflow", help="Transform name (default: fmriflow)")

    sub.add_parser(
        "doctor",
        help="Check pycortex / FreeSurfer / FSL availability",
    )


def dispatch_pycortex_transform(args) -> int:
    cmd = getattr(args, "pycortex_transform_command", None)
    if cmd == "create":
        return _create(args)
    if cmd == "status":
        return _status(args)
    if cmd == "doctor":
        return _doctor(args)
    print("Usage: fmriflow pycortex-transform {create,status,doctor} ...")
    return 1


def _create(args) -> int:
    from fmriflow.preproc.pycortex_transform import (
        PycortexTransformConfig,
        create_transform,
    )

    config = PycortexTransformConfig(
        cx_subject=args.cx_subject,
        reference=args.reference,
        xfmname=args.xfmname,
        method=args.method,
        overwrite=args.overwrite,
    )
    errs = config.validate()
    if errs:
        print("Invalid configuration:")
        for e in errs:
            print(f"  - {e}")
        return 1

    try:
        result = create_transform(config)
    except Exception as exc:
        print(f"pycortex-transform failed: {exc}")
        return 1

    verb = "created" if result.created else "reused (already existed)"
    print(f"Transform '{result.xfmname}' {verb} for '{result.cx_subject}'.")
    print(f"  reference   : {result.reference}")
    print(f"  method      : {result.method}")
    print(f"  mask voxels : {result.n_mask_voxels}")
    print(f"  filestore   : {result.filestore}")
    print(f"  elapsed     : {result.elapsed_s:.1f}s")
    return 0


def _status(args) -> int:
    from fmriflow.preproc.autoflatten import check_pycortex_available
    from fmriflow.preproc.pycortex_transform import (
        transform_exists,
        mask_voxel_count,
    )

    # Both transform_exists() and mask_voxel_count() ``import cortex``
    # unconditionally; without the guard the user gets an ImportError
    # stack trace on a missing-dep box. Mirror the friendly-message
    # pattern ``autoflatten status`` uses.
    ok_px, msg_px = check_pycortex_available()
    if not ok_px:
        print(f"pycortex unavailable — {msg_px}")
        print("Run `fmriflow pycortex-transform doctor` for details.")
        return 1

    if not transform_exists(args.cx_subject, args.xfmname):
        print(f"Transform '{args.xfmname}' not found for '{args.cx_subject}'.")
        return 1
    n = mask_voxel_count(args.cx_subject, args.xfmname)
    print(f"Transform '{args.xfmname}' for '{args.cx_subject}': cortical mask = {n} voxels")
    return 0


def _doctor(args) -> int:
    from fmriflow.preproc.pycortex_transform import (
        check_freesurfer_available,
        check_fsl_available,
    )
    from fmriflow.preproc.autoflatten import check_pycortex_available

    ok_px, msg_px = check_pycortex_available()
    ok_fs, msg_fs = check_freesurfer_available()
    ok_fsl, msg_fsl = check_fsl_available()

    print(f"pycortex   : {'OK' if ok_px else 'MISSING'} — {msg_px}")
    # FreeSurfer covers method='automatic' (the default); FSL covers
    # method='automatic_fsl'. The doctor is purely informational and
    # always exits 0 — matches the convert/autoflatten doctor convention
    # so setup scripts can pipe its output without conditional handling.
    print(f"FreeSurfer : {'OK' if ok_fs else 'MISSING'} — {msg_fs}")
    print(f"FSL flirt  : {'OK' if ok_fsl else 'MISSING'} — {msg_fsl}")

    return 0
