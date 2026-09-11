"""Port specs and type compatibility.

A port spec is a plain dict so node classes can declare ports inline::

    INPUTS = {"prepared": {"type": "PreparedData", "required": True},
              "features": {"type": "FeatureSet", "multiple": True}}

``kind`` is the preprocessing name for the same idea (``"nifti"``,
``"dir"``, ...) and is accepted wherever ``type`` is.
"""

from __future__ import annotations

from typing import Any, Iterable

PortSpec = dict[str, Any]

ANY = "any"


def normalize_ports(spec: Any, *, default_kind: str = ANY) -> dict[str, PortSpec]:
    """Coerce ``INPUTS`` / ``OUTPUTS`` into ``{port: {"kind", "required", ...}}``.

    Accepts a dict of port specs, a list of port names, or ``None``.
    """
    if not spec:
        return {}
    if isinstance(spec, dict):
        out: dict[str, PortSpec] = {}
        for port, ps in spec.items():
            ps = dict(ps or {})
            ps.setdefault("kind", default_kind)
            ps.setdefault("required", False)
            out[str(port)] = ps
        return out
    return {str(p): {"kind": default_kind, "required": False} for p in spec}


def port_type(spec: PortSpec | None) -> str:
    """The port's type name: ``type``, else ``kind``, else ``"any"``."""
    spec = spec or {}
    return str(spec.get("type") or spec.get("kind") or ANY)


def accepts_many(spec: PortSpec | None) -> bool:
    """True when an input port takes several incoming edges (ordered fan-in)."""
    return bool((spec or {}).get("multiple"))


class TypeLattice:
    """Named port types with single or multiple parents.

    ``compatible(src, dst)`` holds when either side is ``"any"`` or ``dst``
    is ``src`` or one of its ancestors, so an output of a more specific type
    can feed an input that asks for a more general one.
    """

    def __init__(self) -> None:
        self._parents: dict[str, tuple[str, ...]] = {ANY: ()}

    def register(self, name: str, parents: Iterable[str] = ()) -> None:
        self._parents[name] = tuple(parents)
        for parent in self._parents[name]:
            self._parents.setdefault(parent, ())

    def names(self) -> list[str]:
        return sorted(self._parents)

    def has(self, name: str) -> bool:
        return name in self._parents

    def ancestors(self, name: str) -> set[str]:
        seen: set[str] = set()
        stack = [name]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(self._parents.get(cur, ()))
        return seen

    def compatible(self, src: str, dst: str) -> bool:
        if src == ANY or dst == ANY:
            return True
        return dst in self.ancestors(src)

    def to_dict(self) -> dict[str, list[str]]:
        return {name: list(parents) for name, parents in sorted(self._parents.items())}
