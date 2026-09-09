"""Built-in preprocessing nodes.

Every module here registers one or more nodes via
``@preproc_node("<name>", kind=...)``. :class:`~fmriflow.preproc.node_registry.NodeRegistry`
imports each module on ``discover()`` so the decorators fire.

To add a built-in node: drop a ``.py`` file here with a decorated class.
User nodes go under ``$FMRIFLOW_HOME/addons/nodes/`` instead and never
into this package.
"""
