"""Helpers shared across QA reporter plugins."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def ensure_dir(path: Path | str) -> Path:
    """Create ``path`` if missing and return it as a Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def mpl_figure(*, figsize: tuple[float, float] = (6.0, 4.0), dpi: int = 110):
    """Open a matplotlib Figure on the Agg backend and tear it down.

    Forces the Agg backend so QA viz works in headless server contexts
    without an X display. Imports matplotlib lazily so the QA package
    can be imported without pulling matplotlib.
    """
    import matplotlib
    matplotlib.use('Agg', force=False)
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=figsize, dpi=dpi)
    try:
        yield fig
    finally:
        plt.close(fig)


def save_png(fig, path: Path) -> str:
    """Save ``fig`` to ``path`` as PNG and return the string path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), bbox_inches='tight', dpi=fig.dpi)
    return str(path)


def banded_groups(result) -> dict[str, tuple[int, int]] | None:
    """Return ``{band_name: (start, end)}`` from a banded ModelResult.

    Returns ``None`` when the result isn't banded. The himalaya backend
    stores band column ranges under ``metadata['groups']`` as a
    ``{name: range_or_slice_or_(start,end)}`` mapping.
    """
    meta = getattr(result, 'metadata', None) or {}
    groups = meta.get('groups')
    if not isinstance(groups, dict) or not groups:
        return None
    out: dict[str, tuple[int, int]] = {}
    for name, spec in groups.items():
        if isinstance(spec, slice):
            out[str(name)] = (int(spec.start or 0), int(spec.stop or 0))
        elif isinstance(spec, range):
            out[str(name)] = (int(spec.start), int(spec.stop))
        elif (isinstance(spec, (list, tuple)) and len(spec) == 2
              and all(isinstance(v, (int, float)) for v in spec)):
            out[str(name)] = (int(spec[0]), int(spec[1]))
        else:
            # Unknown shape — bail out cleanly.
            return None
    return out


def feature_column_layout(result_or_prepared) -> list[tuple[str, int, int, int]]:
    """Return ``[(feature_name, delay_idx, col_start, col_end), …]``.

    Mirrors how the preparer lays out X columns: features are
    concatenated in order, each followed by its full set of delayed
    copies. Used by both prepare- and model-stage QA plots that want
    to colour columns by (feature, delay).
    """
    feature_names = list(getattr(result_or_prepared, 'feature_names', []) or [])
    feature_dims = list(getattr(result_or_prepared, 'feature_dims', []) or [])
    delays = list(getattr(result_or_prepared, 'delays', []) or [1])
    out: list[tuple[str, int, int, int]] = []
    col = 0
    for name, n_dims in zip(feature_names, feature_dims):
        for di, _ in enumerate(delays):
            out.append((name, di, col, col + n_dims))
            col += n_dims
    return out
