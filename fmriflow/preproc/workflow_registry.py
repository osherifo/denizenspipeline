"""Deprecated — ``@register_preproc_workflow`` is now an alias of
``@preproc_node(name, kind="composite")``. Addon files under
``$FMRIFLOW_HOME/addons/workflows/`` keep loading through the node library.
"""

from __future__ import annotations

import warnings


def register_preproc_workflow(name: str):
    def wrapper(cls: type) -> type:
        warnings.warn(
            "@register_preproc_workflow is deprecated; use "
            "@preproc_node(name, kind='composite') from fmriflow.preproc.node_registry",
            DeprecationWarning, stacklevel=2,
        )
        from fmriflow.preproc.node_registry import preproc_node
        return preproc_node(name, kind="composite")(cls)
    return wrapper


__all__ = ["register_preproc_workflow"]
