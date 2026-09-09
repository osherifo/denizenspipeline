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
from pathlib import Path

from fmriflow.preproc.backends.fmriprep_params import VALID_CONTAINER_TYPES

logger = logging.getLogger(__name__)


def add_preproc_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``fmriflow preproc`` and its sub-subcommands."""
    preproc_parser = subparsers.add_parser(
        "preproc", help="fMRI preprocessing tools",
    )
    preproc_subs = preproc_parser.add_subparsers(dest="preproc_command")

    # ── run ──
    run_p = preproc_subs.add_parser(
        "run", help="Run a preprocessing pipeline (a saved pipeline, a template, or a YAML file)",
    )
    run_p.add_argument("pipeline", help="pipeline name (configs/preproc), template name, or path to a pipeline YAML")
    run_p.add_argument("--subject", required=True, help="participant label (no sub-)")
    run_p.add_argument("--output-dir", required=True, help="derivatives root (work dir defaults to <output_dir>/work)")
    run_p.add_argument("--bids-dir", help="BIDS root ($inputs.bids_dir)")
    run_p.add_argument("--derivatives-dir", help="existing preprocessed data ($inputs.derivatives_dir)")
    run_p.add_argument("--work-dir", help="nipype work dir")
    run_p.add_argument("--dataset", default="unknown", help="dataset label for the manifest")
    run_p.add_argument("--input", action="append", default=[], metavar="NAME=VALUE", help="extra pipeline input")
    run_p.add_argument("--param", action="append", default=[], metavar="NODE.KEY=VALUE", help="override a node parameter")
    run_p.add_argument("--plugin", default="Linear", choices=["Linear", "MultiProc"])
    run_p.add_argument("--n-procs", type=int, default=None)
    run_p.add_argument("--no-cache", action="store_true", help="ignore nipype's cache, re-run every node")
    run_p.add_argument("--rerun-from", action="append", default=[], metavar="NODE_ID", help="re-run from this node onwards")
    run_p.add_argument("--abort-on-bad", action="store_true", help="stop on a bad checkpoint verdict")

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
        "doctor", help="Preflight every node in the library (tools, env, python deps)",
    )

    # ── migrate ──
    mig_p = preproc_subs.add_parser(
        "migrate", help="Convert old stack presets / post-preproc graphs / backend configs into pipelines",
    )
    mig_p.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    mig_p.add_argument("--workflows-dir", action="append", default=[], help="also convert legacy preproc sections in these workflow YAML dirs")


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
    elif cmd == "migrate":
        return _preproc_migrate(args)
    else:
        print("Usage: fmriflow preproc {run|collect|validate|info|doctor|migrate}")
        return 1


# ── Subcommand implementations ──────────────────────────────────────────

def _preproc_run(args) -> int:
    from fmriflow.preproc.graph import Pipeline, PipelineRunRequest
    from fmriflow.preproc.node_registry import NodeRegistry
    from fmriflow.preproc.pipeline_runner import PipelineRunner
    from fmriflow.preproc.templates import load_template, template_names

    ref = str(args.pipeline)
    path = Path(ref)
    try:
        if path.suffix in (".yaml", ".yml") and path.is_file():
            pipeline = Pipeline.load(path)
        elif ref in template_names():
            pipeline = load_template(ref)
        else:
            from fmriflow.server.services.pipeline_store import PipelineStore
            pipeline = PipelineStore().load(ref)
    except (KeyError, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    inputs: dict = {}
    for item in args.input:
        k, _, v = item.partition("=")
        inputs[k.strip()] = v
    overrides: dict[str, dict] = {}
    for item in args.param:
        key, _, v = item.partition("=")
        node_id, _, pkey = key.partition(".")
        if not node_id or not pkey:
            print(f"Error: --param expects NODE.KEY=VALUE, got {item!r}", file=sys.stderr)
            return 1
        overrides.setdefault(node_id, {})[pkey] = _coerce(v)
    request = PipelineRunRequest(
        subject=args.subject, output_dir=args.output_dir, bids_dir=args.bids_dir,
        derivatives_dir=args.derivatives_dir, work_dir=args.work_dir, dataset=args.dataset,
        inputs=inputs, plugin=args.plugin, n_procs=args.n_procs, use_cache=not args.no_cache,
        rerun_from=list(args.rerun_from), abort_on_bad=bool(args.abort_on_bad), params_override=overrides,
    )
    registry = NodeRegistry().discover()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    runner = PipelineRunner(registry, run_id="cli", crash_dir=out / "work" / "crash",
                            checkpoints_path=out / "checkpoints.jsonl",
                            event_sink=lambda ev: _print_event(ev))
    result = runner.run(pipeline, request)
    if result.manifest is not None:
        mp = out / "preproc_manifest.json"
        result.manifest.save(mp)
        print(f"\nManifest written to {mp}")
    if result.status != "completed":
        print("\nPipeline failed:", file=sys.stderr)
        for e in result.errors:
            print(f"  {e.splitlines()[0]}", file=sys.stderr)
        return 1
    print(f"\nPipeline complete in {result.duration_s:.0f}s: "
          + ", ".join(f"{r.node_id}={r.status}" for r in result.node_records))
    return 0


def _coerce(value: str):
    """Best-effort typed value for --param overrides."""
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if "," in value:
        return [v.strip() for v in value.split(",")]
    return value


def _print_event(ev: dict) -> None:
    kind = ev.get("event")
    if kind in ("node_start", "node_done", "node_fail"):
        extra = " (cached)" if ev.get("cached") else ""
        print(f"  [{kind[5:]:5s}] {ev.get('leaf')}{extra}")
    elif kind == "checkpoint":
        print(f"  [check] {ev.get('leaf')}/{ev.get('step')}: {ev.get('verdict')} {'; '.join(ev.get('reasons') or [])}")
    elif kind in ("started", "completed", "failed"):
        print(f"  [{kind}]")


def _preproc_collect(args) -> int:
    from fmriflow.server.services.preproc_outputs import collect_manifest

    run_map = json.loads(args.run_map) if args.run_map else None
    backend_params = {}
    if args.file_pattern:
        backend_params["file_pattern"] = args.file_pattern
    try:
        manifest = collect_manifest({
            "backend": args.backend, "subject": args.subject, "output_dir": args.output_dir,
            "bids_dir": args.bids_dir, "task": args.task, "sessions": args.sessions,
            "run_map": run_map, "backend_params": backend_params,
        })
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
        print(f"{'Steps:':<16}{', '.join(s.name for s in manifest.additional_steps)}")
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
    from fmriflow.preproc.node_registry import NodeRegistry

    reg = NodeRegistry().discover()
    print("\nNode library preflight:\n")
    for name in reg.names():
        info = reg.info(name)
        res = reg.preflight(name)
        if res.ok and not res.warnings:
            status = "OK"
        elif res.ok:
            status = "OK (" + "; ".join(res.warnings) + ")"
        else:
            status = "MISSING — " + "; ".join(res.errors)
        print(f"  {name:22s} {info.kind:14s} {info.source:10s} {status}")
    if reg.shadowed():
        print("\nshadowed:", ", ".join(f"{n} ({src})" for n, src in reg.shadowed()))
    return 0


def _preproc_migrate(args) -> int:
    from fmriflow.preproc.migrate import migrate_all

    report = migrate_all(workflow_dirs=[Path(d) for d in args.workflows_dir], dry_run=bool(args.dry_run))
    print(("DRY RUN — " if args.dry_run else "") + report.summary())
    return 0
