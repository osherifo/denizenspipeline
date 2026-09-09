"""Compatibility shim — ``MaskApplyNode`` now lives in ``fmriflow.preproc.nodes.mask_apply``."""

from fmriflow.modules._decorators import nipype_node
from fmriflow.preproc.nodes.mask_apply import MaskApplyNode

nipype_node("mask_apply")(MaskApplyNode)

__all__ = ["MaskApplyNode"]
