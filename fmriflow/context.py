"""PipelineContext — shared state container for pipeline stages."""

from __future__ import annotations

import logging
import pickle
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeVar

from fmriflow.exceptions import PipelineError

if TYPE_CHECKING:
    from fmriflow.core.run_summary import NodeRecord

T = TypeVar("T")

logger = logging.getLogger(__name__)


class PipelineContext:
    """Shared state container for pipeline stages.

    Stores stage outputs with typed access and supports checkpointing.
    """

    def __init__(self, config: dict):
        self.config = config
        self._store: dict[str, Any] = {}
        self._artifacts: dict[str, dict[str, str]] = {}
        self._timestamps: dict[str, float] = {}
        # Cache the resolved ``intermediates`` block so each stage hook
        # doesn't re-parse the config.
        self._intermediates_cfg: dict | None = None

    def put(self, key: str, value: Any) -> None:
        """Store a stage output."""
        self._store[key] = value
        self._timestamps[key] = time.time()

    # ─── Intermediate dumps (opt-in QA) ─────────────────────────

    def _intermediates(self) -> dict:
        """Resolve and cache the ``intermediates`` config block.

        Imported lazily so :mod:`fmriflow.intermediates` (which pulls
        joblib) only loads when the feature is touched.
        """
        if self._intermediates_cfg is not None:
            return self._intermediates_cfg
        from fmriflow.intermediates import resolve_save_set

        block = self.config.get('intermediates') or {}
        if not isinstance(block, dict):
            logger.warning(
                "config.intermediates must be a dict — ignoring %r", block,
            )
            block = {}
        cfg = {
            'save_set': resolve_save_set(block.get('save')),
            'format': block.get('format', 'joblib'),
            'compress': block.get('compress', 'lz4'),
        }
        self._intermediates_cfg = cfg
        return cfg

    def dump_intermediate(
        self,
        stage: str,
        value: Any,
        node_rec: "NodeRecord | None" = None,
    ) -> Path | None:
        """Dump ``value`` to disk if the config has opted this stage in.

        Returns the path written (or ``None`` if disabled / skipped /
        failed). When ``node_rec`` is provided, the dump's path
        (relative to the run dir when possible) is appended to
        ``node_rec.outputs`` so the existing graph viewer's Outputs tab
        surfaces it without any new endpoint.

        Failures are logged but never raised — a QA-only feature must
        never break the pipeline that produced the data.
        """
        cfg = self._intermediates()
        if stage not in cfg['save_set']:
            return None

        from fmriflow import intermediates as _im

        output_dir = (self.config.get('reporting') or {}).get('output_dir')
        if not output_dir:
            logger.warning(
                "intermediates: no reporting.output_dir set; "
                "skipping dump for stage '%s'", stage,
            )
            return None

        path = _im.output_path(output_dir, stage, compress=cfg['compress'])
        try:
            _im.dump(value, path, compress=cfg['compress'])
        except Exception:
            logger.warning(
                "intermediates: failed to dump stage '%s' to %s",
                stage, path, exc_info=True,
            )
            return None

        if node_rec is not None:
            # The path is always ``<output_dir>/intermediates/<file>`` —
            # surface the run-dir-relative form so the graph viewer's
            # Outputs tab can fetch it via the existing per-node file
            # endpoint.
            node_rec.outputs.append(f'intermediates/{path.name}')
        return path

    # ─── Per-stage QA viz (opt-in) ──────────────────────────────

    def _qa_config(self) -> dict:
        """Resolve and cache the ``qa:`` config block.

        Resolved once per pipeline run. Returned shape::

            {
                'enabled': bool,
                'stages': set[str],        # which stages to QA
                'per_stage': dict,         # {stage: {'plugins': [...]}}
                'output_subdir': str,
            }
        """
        if hasattr(self, '_qa_cfg') and self._qa_cfg is not None:
            return self._qa_cfg
        block = self.config.get('qa') or {}
        if not isinstance(block, dict):
            logger.warning("config.qa must be a dict — ignoring %r", block)
            block = {}
        stages_spec = block.get('stages')
        # ``stages: true`` (or missing while enabled=True) → all stages
        # that have any registered plugin. We resolve "all" lazily at
        # runtime against the live registry, so encode it as a sentinel.
        if stages_spec in (True, None):
            stages_set: set[str] | str = 'all'
        elif isinstance(stages_spec, (list, tuple, set)):
            stages_set = {str(s) for s in stages_spec}
        elif isinstance(stages_spec, str):
            stages_set = {stages_spec}
        else:
            stages_set = set()
        per_stage = {
            k: v for k, v in block.items()
            if isinstance(v, dict)
        }
        self._qa_cfg = {
            'enabled': bool(block.get('enabled', False)),
            'stages': stages_set,
            'per_stage': per_stage,
            'output_subdir': str(block.get('output_subdir', 'qa')),
        }
        return self._qa_cfg

    def run_stage_qa(
        self,
        stage: str,
        value: Any,
        node_rec: "NodeRecord | None" = None,
    ) -> list[str]:
        """Run every registered QA reporter for ``stage`` over ``value``.

        Writes artifacts to ``<run_dir>/<qa.output_subdir>/<stage>/<plugin>/``
        and returns the list of artifact paths (one entry per produced
        file, run-dir-relative). Every plugin runs in isolation — a
        single failing plot logs a warning and does not affect others
        or the pipeline itself.

        Resolution of which plugins to run:

        - If ``qa.enabled`` is False → no-op.
        - If ``stage`` not in ``qa.stages`` (and ``stages`` isn't
          ``'all'``) → no-op.
        - Otherwise, look up ``qa.<stage>.plugins`` for an explicit
          subset; default to every registered plugin for the stage.
        """
        cfg = self._qa_config()
        if not cfg['enabled']:
            return []
        stages = cfg['stages']
        if stages != 'all' and stage not in stages:
            return []
        # Lazy import — registry pulls a lot of plugin code.
        from fmriflow.modules._decorators import _qa_reporters

        plugins = _qa_reporters.get(stage, {})
        if not plugins:
            return []
        # Per-stage plugin selection.
        stage_block = cfg['per_stage'].get(stage) or {}
        wanted = stage_block.get('plugins')
        if isinstance(wanted, list):
            selected = [(p, plugins[p]) for p in wanted if p in plugins]
            unknown = [p for p in wanted if p not in plugins]
            if unknown:
                logger.warning(
                    "qa.%s.plugins: unknown plugin(s) %s — available: %s",
                    stage, unknown, sorted(plugins.keys()),
                )
        else:
            selected = list(plugins.items())

        output_dir = (self.config.get('reporting') or {}).get('output_dir')
        if not output_dir:
            logger.warning(
                "qa: no reporting.output_dir set; skipping stage '%s'", stage,
            )
            return []
        stage_dir = Path(output_dir) / cfg['output_subdir'] / stage

        produced: list[str] = []
        for plugin_name, plugin_cls in selected:
            plugin_dir = stage_dir / plugin_name
            try:
                plugin = plugin_cls()
                # Per-plugin params from config, if provided. Skip for
                # v1 — plugins read what they need from ``config``.
                artifacts = plugin.report(value, self.config, plugin_dir) or {}
            except Exception:
                logger.warning(
                    "qa: %s/%s failed — skipping", stage, plugin_name,
                    exc_info=True,
                )
                continue
            for _, path in artifacts.items():
                try:
                    rel = str(
                        Path(path).resolve().relative_to(
                            Path(output_dir).resolve())
                    )
                except (ValueError, OSError):
                    rel = str(path)
                produced.append(rel)
        if produced and node_rec is not None:
            # Surface QA outputs separately from the node's regular
            # outputs so the existing Outputs tab stays uncluttered.
            # ``qa_outputs`` is a declared NodeRecord field — extends
            # cleanly across multiple calls if the same stage runs
            # several reporters that contribute paths.
            node_rec.qa_outputs.extend(produced)
        return produced

    def get(self, key: str, expected_type: type[T] | None = None) -> T:
        """Retrieve a stage output with optional type checking.

        Raises
        ------
        PipelineError
            If key not found or type mismatch.
        """
        if key not in self._store:
            raise PipelineError(
                f"'{key}' not found in context. "
                f"Was the required stage run?")
        value = self._store[key]
        if expected_type is not None and not isinstance(value, expected_type):
            raise PipelineError(
                f"Expected {expected_type.__name__}, "
                f"got {type(value).__name__}")
        return value

    def has(self, key: str) -> bool:
        """Check if a key exists in the context."""
        return key in self._store

    def add_artifacts(self, reporter_name: str,
                      artifacts: dict[str, str]) -> None:
        """Store artifacts produced by a reporter."""
        self._artifacts[reporter_name] = artifacts

    @property
    def artifacts(self) -> dict[str, dict[str, str]]:
        """All stored artifacts."""
        return dict(self._artifacts)

    # ─── Checkpointing ──────────────────────────────────────────

    def save_checkpoint(self, stage_name: str) -> Path:
        """Save context state to disk for resuming.

        Returns
        -------
        Path
            Path to the checkpoint file.
        """
        output_dir = self.config.get('reporting', {}).get('output_dir', './results')
        checkpoint_dir = Path(output_dir) / '.checkpoints'
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = checkpoint_dir / f'{stage_name}.pkl'
        with open(path, 'wb') as f:
            pickle.dump(self._store, f)
        return path

    @classmethod
    def from_checkpoint(cls, config: dict, stage_name: str) -> PipelineContext:
        """Resume from a previously saved checkpoint.

        Parameters
        ----------
        config : dict
            Pipeline configuration.
        stage_name : str
            Name of the stage checkpoint to restore.

        Returns
        -------
        PipelineContext
            Restored context.
        """
        ctx = cls(config)
        output_dir = config.get('reporting', {}).get('output_dir', './results')
        path = Path(output_dir) / '.checkpoints' / f'{stage_name}.pkl'
        with open(path, 'rb') as f:
            ctx._store = pickle.load(f)
        return ctx
