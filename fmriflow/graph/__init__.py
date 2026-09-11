"""Graph core shared by the preprocessing and analysis pipelines.

A pipeline is a DAG of typed nodes drawn from a registry. This package
holds the parts that do not depend on what the nodes *do*: the
ReactFlow-compatible node/edge/graph model and its YAML round-trip,
topology, structural validation, port specs with type compatibility, and
bundled/user template tiers. Preprocessing (:mod:`fmriflow.preproc.graph`)
and analysis subclass these.
"""

from fmriflow.graph.model import (
    INPUT_REF_PREFIX,
    SCHEMA_VERSION,
    EdgeSpec,
    GraphSpec,
    NodeSpec,
)
from fmriflow.graph.ports import (
    PortSpec,
    TypeLattice,
    accepts_many,
    normalize_ports,
    port_type,
)
from fmriflow.graph.templates import TemplateTiers, concrete_path_warnings, validate_slug

__all__ = [
    "INPUT_REF_PREFIX", "SCHEMA_VERSION", "EdgeSpec", "GraphSpec", "NodeSpec",
    "PortSpec", "TypeLattice", "accepts_many", "normalize_ports", "port_type",
    "TemplateTiers", "concrete_path_warnings", "validate_slug",
]
