"""HubService — the façade held on ``app.state.hub`` and driven by the route.

Owns the source registry, the per-source local clones under
``paths.hub_cache_dir()``, and orchestrates sync → catalog → install / publish.
Nothing here is imported unless the hub route is hit, so a base install is
unaffected.
"""

from __future__ import annotations

import logging

from fmriflow.core import paths
from fmriflow.hub import catalog, installer, manifest, publisher
from fmriflow.hub.backends import get_backend
from fmriflow.hub.source import HubSource, SourceRegistry

logger = logging.getLogger(__name__)


class HubService:
    def __init__(self) -> None:
        self.registry = SourceRegistry()

    # ── source clones ──

    def clone_dir(self, source: HubSource):
        return paths.hub_cache_dir() / source.id

    def is_synced(self, source: HubSource) -> bool:
        return (self.clone_dir(source) / manifest.MANIFEST_NAME).is_file() or \
               (self.clone_dir(source) / ".git").is_dir()

    def preflight(self) -> list[str]:
        return get_backend("git").preflight()

    # ── status / sources ──

    def sources_snapshot(self) -> dict:
        srcs = []
        for s in self.registry.list_sources():
            srcs.append({
                **s.to_public(),
                "has_token": self.registry.has_token(s.id),
                "synced": self.is_synced(s),
            })
        return {
            "sources": srcs,
            "env_override": self.registry.env_override(),
            "preflight": self.preflight(),
        }

    # ── sync ──

    def sync(self, sid: str) -> dict:
        source = self.registry.get(sid)
        if source is None:
            raise KeyError(f"no source '{sid}'")
        backend = get_backend(source.backend)
        missing = backend.preflight()
        if missing:
            raise RuntimeError("; ".join(missing))
        dest = self.clone_dir(source)
        backend.sync(source.url, source.branch, dest,
                     self.registry.token_for(sid))
        entries = manifest.read_manifest(dest)
        return {"synced": True, "source_id": sid, "artifacts": len(entries)}

    def _synced_entries(self) -> list[tuple[HubSource, list[manifest.ArtifactEntry]]]:
        out = []
        for s in self.registry.list_sources():
            if not s.enabled:
                continue
            dest = self.clone_dir(s)
            if not dest.is_dir():
                continue
            out.append((s, manifest.read_manifest(dest)))
        return out

    # ── catalog ──

    def catalog(self, state, kind: str | None = None) -> list[dict]:
        return catalog.build(self._synced_entries(), state, kind=kind)

    def artifact(self, sid: str, kind: str, name: str, state) -> dict:
        source, entry, dest = self._find(sid, kind, name)
        installed_local = name in installer.local_names(kind, state)
        item = catalog.to_item(source, entry, installed_local)
        # Include a small text preview of the first file when it's not a blob.
        preview = None
        if entry.files and not entry.lfs:
            p = dest / entry.files[0]
            try:
                if p.is_file() and p.stat().st_size < 200_000:
                    preview = p.read_text(errors="replace")
            except OSError:
                preview = None
        item["preview"] = preview
        item["verified"] = manifest.verify(dest, entry)
        return item

    # ── install ──

    def install(self, sid: str, kind: str, name: str, state) -> dict:
        source, entry, dest = self._find(sid, kind, name)
        return installer.install(entry, dest, state, source=source)

    def provenance(self) -> dict:
        from fmriflow.hub import provenance as _p
        return _p.all_records()

    # ── publish ──

    def publish(self, sid: str, kind: str, name: str, state, *,
                author: str = "", description: str = "") -> dict:
        source = self.registry.get(sid)
        if source is None:
            raise KeyError(f"no source '{sid}'")
        dest = self.clone_dir(source)
        if not dest.is_dir():
            self.sync(sid)
        backend = get_backend(source.backend)
        return publisher.publish(
            source, dest, kind, name, state,
            backend=backend, token=self.registry.token_for(sid),
            author=author, description=description,
        )

    # ── helper ──

    def _find(self, sid: str, kind: str, name: str):
        source = self.registry.get(sid)
        if source is None:
            raise KeyError(f"no source '{sid}'")
        dest = self.clone_dir(source)
        for e in manifest.read_manifest(dest):
            if e.kind == kind and e.name == name:
                return source, e, dest
        raise KeyError(f"no artifact {kind}/{name} in source '{sid}' (sync first?)")
