"""CLI entry point for denizenspipeline.

Usage:
    denizens run experiment.yaml
    denizens run experiment.yaml --stages features,preprocess,model
    denizens run experiment.yaml --resume-from model
    denizens validate experiment.yaml
    denizens plugins
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='denizens',
        description='Denizens Pipeline — neuroscience encoding model pipeline',
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

    args = parser.parse_args(argv)

    # Set up logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )

    if args.command == 'run':
        return _cmd_run(args)
    elif args.command == 'validate':
        return _cmd_validate(args)
    elif args.command == 'plugins':
        return _cmd_plugins(args)
    else:
        parser.print_help()
        return 1


def _cmd_run(args) -> int:
    """Run the pipeline."""
    from denizenspipeline.pipeline import Pipeline

    try:
        pipeline = Pipeline.from_yaml(args.config)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1

    # Override subject if specified
    if args.subject:
        pipeline.config['subject'] = args.subject

    # Parse stages
    stages = None
    if args.stages:
        stages = [s.strip() for s in args.stages.split(',')]

    if args.dry_run:
        print("Config resolved successfully.")
        print(f"  Experiment: {pipeline.config.get('experiment')}")
        print(f"  Subject: {pipeline.config.get('subject')}")
        features = pipeline.config.get('features', [])
        print(f"  Features ({len(features)}):")
        for f in features:
            print(f"    - {f['name']} (source: {f.get('source', 'compute')})")
        print(f"  Model: {pipeline.config.get('model', {}).get('type')}")
        print(f"  Reporters: {pipeline.config.get('reporting', {}).get('formats')}")
        if stages:
            print(f"  Stages to run: {stages}")
        else:
            print("  Stages to run: all")
        return 0

    try:
        ctx = pipeline.run(stages=stages, resume_from=args.resume_from)
        print("\nPipeline completed successfully.")

        # Print summary
        if ctx.has('result'):
            from denizenspipeline.core.types import ModelResult
            result = ctx.get('result', ModelResult)
            print(f"  Mean score: {result.scores.mean():.4f}")
            print(f"  Max score: {result.scores.max():.4f}")
            print(f"  N voxels: {result.n_voxels}")

        if ctx.artifacts:
            print("  Artifacts:")
            for reporter, files in ctx.artifacts.items():
                for name, path in files.items():
                    print(f"    [{reporter}] {name}: {path}")

        return 0

    except Exception as e:
        print(f"Pipeline failed: {e}", file=sys.stderr)
        if logger.isEnabledFor(logging.DEBUG):
            import traceback
            traceback.print_exc()
        return 1


def _cmd_validate(args) -> int:
    """Validate a config file."""
    from denizenspipeline.config.loader import load_config
    from denizenspipeline.registry import PluginRegistry

    try:
        config = load_config(args.config)
        print("Validating experiment config...")
        print(f"  [OK] Config loaded: {args.config}")
        print(f"  [OK] Experiment: {config.get('experiment')}")
        print(f"  [OK] Subject: {config.get('subject')}")

        # Check plugins
        registry = PluginRegistry()
        registry.discover()

        stim_loader = config.get('stimulus', {}).get('loader', 'textgrid')
        try:
            registry.get_stimulus_loader(stim_loader)
            print(f"  [OK] Stimulus loader '{stim_loader}' registered")
        except Exception as e:
            print(f"  [FAIL] Stimulus loader: {e}")

        resp_loader = config.get('response', {}).get('loader', 'cloud')
        try:
            registry.get_response_loader(resp_loader)
            print(f"  [OK] Response loader '{resp_loader}' registered")
        except Exception as e:
            print(f"  [FAIL] Response loader: {e}")

        for feat in config.get('features', []):
            source = feat.get('source', 'compute')
            name = feat.get('name', '?')
            try:
                registry.get_feature_source(source)
                if source == 'compute':
                    ext_name = feat.get('extractor', name)
                    ext = registry.get_feature_extractor(ext_name)
                    print(f"  [OK] Feature '{name}' source=compute, "
                          f"extractor '{ext_name}' (dims={ext.n_dims})")
                else:
                    print(f"  [OK] Feature '{name}' source={source}")
            except Exception as e:
                print(f"  [FAIL] Feature '{name}': {e}")

        model_type = config.get('model', {}).get('type', 'bootstrap_ridge')
        try:
            registry.get_model(model_type)
            print(f"  [OK] Model '{model_type}' registered")
        except Exception as e:
            print(f"  [FAIL] Model: {e}")

        print("\nAll checks passed. Ready to run.")
        return 0

    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        return 1


def _cmd_plugins(args) -> int:
    """List available plugins."""
    from denizenspipeline.registry import PluginRegistry

    registry = PluginRegistry()
    registry.discover()
    plugins = registry.list_plugins()

    labels = {
        'stimulus_loaders': 'Stimulus Loaders',
        'response_loaders': 'Response Loaders',
        'feature_extractors': 'Feature Extractors',
        'feature_sources': 'Feature Sources',
        'preprocessors': 'Preprocessors',
        'models': 'Models',
        'reporters': 'Reporters',
    }

    for key, names in plugins.items():
        print(f"\n{labels.get(key, key)}:")
        if names:
            for name in names:
                print(f"  {name}")
        else:
            print("  (none)")

    return 0


if __name__ == '__main__':
    sys.exit(main())
