"""CLI entry point for fmriflow.

Usage:
    fmriflow run experiment.yaml
    fmriflow run experiment.yaml --stages features,preprocess,model
    fmriflow run experiment.yaml --resume-from model
    fmriflow validate experiment.yaml
    fmriflow plugins
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

    # ── validate ──
    validate_parser = subparsers.add_parser(
        'validate', help='Validate a config without running')
    validate_parser.add_argument('config', help='Path to experiment YAML config')

    # ── plugins ──
    subparsers.add_parser('plugins', help='List available plugins')

    # ── list ──
    list_parser = subparsers.add_parser(
        'list', help='List stages, plugins, or plugins for a stage')
    list_parser.add_argument(
        'what', nargs='?', default='stages',
        help=(
            'What to list: "stages" (default), "plugins" (all), '
            'or a stage name to list its plugins'
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
        '--results-dir', type=str, default='./results',
        help='Directory to scan for run summaries')
    serve_parser.add_argument(
        '--no-open', action='store_true',
        help='Do not open browser automatically')
    serve_parser.add_argument(
        '--plugins-dir', type=str, default=None,
        help='Directory for user plugins (default: ~/.fmriflow/plugins/)')
    serve_parser.add_argument(
        '--configs-dir', type=str, default='./experiments',
        help='Directory containing experiment YAML configs (default: ./experiments)')
    serve_parser.add_argument(
        '--derivatives-dir', type=str, default='./derivatives',
        help='Directory containing preprocessing derivatives (default: ./derivatives)')

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

    args = parser.parse_args(argv)

    # Set up logging — suppress standard log format, let rich handle output.
    # Always show logs for preproc commands (they are long-running).
    level = logging.DEBUG if args.verbose else logging.INFO
    show_logs = args.verbose or args.command in ('preproc', 'convert', 'autoflatten')
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

    if args.command == 'run':
        return _cmd_run(args)
    elif args.command == 'validate':
        return _cmd_validate(args)
    elif args.command == 'plugins':
        return _cmd_plugins(args)
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
    else:
        parser.print_help()
        return 1


def _cmd_run(args) -> int:
    """Run the pipeline."""
    from fmriflow.pipeline import Pipeline

    try:
        pipeline = Pipeline.from_yaml(args.config)
    except Exception as e:
        ui.error_panel(str(e))
        return 1

    # Override subject if specified
    if args.subject:
        pipeline.config['subject'] = args.subject

    # Set up file logging to {output_dir}/pipeline.log
    output_dir = pipeline.config.get('reporting', {}).get(
        'output_dir', './results')
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
    from fmriflow.registry import PluginRegistry

    try:
        config = load_config(args.config)
        ui.console.print(f"\n[bold]Validating[/] {args.config}\n")

        ui.validate_line(True, f"Config loaded")
        ui.validate_line(True, f"Experiment: {config.get('experiment')}")
        ui.validate_line(True, f"Subject: {config.get('subject')}")

        # Check plugins
        registry = PluginRegistry()
        registry.discover()

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


def _cmd_plugins(args) -> int:
    """List available plugins."""
    from fmriflow.registry import PluginRegistry

    registry = PluginRegistry()
    registry.discover()
    plugins = registry.list_plugins()

    ui.console.print()
    ui.plugins_table(plugins)
    return 0


def _cmd_list(args) -> int:
    """List stages, all plugins, or plugins for a specific stage."""
    from fmriflow.orchestrator import ALL_STAGES
    from fmriflow.registry import PluginRegistry

    what = args.what

    if what == 'stages':
        ui.stages_table(ALL_STAGES)
        return 0

    registry = PluginRegistry()
    registry.discover()
    plugins = registry.list_plugins()

    if what == 'plugins':
        ui.console.print()
        ui.plugins_table(plugins)
        return 0

    # Treat as a stage name — show plugins for that stage
    stage_plugin_map = {
        'stimuli': ['stimulus_loaders'],
        'responses': ['response_loaders', 'response_readers'],
        'features': ['feature_extractors', 'feature_sources'],
        'preprocess': ['preprocessors', 'preprocessing_steps'],
        'model': ['models'],
        'analyze': ['analyzers'],
        'report': ['reporters'],
    }

    if what not in stage_plugin_map:
        ui.error_panel(
            f"Unknown stage '{what}'. "
            f"Available stages: {', '.join(ALL_STAGES)}")
        return 1

    categories = stage_plugin_map[what]
    filtered = {k: plugins[k] for k in categories if k in plugins}
    ui.console.print()
    ui.plugins_table(filtered, title=f"Plugins for stage: {what}")
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
        plugins_dir=args.plugins_dir,
        configs_dir=args.configs_dir,
        derivatives_dir=args.derivatives_dir,
    )

    ui.console.print(
        f"\n[bold bright_cyan]fMRIflow Server[/] "
        f"starting on [bold]http://{args.host}:{args.port}[/]\n"
    )

    if not args.no_open:
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
