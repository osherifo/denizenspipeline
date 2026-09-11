"""Analysis as a node graph.

Every analysis module (stimulus loaders, feature extractors, preparers,
models, analyzers, reporters, group and study modules) is a node type in
the :class:`~fmriflow.analysis.catalog.NodeCatalog`. Modules written for
the fixed-stage pipeline run unchanged through category adapters
(:mod:`fmriflow.analysis.adapters`); modules can also declare ports and a
``run`` method directly. Values on edges are the typed data classes from
:mod:`fmriflow.core.types` plus a ``Context`` mapping for modules that read
and write context keys.
"""
