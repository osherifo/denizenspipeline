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


def _is_empty_clone(dest) -> bool:
    """A freshly-cloned empty (commit-less) repo has only .git in its tree."""
    try:
        return not any(p.name != ".git" for p in dest.iterdir())
    except OSError:
        return True


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
        from fmriflow.hub.source import keyring_available
        srcs = []
        for s in self.registry.list_sources():
            srcs.append({
                **s.to_public(),
                "has_token": self.registry.has_token(s.id),
                "token_storage": self.registry.token_storage(s.id),
                "synced": self.is_synced(s),
            })
        return {
            "sources": srcs,
            "env_override": self.registry.env_override(),
            "preflight": self.preflight(),
            "keyring_available": keyring_available(),
        }

    # Kinds that can be published from the local tier (feature_array blobs are
    # excluded — they're pushed by path, not from a named local artifact).
    PUBLISHABLE_KINDS = (
        "analysis_config", "workflow_config",
        "convert_config", "preproc_config", "autoflatten_config",
        "module", "heuristic",
        "stack_preset", "transform", "workflow", "error",
    )

    def local_artifacts(self, state) -> dict:
        """Local artifacts available to publish, grouped by kind.

        Only **user-tier** items are publishable — a builtin module/heuristic
        has no user-tier file to push — so those two kinds are narrowed to the
        user addon dirs rather than the full registry.
        """
        out: dict[str, list[str]] = {}
        for kind in self.PUBLISHABLE_KINDS:
            if kind == "module":
                from fmriflow.server.services.module_loader import get_modules_dir
                # Only user-tier files that are actually *registered* — an
                # unregistered/invalid .py has no known category, and publishing
                # it would produce a manifest entry missing metadata.category
                # (which the store schema requires) and fail validation.
                registered: set[str] = set()
                for lst in state.registry.list_modules().values():
                    registered.update(lst)
                names = sorted(p.stem for p in get_modules_dir().glob("*.py")
                               if p.stem != "__init__" and p.stem in registered)
            elif kind == "heuristic":
                from fmriflow.convert.heuristics import _heuristics_dir
                names = sorted(p.stem for p in _heuristics_dir().glob("*.py"))
            else:
                names = sorted(installer.local_names(kind, state))
            if names:
                out[kind] = names
        return out

    def list_branches(self, sid: str) -> list[str]:
        source = self.registry.get(sid)
        if source is None:
            raise KeyError(f"no source '{sid}'")
        backend = get_backend(source.backend)
        return backend.list_branches(source.url, self.registry.token_for(sid))

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
        # Validate a repo that has content. A truly empty (commit-less) repo
        # legitimately has no manifest yet — don't warn on that; but a
        # non-empty repo missing/breaking hub.json IS a schema problem and must
        # be surfaced.
        warnings = [] if _is_empty_clone(dest) else manifest.validate_manifest(dest)
        return {"synced": True, "source_id": sid,
                "artifacts": len(entries), "warnings": warnings}

    def validate(self, sid: str) -> dict:
        source = self.registry.get(sid)
        if source is None:
            raise KeyError(f"no source '{sid}'")
        dest = self.clone_dir(source)
        if not dest.is_dir():
            return {"synced": False, "problems": ["source not synced yet — sync first"]}
        return {"synced": True, "problems": manifest.validate_manifest(dest)}

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

    def install_many(self, state, sid: str | None = None,
                     kind: str | None = None) -> dict:
        """Install every not-yet-installed catalog artifact.

        Scope: one *kind* (or all kinds when omitted), from one source (or all
        synced sources when *sid* is omitted). Already-installed items and
        duplicates across sources are skipped; a failure on one artifact never
        aborts the rest — it's collected and reported.
        """
        items = self.catalog(state, kind=kind)
        if sid:
            items = [i for i in items if i["source_id"] == sid]

        installed: list[str] = []
        skipped = 0
        failed: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for it in items:
            key = (it["kind"], it["name"])
            if it["installed"] or key in seen:
                skipped += 1
                continue
            seen.add(key)
            try:
                self.install(it["source_id"], it["kind"], it["name"], state)
                installed.append(f"{it['kind']}/{it['name']}")
            except Exception as e:  # noqa: BLE001 - report, keep going
                logger.warning("Hub bulk install failed for %s/%s: %s",
                               it["kind"], it["name"], e)
                failed.append({"kind": it["kind"], "name": it["name"], "error": str(e)})
        return {"installed": len(installed), "skipped": skipped,
                "failed": failed, "names": installed, "kind": kind}

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

    def publish_kind(self, sid: str, kind: str, state, *, author: str = "") -> dict:
        """Publish every local artifact of *kind* to the source in one commit."""
        source = self.registry.get(sid)
        if source is None:
            raise KeyError(f"no source '{sid}'")
        if kind not in self.PUBLISHABLE_KINDS:
            raise RuntimeError(f"kind '{kind}' is not publishable")
        names = self.local_artifacts(state).get(kind, [])
        if not names:
            # No-op, not an error — mirrors the "nothing to publish" shape so a
            # stale UI selection surfaces as a notice, not a 400.
            return {"pushed": False, "kind": kind, "count": 0,
                    "detail": f"no local {kind} artifacts to publish"}
        dest = self.clone_dir(source)
        if not dest.is_dir():
            self.sync(sid)
        backend = get_backend(source.backend)
        return publisher.publish_many(
            source, dest, kind, names, state,
            backend=backend, token=self.registry.token_for(sid), author=author,
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
