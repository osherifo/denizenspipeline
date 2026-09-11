"""Persist + reload per-stage intermediate dataclasses for QA.

Opt-in via the ``intermediates`` block in a subject-scope config:

.. code-block:: yaml

    intermediates:
      save: false              # bool | list[str]   (default off)
      # save: true                                  # everything
      # save: [features, prepare]                   # selective by stage name
      format: joblib                                # only one in v1
      compress: lz4                                 # lz4 | gzip | none

Stage names map 1:1 to the subject pipeline stages whose
``ctx.put(...)`` produces a dataclass we can dump:

    ``stimuli``     — :class:`fmriflow.core.types.StimulusData`
    ``responses``   — :class:`fmriflow.core.types.ResponseData`
    ``features``    — :class:`fmriflow.core.types.FeatureData`
    ``prepare``     — :class:`fmriflow.core.types.PreparedData`
    ``model``       — :class:`fmriflow.core.types.ModelResult`

The orchestrator calls :func:`PipelineContext.dump_intermediate` right
after each stage's ``put(...)``. Dumps land in
``<run_dir>/intermediates/<stage>.joblib`` (or ``.joblib.gz`` /
``.joblib.lz4`` depending on compression) and the path is appended to
the stage's :class:`NodeRecord.outputs` so it shows up in the existing
graph viewer's Outputs tab — no new endpoint or UI work needed.

Reload with :func:`load`. The format is plain ``joblib`` (pickle under
the hood) — Python-only and tied to the current dataclass shape. v2
may add HDF5 if we ever need cross-language consumers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _import_joblib():
    """Lazy joblib import — only required for dump/load, not for
    importing SAVEABLE_STAGES (which the config schema validator
    pulls in for every config check, regardless of whether the
    user wants intermediates). joblib is not in the base
    ``pyproject.toml`` dependencies, so a base install must be
    able to import this module without it."""
    try:
        import joblib
        return joblib
    except ImportError as exc:
        raise ImportError(
            "fmriflow.intermediates: 'joblib' is required for the "
            "intermediates feature. Install it directly (`pip install "
            "joblib`) or pull in an extra that depends on it "
            "(`pip install fmriflow[ml]` / `fmriflow[himalaya]`)."
        ) from exc

# Stages the orchestrator can hand off to dump(). The literal names are
# the same as the orchestrator's stage names so configs can request
# them by stage. ``True`` in ``save:`` expands to this set.
from fmriflow.core.stages import SAVEABLE_STAGES  # noqa: E402,F401

_LZ4_WARNED = False


def _joblib_compress(spec: str | int | None) -> int | tuple[str, int]:
    """Translate a config ``compress:`` value to joblib's argument shape.

    ``lz4`` falls back to ``gzip`` (with a one-shot warning) when the
    ``lz4`` package isn't installed — joblib's lz4 path requires it.
    """
    global _LZ4_WARNED
    if spec in (None, False, 'none', 'off', 0):
        return 0
    if spec is True or spec == 'lz4':
        try:
            import lz4  # noqa: F401  – only used to confirm availability
            return ('lz4', 3)
        except ImportError:
            if not _LZ4_WARNED:
                logger.warning(
                    "intermediates: 'lz4' compression requested but the "
                    "lz4 package is not installed — falling back to gzip"
                )
                _LZ4_WARNED = True
            return ('gzip', 3)
    if spec == 'gzip':
        return ('gzip', 3)
    if isinstance(spec, int):
        return max(0, min(9, spec))
    logger.warning(
        "intermediates: unknown compress spec %r — using gzip", spec,
    )
    return ('gzip', 3)


def _suffix_for(spec: str | int | None) -> str:
    """File suffix that hints at the compression used."""
    if spec in (None, False, 'none', 'off', 0):
        return '.joblib'
    if spec is True or spec == 'lz4':
        try:
            import lz4  # noqa: F401
            return '.joblib.lz4'
        except ImportError:
            return '.joblib.gz'
    if spec == 'gzip':
        return '.joblib.gz'
    return '.joblib.gz'


def resolve_save_set(spec: Any) -> set[str]:
    """Turn the config ``save:`` value into a concrete set of stage names.

    ``False`` / missing → empty set; ``True`` → every saveable stage;
    a list is filtered to known stages with a warning for unknown ones.
    """
    if spec in (None, False, '', 0):
        return set()
    if spec is True:
        return set(SAVEABLE_STAGES)
    if isinstance(spec, (list, tuple, set)):
        out: set[str] = set()
        for name in spec:
            if name in SAVEABLE_STAGES:
                out.add(name)
            else:
                logger.warning(
                    "intermediates.save: '%s' is not a recognised stage "
                    "(known: %s) — ignoring",
                    name, ', '.join(SAVEABLE_STAGES),
                )
        return out
    if isinstance(spec, str) and spec in SAVEABLE_STAGES:
        return {spec}
    logger.warning(
        "intermediates.save: unrecognised value %r — ignoring", spec,
    )
    return set()


def dump(obj: Any, path: Path, *, compress: str | int | None = 'lz4') -> Path:
    """Joblib-dump ``obj`` to ``path``, creating parent dirs as needed."""
    joblib = _import_joblib()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, str(path), compress=_joblib_compress(compress))
    return path


def load(path: Path | str) -> Any:
    """Counterpart to :func:`dump` — read a saved intermediate back."""
    joblib = _import_joblib()
    return joblib.load(str(path))


def output_path(run_dir: Path | str, stage: str,
                compress: str | int | None = 'lz4') -> Path:
    """Resolve the on-disk path used for a stage's dump."""
    return Path(run_dir) / 'intermediates' / f'{stage}{_suffix_for(compress)}'


def load_intermediate(run_dir: Path | str, stage: str) -> Any:
    """Convenience: load a stage's intermediate without knowing the suffix.

    Tries the known compression suffixes in turn; raises FileNotFoundError
    if nothing matches.
    """
    base = Path(run_dir) / 'intermediates'
    for suffix in ('.joblib.lz4', '.joblib.gz', '.joblib'):
        candidate = base / f'{stage}{suffix}'
        if candidate.is_file():
            return load(candidate)
    raise FileNotFoundError(
        f"no intermediate dump for stage '{stage}' under {base}"
    )
