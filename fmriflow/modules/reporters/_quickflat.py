"""Shared pycortex quickflat rendering for flatmap reporters."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def quickflat_png(path, data, **kwargs) -> None:
    """``cortex.quickflat.make_png``, retried without ROI overlays when inkscape is missing.

    pycortex renders ROI outlines and labels through inkscape. Without it the call
    raises, so the flatmap is drawn again with only the curvature and data layers.
    """
    import cortex

    try:
        cortex.quickflat.make_png(str(path), data, **kwargs)
    except Exception as exc:
        if "inkscape" not in str(exc).lower():
            raise
        logger.warning("inkscape is not installed; rendering %s without ROI overlays and labels", path)
        kwargs.update(with_rois=False, with_labels=False)
        cortex.quickflat.make_png(str(path), data, **kwargs)
