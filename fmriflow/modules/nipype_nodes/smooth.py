"""Compatibility shim — ``SmoothNode`` now lives in ``fmriflow.preproc.nodes.smooth``."""

from fmriflow.modules._decorators import nipype_node
from fmriflow.preproc.nodes.smooth import SmoothNode

nipype_node("smooth")(SmoothNode)

__all__ = ["SmoothNode"]
