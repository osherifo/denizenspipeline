/**
 * Artifact Hub store — sources + merged local/remote catalog + install/publish.
 * Self-contained; delete this file + views/HubView.tsx to remove the feature.
 */

import { create } from 'zustand'
import {
  fetchHubSources, addHubSource, removeHubSource, syncHubSource,
  fetchHubCatalog, installHubArtifact, publishHubArtifact, fetchHubProvenance,
} from '../api/client'
import type { HubSource, HubCatalogItem, HubProvenanceMap } from '../api/types'

interface HubState {
  sources: HubSource[]
  envOverride: boolean
  preflight: string[]
  catalog: HubCatalogItem[]
  kindFilter: string | null
  loading: boolean
  error: string | null
  busy: string | null           // key of the item/source currently mutating
  notice: string | null
  provenance: HubProvenanceMap
  provenanceLoaded: boolean

  loadSources: () => Promise<void>
  loadProvenance: (force?: boolean) => Promise<void>
  addSource: (b: { name: string; url: string; tier: string; branch?: string; token?: string }) => Promise<void>
  removeSource: (sid: string) => Promise<void>
  sync: (sid: string) => Promise<void>
  syncAll: () => Promise<void>
  loadCatalog: (kind?: string | null) => Promise<void>
  install: (item: HubCatalogItem) => Promise<void>
  publish: (item: HubCatalogItem) => Promise<void>
  setKindFilter: (kind: string | null) => void
  clearNotice: () => void
}

export const useHubStore = create<HubState>((set, get) => ({
  sources: [],
  envOverride: false,
  preflight: [],
  catalog: [],
  kindFilter: null,
  loading: false,
  error: null,
  busy: null,
  notice: null,
  provenance: {},
  provenanceLoaded: false,

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
      set({ sources: s.sources, envOverride: s.env_override, preflight: s.preflight, error: null })
    } catch (e) {
      set({ error: String(e) })
    }
  },

  addSource: async (b) => {
    set({ busy: 'add', error: null })
    try {
      const s = await addHubSource(b)
      set({ sources: s.sources, envOverride: s.env_override, preflight: s.preflight })
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
    set({ busy: sid, error: null })
    try {
      const r = await syncHubSource(sid)
      set({ notice: `Synced — ${r.artifacts} artifact(s).` })
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
      set({ catalog: r.items, loading: false })
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

  publish: async (item) => {
    const key = `${item.source_id}:${item.kind}:${item.name}`
    set({ busy: key, error: null, notice: null })
    try {
      const r = await publishHubArtifact({ source_id: item.source_id, kind: item.kind, name: item.name })
      set({ notice: r.pushed
        ? `Published to branch ${r.branch}${r.pr_url ? ` — open a PR: ${r.pr_url}` : ''}`
        : (r.detail || 'Nothing to publish.') })
    } catch (e) { set({ error: String(e) }) } finally { set({ busy: null }) }
  },

  setKindFilter: (kind) => { set({ kindFilter: kind }); void get().loadCatalog(kind) },
  clearNotice: () => set({ notice: null }),
}))
