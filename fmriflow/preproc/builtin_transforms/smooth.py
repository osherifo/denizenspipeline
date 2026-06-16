"""Smooth — register the existing ``SmoothNode`` as a Transform.

The implementation lives in ``fmriflow.modules.nipype_nodes.smooth``
because the same class is useful in *two* places:

- The post-preproc DAG builder (registered via ``@nipype_node``).
- The preproc-stack runner as a Stage-N transform (registered here).

Both registrations point at the same class object — there's no
behavioural divergence, only two registries to look up by name.
This proxy-registration pattern keeps the dependency direction
clean: ``preproc → modules``, never the reverse.
"""

from __future__ import annotations

from fmriflow.modules.nipype_nodes.smooth import SmoothNode
from fmriflow.preproc.transform_registry import register_transform


# Decorators are just function calls; this is equivalent to writing
# ``@register_transform("smooth")`` above the class definition, but
# we don't own the class — we're just adding our registry's pointer.
register_transform("smooth")(SmoothNode)
