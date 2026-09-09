"""Compatibility shim — the implementation lives in ``fmriflow.preproc.nodes.identity``."""

from fmriflow.preproc.nodes.identity import IdentityTransform
from fmriflow.preproc.transform_registry import register_transform

register_transform("identity")(IdentityTransform)

__all__ = ["IdentityTransform"]
