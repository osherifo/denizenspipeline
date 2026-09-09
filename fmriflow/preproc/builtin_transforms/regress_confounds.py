"""Compatibility shim — the implementation lives in ``fmriflow.preproc.nodes.regress_confounds``."""

from fmriflow.preproc.nodes.regress_confounds import DEFAULT_COLUMNS, RegressConfoundsTransform
from fmriflow.preproc.transform_registry import register_transform

register_transform("regress_confounds")(RegressConfoundsTransform)

__all__ = ["DEFAULT_COLUMNS", "RegressConfoundsTransform"]
