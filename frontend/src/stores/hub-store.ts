/**
 * Artifact Hub store — sources + merged local/remote catalog + install/publish.
 * Self-contained; delete this file + views/HubView.tsx to remove the feature.
 */

import { create } from 'zustand'
import {
  fetchHubSources, addHubSource, removeHubSource, syncHubSource,
  fetchHubCatalog, installHubArtifact, publishHubArtifact, fetchHubProvenance,
  fetchHubLocalArtifacts, publishHubKind, installHubMany,
} from '../api/client'
import type { HubSource, HubCatalogItem, HubProvenanceMap } from '../api/types'

interface HubState {
  sources: HubSource[]
  envOverride: boolean
  preflight: string[]
  keyringAvailable: boolean
  catalog: HubCatalogItem[]
  kindFilter: string | null
  loading: boolean
  error: string | null
  busy: string | null           // key of the item/source currently mutating
  notice: string | null
  provenance: HubProvenanceMap
  provenanceLoaded: boolean
  localArtifacts: Record<string, string[]>

  loadSources: () => Promise<void>
  loadProvenance: (force?: boolean) => Promise<void>
  loadLocalArtifacts: () => Promise<void>
  publishLocal: (sourceId: string, kind: string, name: string) => Promise<void>
  publishKind: (sourceId: string, kind: string) => Promise<void>
  addSource: (b: { name: string; url: string; tier: string; branch?: string; token?: string }) => Promise<void>
  removeSource: (sid: string) => Promise<void>
  sync: (sid: string) => Promise<void>
  syncAll: () => Promise<void>
  loadCatalog: (kind?: string | null) => Promise<void>
  install: (item: HubCatalogItem) => Promise<void>
  installMany: (kind?: string | null) => Promise<void>
  publish: (item: HubCatalogItem) => Promise<void>
  setKindFilter: (kind: string | null) => void
  clearNotice: () => void
}

