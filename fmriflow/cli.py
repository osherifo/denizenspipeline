"""CLI entry point for fmriflow.

Usage:
    fmriflow run experiment.yaml
    fmriflow run experiment.yaml --stages features,preprocess,model
    fmriflow run experiment.yaml --resume-from model
    fmriflow validate experiment.yaml
    fmriflow modules
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from fmriflow import ui

logger = logging.getLogger(__name__)


def _setup_file_logging(output_dir: str) -> Path:
    """Configure a file handler that logs everything to {output_dir}/pipeline.log.

    Returns the log file path.
    """
    log_dir = Path(output_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pipeline.log"

    file_handler = logging.FileHandler(log_path, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))

    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    # Ensure root logger level allows DEBUG through to the file handler
    if root_logger.level > logging.DEBUG:
        root_logger.setLevel(logging.DEBUG)

    # Silence noisy third-party loggers
    for name in ('matplotlib', 'PIL', 'h5py'):
        logging.getLogger(name).setLevel(logging.WARNING)

    return log_path


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='fmriflow',
        description='fMRIflow — neuroscience encoding model pipeline',
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='Enable verbose logging',
    )

    subparsers = parser.add_subparsers(dest='command')

    # ── run ──
    run_parser = subparsers.add_parser('run', help='Run a pipeline')
    run_parser.add_argument('config', help='Path to experiment YAML config')
    run_parser.add_argument(
        '--stages', type=str, default=None,
        help='Comma-separated list of stages to run',
    )
    run_parser.add_argument(
        '--resume-from', type=str, default=None,
        help='Resume from a checkpoint at this stage',
    )
    run_parser.add_argument(
        '--subject', type=str, default=None,
        help='Override subject (for batch configs)',
    )
    run_parser.add_argument(
        '--dry-run', action='store_true',
        help='Resolve config and show what would execute, without running',
    )
    run_parser.add_argument(
        '--input', action='append', default=[], metavar='NAME=VALUE',
        help='Value for a graph input (graph files only; repeatable)',
    )
    run_parser.add_argument(
        '--engine', choices=['legacy', 'graph'], default=None,
        help='Execution engine: legacy stage orchestrator or the node-graph '
             'engine (default: $FMRIFLOW_ENGINE, else graph; --stages and '
             '--resume-from fall back to legacy)',
    )

    # ── run-group ──
    rg_parser = subparsers.add_parser(
        'run-group', help='Run a group-scope (cross-subject) pipeline')
    rg_parser.add_argument('config', help='Path to group YAML config')
    rg_parser.add_argument(
        '--resume', action='store_true',
        help='Continue the most recent run (or --run-id): subjects whose '
             'run_summary.json is ok are skipped',
    )
    rg_parser.add_argument(
        '--run-id', type=str, default=None,
        help='Run directory name to write to (default: new timestamp)',
    )
    rg_parser.add_argument(
        '--dry-run', action='store_true',
        help='Resolve subject configs and print plan without running',
    )

    # ── run-study ──
    rs_parser = subparsers.add_parser(
        'run-study', help='Run a study-scope (cross-group) pipeline')
    rs_parser.add_argument('config', help='Path to study YAML config')
    rs_parser.add_argument(
        '--resume', action='store_true',
        help='Continue the most recent run (or --run-id): subjects whose '
             'run_summary.json is ok are skipped in every group',
    )
    rs_parser.add_argument(
        '--run-id', type=str, default=None,
        help='Run directory name to write to (default: new timestamp)',
    )
    rs_parser.add_argument(
        '--dry-run', action='store_true',
        help='Resolve groups and print plan without running',
    )

    # ── graph ──
    graph_parser = subparsers.add_parser('graph', help='Analysis graph tools')
    graph_sub = graph_parser.add_subparsers(dest='graph_command')
    graph_compile = graph_sub.add_parser(
        'compile', help='Compile a stage config into an analysis graph YAML')
    graph_compile.add_argument('config', help='Path to a subject stage config')
    graph_compile.add_argument('-o', '--output', default=None,
                               help='Write the graph here (default: stdout)')
    graph_validate = graph_sub.add_parser(
        'validate', help='Validate an analysis graph, or the graph a stage config compiles to')
    graph_validate.add_argument('config', help='Path to a graph YAML or a stage config')
    graph_validate.add_argument('--input', action='append', default=[], metavar='NAME=VALUE',
                                help='Value for a graph input (repeatable)')

    # ── validate ──
    validate_parser = subparsers.add_parser(
        'validate', help='Validate a config without running')
    validate_parser.add_argument('config', help='Path to experiment YAML config')

    # ── modules ──
    subparsers.add_parser('modules', help='List available pipeline modules')

    # ── list ──
    list_parser = subparsers.add_parser(
        'list', help='List stages, modules, or modules for a stage')
    list_parser.add_argument(
        'what', nargs='?', default='stages',
        help=(
            'What to list: "stages" (default), "modules" (all), '
            'or a stage name to list its modules'
        ),
    )

    # ── serve ──
    serve_parser = subparsers.add_parser(
        'serve', help='Start the frontend server')
    serve_parser.add_argument(
        '--port', type=int, default=8421, help='Server port (default: 8421)')
    serve_parser.add_argument(
        '--host', type=str, default='127.0.0.1', help='Server host')
    serve_parser.add_argument(
        '--results-dir', type=str, default=None,
        help='Directory to scan for run summaries '
             '(default: $FMRIFLOW_HOME/data/results/)')
    serve_parser.add_argument(
        '--open', action='store_true',
        help='Open the web UI in a browser after starting')
    serve_parser.add_argument(
        '--modules-dir', type=str, default=None,
        help='Directory for user modules '
             '(default: $FMRIFLOW_HOME/addons/modules/)')
    serve_parser.add_argument(
        '--configs-dir', type=str, default=None,
        help='Directory containing experiment YAML configs '
             '(default: $FMRIFLOW_HOME/configs/)')
    serve_parser.add_argument(
        '--derivatives-dir', type=str, default=None,
        help='Directory containing preprocessing derivatives '
             '(default: $FMRIFLOW_HOME/data/derivatives/)')

    # ── compose ──
    compose_parser = subparsers.add_parser(
        'compose', help='Open a config in the frontend composer')
    compose_parser.add_argument('config', help='Path to experiment YAML config')
    compose_parser.add_argument(
        '--port', type=int, default=8421, help='Server port (default: 8421)')

    # ── preproc ──
    from fmriflow.preproc.cli import add_preproc_subcommands
    add_preproc_subcommands(subparsers)

    # ── convert ──
    from fmriflow.convert.cli import add_convert_subcommands
    add_convert_subcommands(subparsers)

    # ── autoflatten ──
    from fmriflow.preproc.autoflatten_cli import add_autoflatten_subcommands
    add_autoflatten_subcommands(subparsers)

    # ── pycortex transforms (EPI→surface alignment) ──
    from fmriflow.preproc.pycortex_transform_cli import add_pycortex_transform_subcommands
    add_pycortex_transform_subcommands(subparsers)

    # ── triage (automatic error capture) ──
    from fmriflow.triage.cli import add_triage_subcommands
    add_triage_subcommands(subparsers)

    # ── working-directory bootstrap (init, paths, migrate) ──
    from fmriflow import cli_bootstrap
    cli_bootstrap.add_subcommands(subparsers)

    args = parser.parse_args(argv)

    # Set up logging — suppress standard log format, let rich handle output.
    # Always show logs for preproc commands (they are long-running).
    level = logging.DEBUG if args.verbose else logging.INFO
    show_logs = args.verbose or args.command in ('preproc', 'convert', 'autoflatten', 'pycortex-transform')
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        handlers=[logging.NullHandler()] if not show_logs else None,
    )

    # Python 3.3+ argparse bug: nested subparsers don't always set the
    # parent dest.  Fall back to checking subcommand attrs when command is None.
    if args.command is None and getattr(args, 'preproc_command', None):
        args.command = 'preproc'
    if args.command is None and getattr(args, 'convert_command', None):
        args.command = 'convert'
    if args.command is None and getattr(args, 'autoflatten_command', None):
        args.command = 'autoflatten'
    if args.command is None and getattr(args, 'pycortex_transform_command', None):
        args.command = 'pycortex-transform'
    if args.command is None and getattr(args, 'triage_command', None):
        args.command = 'triage'

    if args.command == 'run':
        return _cmd_run(args)
    elif args.command == 'run-group':
        return _cmd_run_group(args)
    elif args.command == 'run-study':
        return _cmd_run_study(args)
    elif args.command == 'validate':
        return _cmd_validate(args)
    elif args.command == 'graph':
        return _cmd_graph(args)
    elif args.command == 'modules':
        return _cmd_modules(args)
    elif args.command == 'list':
        return _cmd_list(args)
    elif args.command == 'serve':
        return _cmd_serve(args)
    elif args.command == 'compose':
        return _cmd_compose(args)
    elif args.command == 'preproc':
        from fmriflow.preproc.cli import dispatch_preproc
        return dispatch_preproc(args)
    elif args.command == 'convert':
        from fmriflow.convert.cli import dispatch_convert
        return dispatch_convert(args)
    elif args.command == 'autoflatten':
        from fmriflow.preproc.autoflatten_cli import dispatch_autoflatten
        return dispatch_autoflatten(args)
    elif args.command == 'pycortex-transform':
        from fmriflow.preproc.pycortex_transform_cli import dispatch_pycortex_transform
        return dispatch_pycortex_transform(args)
    elif args.command == 'triage':
        from fmriflow.triage.cli import run_triage_command
        return run_triage_command(args)
    elif args.command in ('init', 'paths', 'migrate'):
        from fmriflow import cli_bootstrap
        return cli_bootstrap.dispatch(args)
    else:
        parser.print_help()
        return 1


def _build_registry():
    """Module registry with built-ins, entry points and user add-on modules.

    Runs launched from the web server execute in this CLI process, so the
    add-on modules have to be loaded here too, not only in the server.
    """
    from fmriflow.modules.user_modules import discover_user_modules
    from fmriflow.registry import ModuleRegistry

    registry = ModuleRegistry()
    registry.discover()
    n_user = discover_user_modules()
    if n_user:
        logger.info("Loaded %d user add-on module file(s)", n_user)
    return registry


def _yaml_mapping(path: str) -> dict | None:
    import yaml
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _is_graph_file(path: str) -> bool:
    """True for an analysis graph YAML (``nodes:``, optionally under ``graph:``)."""
    data = _yaml_mapping(path)
    if not data:
        return False
    if isinstance(data.get('graph'), dict) and 'nodes' not in data:
        data = data['graph']
    return 'nodes' in data


def _parse_inputs(items: list[str]) -> dict:
    """``NAME=VALUE`` pairs; values parse as YAML so lists and numbers work."""
    import yaml
    out: dict = {}
    for item in items or []:
        name, sep, value = item.partition('=')
        if not sep or not name.strip():
            raise ValueError(f"--input expects NAME=VALUE, got {item!r}")
        try:
            out[name.strip()] = yaml.safe_load(value)
        except Exception:
            out[name.strip()] = value
    return out


def _cmd_run_graph_file(args) -> int:
    """Run an analysis graph YAML on the graph engine."""
    import os as _os

    from fmriflow.analysis.catalog import NodeCatalog
    from fmriflow.analysis.executor import GraphExecutor, resolve_graph_inputs
    from fmriflow.analysis.graph import AnalysisGraph
    from fmriflow.core import paths

    if getattr(args, 'engine', None) == 'legacy':
        ui.error_panel("Graph files run on the graph engine; drop --engine legacy.")
        return 1
    if args.stages or args.resume_from:
        ui.error_panel("--stages and --resume-from apply to stage configs, not graph files.")
        return 1
    try:
        graph = AnalysisGraph.load(args.config)
        inputs = _parse_inputs(getattr(args, 'input', []))
        if args.subject and 'subject' in graph.inputs:
            inputs.setdefault('subject', args.subject)
        bound, _ = resolve_graph_inputs(graph, inputs)
    except Exception as e:
        ui.error_panel(str(e))
        return 1
    if graph.scope != 'subject':
        ui.error_panel(f"{graph.scope} graphs cannot run yet; only subject graphs do.")
        return 1
    if args.subject and 'subject' not in graph.inputs:
        bound.globals['subject'] = args.subject

    reporting = bound.globals.setdefault('reporting', {})
    output_dir = reporting.get('output_dir') or str(paths.results_root())
    output_dir = _os.path.expanduser(_os.path.expandvars(str(output_dir)))
    reporting['output_dir'] = output_dir
    log_path = _setup_file_logging(output_dir)
    logger.info("Graph run started — graph: %s", args.config)

    if args.dry_run:
        ui.console.print(f"\n[bold]Graph:[/] {bound.name} ({bound.scope})")
        for node in bound.nodes:
            ui.console.print(f"  {node.id:<32} {node.type}")
        return 0

    ui.header(bound.globals.get('experiment') or bound.name, bound.globals.get('subject', '?'), bound.globals)
    ui.console.print()
    executor = GraphExecutor(NodeCatalog(_build_registry()).discover())
    ctx = None
    try:
        ctx = executor.run(bound, write_graph=True)
        ui.success("Graph run completed successfully.")
        if ctx.has('result'):
            from fmriflow.core.types import ModelResult
            result = ctx.get('result', ModelResult)
            ui.results_panel(mean_score=result.scores.mean(), max_score=result.scores.max(),
                             n_voxels=result.n_voxels)
        if ctx.artifacts:
            ui.artifacts_panel(ctx.artifacts)
        _save_run_summary(ctx, output_dir)
        return 0
    except Exception as e:
        logger.error("Graph run failed: %s", e, exc_info=True)
        ui.error_panel(str(e), stage=getattr(e, 'stage', None))
        ui.log_hint(str(log_path))
        _save_run_summary(executor.last_context, output_dir)
        return 1


def _cmd_graph(args) -> int:
    """fmriflow graph compile | validate."""
    import sys as _sys

    from fmriflow.analysis.catalog import NodeCatalog
    from fmriflow.analysis.compile_legacy import compile_subject_config
    from fmriflow.analysis.executor import GraphExecutor, resolve_graph_inputs
    from fmriflow.analysis.graph import AnalysisGraph
    from fmriflow.config.loader import load_config
    from fmriflow.exceptions import ConfigError

    if args.graph_command == 'compile':
        try:
            graph = compile_subject_config(load_config(args.config))
        except Exception as e:
            ui.error_panel(str(e))
            return 1
        text = graph.to_yaml()
        if args.output:
            Path(args.output).write_text(text)
            ui.success(f"Wrote {args.output}: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
        else:
            _sys.stdout.write(text)
        return 0

    if args.graph_command == 'validate':
        try:
            if _is_graph_file(args.config):
                graph = AnalysisGraph.load(args.config)
            else:
                graph = compile_subject_config(load_config(args.config))
            catalog = NodeCatalog(_build_registry()).discover()
            errors = graph.validate(catalog)
            if not errors:
                try:
                    bound, _ = resolve_graph_inputs(graph, _parse_inputs(args.input))
                except ConfigError as e:
                    errors = list(e.errors)
                else:
                    errors = GraphExecutor(catalog).validate(bound)
        except Exception as e:
            ui.error_panel(str(e))
            return 1
        if errors:
            ui.config_error(errors)
            return 1
        ui.success(f"Graph is valid: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
        return 0

    ui.error_panel("usage: fmriflow graph {compile,validate} ...")
    return 1


def _cmd_run(args) -> int:
    """Run the pipeline."""
    from fmriflow.pipeline import Pipeline

    if _is_graph_file(args.config):
        return _cmd_run_graph_file(args)

    try:
        pipeline = Pipeline.from_yaml(args.config, registry=_build_registry(),
                                      engine=getattr(args, 'engine', None))
    except Exception as e:
        ui.error_panel(str(e))
        return 1

    # Override subject if specified
    if args.subject:
        pipeline.config['subject'] = args.subject

    # Set up file logging to {output_dir}/pipeline.log
    from fmriflow.core import paths
    output_dir = pipeline.config.get('reporting', {}).get(
        'output_dir') or str(paths.results_root())
    # Expand `~` / `$VAR` so YAML can use them naturally without
    # creating a literal-tilde directory under CWD.
    import os as _os
    output_dir = _os.path.expanduser(_os.path.expandvars(output_dir))
    log_path = _setup_file_logging(output_dir)
    logger.info("Pipeline started — config: %s", args.config)

    # Parse stages
    stages = None
    if args.stages:
        stages = [s.strip() for s in args.stages.split(',')]

    if args.dry_run:
        ui.dry_run_panel(pipeline.config, stages)
        return 0

    # Print header
    ui.header(
        pipeline.config.get('experiment', '?'),
        pipeline.config.get('subject', '?'),
        pipeline.config,
    )
    ui.console.print()

    ctx = None
    try:
        ctx = pipeline.run(stages=stages, resume_from=args.resume_from)
        ui.success("Pipeline completed successfully.")

        # Print results
        if ctx.has('result'):
            from fmriflow.core.types import ModelResult
            result = ctx.get('result', ModelResult)
            ui.results_panel(
                mean_score=result.scores.mean(),
                max_score=result.scores.max(),
                n_voxels=result.n_voxels,
            )

        if ctx.artifacts:
            ui.artifacts_panel(ctx.artifacts)

        _save_run_summary(ctx, output_dir)
        return 0

    except Exception as e:
        stage = getattr(e, 'stage', None)
        logger.error("Pipeline failed: %s", e, exc_info=True)
        ui.error_panel(str(e), stage=stage)
        ui.log_hint(str(log_path))
        if logger.isEnabledFor(logging.DEBUG):
            ui.console.print_exception()
        # Save partial summary on failure too
        if ctx is None:
            ctx = pipeline.last_context
        _save_run_summary(ctx, output_dir)
        return 1


def _resume_run_id(args, resolve, config: dict) -> str | None:
    """Run id for run-group / run-study: --run-id, else the latest run on --resume."""
    run_id = getattr(args, 'run_id', None)
    if run_id or not getattr(args, 'resume', False):
        return run_id
    run_id = resolve(config)
    if run_id:
        ui.console.print(f"[bold]Resuming[/] run {run_id}")
    else:
        ui.console.print("No previous run found; starting a new run.")
    return run_id


def _cmd_run_group(args) -> int:
    """Run a group-scope (cross-subject) pipeline."""
    from fmriflow.config.loader import load_group_config
    from fmriflow.group_orchestrator import GroupOrchestrator
    from fmriflow.registry import ModuleRegistry

    try:
        group_config = load_group_config(args.config)
    except Exception as e:
        ui.error_panel(str(e))
        return 1

    registry = _build_registry()
    run_id = _resume_run_id(args, GroupOrchestrator.resolve_resume_run_id, group_config)
    orch = GroupOrchestrator(group_config, registry, run_id=run_id)

    if args.dry_run:
        ui.console.print(
            f"\n[bold]Group:[/] {orch.group_name}\n"
            f"[bold]Output dir:[/] {orch.group_dir}\n"
            f"[bold]Subjects:[/] "
            f"{', '.join(group_config.get('subjects', []))}\n"
        )
        return 0

    ui.console.print(
        f"\n[bold bright_cyan]Group run[/] "
        f"{orch.group_name} → {orch.group_dir}\n"
    )

    try:
        result = orch.run(resume=args.resume)
    except Exception as e:
        ui.error_panel(str(e))
        logger.error("Group run failed: %s", e, exc_info=True)
        return 1

    ok = len(result.subjects_by_status('ok'))
    failed = len(result.subjects_by_status('failed'))
    ui.console.print(
        f"\n[bold]Done.[/] "
        f"{ok} ok, {failed} failed, "
        f"{len(result.subjects)} total subjects.\n"
        f"Group summary: {orch.group_dir / 'group_summary.json'}\n"
    )
    return 0 if failed == 0 else 1


def _cmd_run_study(args) -> int:
    """Run a study-scope (cross-group) pipeline."""
    from fmriflow.config.loader import load_study_config
    from fmriflow.study_orchestrator import StudyOrchestrator
    from fmriflow.registry import ModuleRegistry

    try:
        study_config = load_study_config(args.config)
    except Exception as e:
        ui.error_panel(str(e))
        return 1

    registry = _build_registry()
    run_id = _resume_run_id(args, StudyOrchestrator.resolve_resume_run_id, study_config)
    orch = StudyOrchestrator(study_config, registry, run_id=run_id,
                             config_path=args.config)

    if args.dry_run:
        labels = [str(e.get('name')) for e in study_config.get('groups', [])]
        ui.console.print(
            f"\n[bold]Study:[/] {orch.study_name}\n"
            f"[bold]Output dir:[/] {orch.study_dir}\n"
            f"[bold]Groups:[/] {', '.join(labels)}\n"
        )
        return 0

    ui.console.print(
        f"\n[bold bright_cyan]Study run[/] "
        f"{orch.study_name} → {orch.study_dir}\n"
    )

    try:
        result = orch.run(resume=args.resume)
    except Exception as e:
        ui.error_panel(str(e))
        logger.error("Study run failed: %s", e, exc_info=True)
        return 1

    n_groups = len(result.groups)
    n_failed_groups = len(result.groups_by_status('failed'))
    ui.console.print(
        f"\n[bold]Done.[/] "
        f"{n_groups - n_failed_groups} ok, {n_failed_groups} failed, "
        f"{n_groups} total groups.\n"
        f"Study summary: {orch.study_dir / 'study_summary.json'}\n"
    )
    return 0 if n_failed_groups == 0 else 1


def _save_run_summary(ctx, output_dir: str) -> None:
    """Persist run summary JSON and timeline chart if available."""
    if ctx is None or not hasattr(ctx, 'run_summary'):
        return
    summary = ctx.run_summary
    out = Path(output_dir)
    try:
        summary.save_json(out / 'run_summary.json')
    except Exception:
        logger.warning("Could not save run_summary.json", exc_info=True)
    try:
        from fmriflow.core.run_chart import save_timeline_chart
        save_timeline_chart(summary, out / 'run_timeline.png')
    except Exception:
        logger.warning("Could not save run_timeline.png", exc_info=True)


def _cmd_validate(args) -> int:
    """Validate a config file."""
    from fmriflow.config.loader import load_config
    from fmriflow.registry import ModuleRegistry

    try:
        config = load_config(args.config)
        ui.console.print(f"\n[bold]Validating[/] {args.config}\n")

        ui.validate_line(True, f"Config loaded")
        ui.validate_line(True, f"Experiment: {config.get('experiment')}")
        ui.validate_line(True, f"Subject: {config.get('subject')}")

        # Check modules
        registry = _build_registry()

        stim_loader = config.get('stimulus', {}).get('loader', 'textgrid')
        try:
            registry.get_stimulus_loader(stim_loader)
            ui.validate_line(True, f"Stimulus loader: [cyan]{stim_loader}[/]")
        except Exception as e:
            ui.validate_line(False, f"Stimulus loader: {e}")

        resp_loader = config.get('response', {}).get('loader', 'cloud')
        try:
            registry.get_response_loader(resp_loader)
            ui.validate_line(True, f"Response loader: [cyan]{resp_loader}[/]")
        except Exception as e:
            ui.validate_line(False, f"Response loader: {e}")

        for feat in config.get('features', []):
            source = feat.get('source', 'compute')
            name = feat.get('name', '?')
            try:
                registry.get_feature_source(source)
                if source == 'compute':
                    ext_name = feat.get('extractor', name)
                    ext = registry.get_feature_extractor(ext_name)
                    ui.validate_line(
                        True,
                        f"Feature [yellow]{name}[/]: source={source}, "
                        f"extractor={ext_name} (dims={ext.n_dims})"
                    )
                else:
                    ui.validate_line(True, f"Feature [yellow]{name}[/]: source={source}")
            except Exception as e:
                ui.validate_line(False, f"Feature [yellow]{name}[/]: {e}")

        model_type = config.get('model', {}).get('type', 'bootstrap_ridge')
        try:
            registry.get_model(model_type)
            ui.validate_line(True, f"Model: [cyan]{model_type}[/]")
        except Exception as e:
            ui.validate_line(False, f"Model: {e}")

        ui.success("All checks passed. Ready to run.")
        return 0

    except Exception as e:
        ui.error_panel(str(e))
        return 1


def _cmd_modules(args) -> int:
    """List available pipeline modules."""
    from fmriflow.registry import ModuleRegistry

    registry = _build_registry()
    modules = registry.list_modules()

    ui.console.print()
    ui.modules_table(modules)
    return 0


def _cmd_list(args) -> int:
    """List stages, all modules, or modules for a specific stage."""
    from fmriflow.core.stages import STAGE_MODULE_CATEGORIES
    from fmriflow.core.stages import SUBJECT_STAGES as ALL_STAGES
    from fmriflow.registry import ModuleRegistry

    what = args.what

    if what == 'stages':
        ui.stages_table(list(ALL_STAGES))
        return 0

    registry = _build_registry()
    modules = registry.list_modules()

    if what == 'modules':
        ui.console.print()
        ui.modules_table(modules)
        return 0

    # Treat as a stage name — show modules for that stage
    stage_module_map = {s: STAGE_MODULE_CATEGORIES[s] for s in ALL_STAGES}

    if what not in stage_module_map:
        ui.error_panel(
            f"Unknown stage '{what}'. "
            f"Available stages: {', '.join(ALL_STAGES)}")
        return 1

    categories = stage_module_map[what]
    filtered = {k: modules[k] for k in categories if k in modules}
    ui.console.print()
    ui.modules_table(filtered, title=f"Modules for stage: {what}")
    return 0


def _cmd_serve(args) -> int:
    """Start the frontend server."""
    try:
        import uvicorn
        from fmriflow.server.app import create_app
    except ImportError:
        ui.error_panel(
            "Frontend dependencies not installed.\n"
            "Run: pip install fmriflow[frontend]"
        )
        return 1

    app = create_app(
        results_dir=args.results_dir,
        modules_dir=args.modules_dir,
        configs_dir=args.configs_dir,
        derivatives_dir=args.derivatives_dir,
    )

    ui.console.print(
        f"\n[bold bright_cyan]fMRIflow Server[/] "
        f"starting on [bold]http://{args.host}:{args.port}[/]\n"
    )

    if args.open:
        import webbrowser
        webbrowser.open(f"http://{args.host}:{args.port}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _cmd_compose(args) -> int:
    """Open a config in the frontend composer."""
    import urllib.parse

    config_path = Path(args.config).resolve()
    if not config_path.is_file():
        ui.error_panel(f"Config file not found: {config_path}")
        return 1

    url = f"http://127.0.0.1:{args.port}/#/compose?config={urllib.parse.quote(str(config_path))}"
    ui.console.print(f"\n[bold]Opening composer:[/] {url}\n")

    import webbrowser
    webbrowser.open(url)
    return 0


if __name__ == '__main__':
    sys.exit(main())
