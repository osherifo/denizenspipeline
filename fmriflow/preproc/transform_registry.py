"""Deprecated — ``@register_transform`` is now an alias of ``@preproc_node``.
Addon files under ``$FMRIFLOW_HOME/addons/transforms/`` keep loading through
the node library.
"""

from __future__ import annotations

import warnings


def register_transform(name: str):
    def wrapper(cls: type) -> type:
        warnings.warn(
            "@register_transform is deprecated; use @preproc_node from fmriflow.preproc.node_registry",
            DeprecationWarning, stacklevel=2,
        )
        from fmriflow.preproc.node_registry import preproc_node
        return preproc_node(name, kind="interface")(cls)
    return wrapper


__all__ = ["register_transform"]
