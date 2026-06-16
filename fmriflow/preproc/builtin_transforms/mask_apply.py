"""mask_apply — register the existing ``MaskApplyNode`` as a Transform.

See ``smooth.py`` in this package for the proxy-registration
rationale. Same class, two registries.
"""

from __future__ import annotations

from fmriflow.modules.nipype_nodes.mask_apply import MaskApplyNode
from fmriflow.preproc.transform_registry import register_transform


register_transform("mask_apply")(MaskApplyNode)