export const useHubStore = create<HubState>((set, get) => ({
  sources: [],
  envOverride: false,
  preflight: [],
  keyringAvailable: false,
  catalog: [],
  kindFilter: null,
  loading: false,
  error: null,
  busy: null,
  notice: null,
  provenance: {},
  provenanceLoaded: false,
  localArtifacts: {},

  loadLocalArtifacts: async () => {
    try {
      const r = await fetchHubLocalArtifacts()
      set({ localArtifacts: r.artifacts })
    } catch { /* non-fatal */ }
  },

  publishLocal: async (sourceId, kind, name) => {
    const key = `pub:${sourceId}:${kind}:${name}`
    set({ busy: key, error: null, notice: `Publishing ${kind}/${name}…` })
    try {
      const r = await publishHubArtifact({ source_id: sourceId, kind, name })
      // Refresh the catalog from the (already-updated) local clone — NOT a
      // full sync, which would overwrite this notice with "Synced — …" and
      // lose the PR link.
      await get().loadCatalog(get().kindFilter)
      set({ notice: !r.pushed
        ? (r.detail || 'Nothing to publish.')
        : r.initialized
          ? `Initialized the store on ${r.branch} with ${kind}/${name}.`
          : `Published ${kind}/${name} to branch ${r.branch}${r.pr_url ? ` — open a PR: ${r.pr_url}` : ''}` })
    } catch (e) { set({ error: String(e) }) } finally { set({ busy: null }) }
  },

  publishKind: async (sourceId, kind) => {
    const key = `pubkind:${sourceId}:${kind}`
    set({ busy: key, error: null, notice: `Publishing all ${kind}…` })
    try {
      const r = await publishHubKind({ source_id: sourceId, kind })
      await get().loadCatalog(get().kindFilter)
      set({ notice: !r.pushed
        ? (r.detail || 'Nothing to publish.')
        : r.initialized
          ? `Initialized the store on ${r.branch} with ${r.count} ${kind} artifact(s).`
          : `Published ${r.count} ${kind} artifact(s) to branch ${r.branch}${r.pr_url ? ` — open a PR: ${r.pr_url}` : ''}` })
    } catch (e) { set({ error: String(e) }) } finally { set({ busy: null }) }
  },

  loadProvenance: async (force = false) => {
    if (get().provenanceLoaded && !force) return
    try {
      const p = await fetchHubProvenance()
      set({ provenance: p, provenanceLoaded: true })
    } catch {
      set({ provenanceLoaded: true })   // don't retry-storm on failure
    }
  },

  loadSources: async () => {
    try {
      const s = await fetchHubSources()
      set({ sources: s.sources, envOverride: s.env_override, preflight: s.preflight, keyringAvailable: s.keyring_available, error: null })
    } catch (e) {
      set({ error: String(e) })
    }
  },

  addSource: async (b) => {
    set({ busy: 'add', error: null })
    try {
      const s = await addHubSource(b)
      set({ sources: s.sources, envOverride: s.env_override, preflight: s.preflight, keyringAvailable: s.keyring_available })
    } catch (e) {
      set({ error: String(e) })
    } finally { set({ busy: null }) }
  },

  removeSource: async (sid) => {
    set({ busy: sid })
    try {
      const s = await removeHubSource(sid)
      set({ sources: s.sources, envOverride: s.env_override })
      await get().loadCatalog(get().kindFilter)
    } catch (e) { set({ error: String(e) }) } finally { set({ busy: null }) }
  },

  sync: async (sid) => {
    const name = get().sources.find((s) => s.id === sid)?.name ?? 'source'
    set({ busy: sid, error: null, notice: `Syncing ${name}… (cloning/pulling the repo)` })
    try {
      const r = await syncHubSource(sid)
      const warn = r.warnings && r.warnings.length
        ? `  ⚠️ store schema issues: ${r.warnings.slice(0, 3).join('; ')}${r.warnings.length > 3 ? ` (+${r.warnings.length - 3} more)` : ''}`
        : ''
      set({ notice: `Synced — ${r.artifacts} artifact(s).${warn}` })
      await get().loadSources()
      await get().loadCatalog(get().kindFilter)
    } catch (e) { set({ error: String(e) }) } finally { set({ busy: null }) }
  },

  syncAll: async () => {
    for (const s of get().sources) {
      if (s.enabled) { try { await get().sync(s.id) } catch { /* keep going */ } }
    }
  },

  loadCatalog: async (kind) => {
    set({ loading: true })
    try {
      const r = await fetchHubCatalog(kind ?? undefined)
      set({ catalog: r.items, loading: false, error: null })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  install: async (item) => {
    const key = `${item.source_id}:${item.kind}:${item.name}`
    set({ busy: key, error: null, notice: null })
    try {
      await installHubArtifact({ source_id: item.source_id, kind: item.kind, name: item.name })
      set({ notice: `Installed ${item.kind}/${item.name} to your local tier.` })
      await get().loadCatalog(get().kindFilter)
      await get().loadProvenance(true)
    } catch (e) { set({ error: String(e) }) } finally { set({ busy: null }) }
  },

  installMany: async (kind) => {
    const key = `installmany:${kind ?? 'all'}`
    set({ busy: key, error: null, notice: `Installing all ${kind ?? 'artifacts'}…` })
    try {
      const r = await installHubMany(kind ? { kind } : {})
      await get().loadCatalog(get().kindFilter)
      await get().loadProvenance(true)
      // `skipped` covers both already-installed items *and* duplicates of the
      // same kind/name offered by another source — don't claim it's only the
      // former. Failures are qualified with the kind, since a bare name is
      // ambiguous when installing across kinds.
      const bits = [`Installed ${r.installed}`]
      if (r.skipped) bits.push(`${r.skipped} skipped (already installed or duplicated across sources)`)
      if (r.failed.length) {
        const shown = r.failed.slice(0, 2).map((f) => `${f.kind}/${f.name}`).join(', ')
        const more = r.failed.length > 2 ? `, +${r.failed.length - 2} more` : ''
        bits.push(`${r.failed.length} failed (${shown}${more})`)
      }
      set({ notice: bits.join(' · ') + '.' })
    } catch (e) { set({ error: String(e) }) } finally { set({ busy: null }) }
  },

  publish: async (item) => {
    const key = `${item.source_id}:${item.kind}:${item.name}`
    set({ busy: key, error: null, notice: `Publishing ${item.kind}/${item.name}…` })
    try {
      const r = await publishHubArtifact({ source_id: item.source_id, kind: item.kind, name: item.name })
      set({ notice: !r.pushed
        ? (r.detail || 'Nothing to publish.')
        : r.initialized
          ? `Initialized the empty repo on ${r.branch} with ${r.kind}/${r.name}.`
          : `Published to branch ${r.branch}${r.pr_url ? ` — open a PR: ${r.pr_url}` : ''}` })
    } catch (e) { set({ error: String(e) }) } finally { set({ busy: null }) }
  },

  setKindFilter: (kind) => { set({ kindFilter: kind }); void get().loadCatalog(kind) },
  clearNotice: () => set({ notice: null }),
}))
