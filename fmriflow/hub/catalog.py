"""Catalog assembly — turn synced source manifests into UI-ready items,
each tagged with its source/tier and whether it's already installed locally.
"""

from __future__ import annotations

from fmriflow.hub.installer import local_names
from fmriflow.hub.manifest import ArtifactEntry
from fmriflow.hub.source import HubSource


def to_item(source: HubSource, entry: ArtifactEntry, installed: bool) -> dict:
    return {
        "source_id": source.id,
        "source_name": source.name,
        "tier": source.tier,                 # "lab" | "community"
        "kind": entry.kind,
        "name": entry.name,
        "version": entry.version,
        "description": entry.description,
        "author": entry.author,
        "tags": entry.tags,
        "size": entry.size,
        "lfs": entry.lfs,
        "sha256": entry.sha256,
        "files": entry.files,
        "metadata": entry.metadata,
        "installed": installed,
    }


def build(sources_entries: list[tuple[HubSource, list[ArtifactEntry]]],
          state, kind: str | None = None) -> list[dict]:
    """Merge per-source entries into a flat, installed-tagged catalog."""
    # Cache local-name sets per kind so we don't rescan repeatedly.
    local_cache: dict[str, set[str]] = {}
    items: list[dict] = []
    for source, entries in sources_entries:
        for e in entries:
            if kind and e.kind != kind:
                continue
            if e.kind not in local_cache:
                local_cache[e.kind] = local_names(e.kind, state)
            installed = e.name in local_cache[e.kind]
            items.append(to_item(source, e, installed))
    items.sort(key=lambda i: (i["kind"], i["name"], i["tier"]))
    return items
