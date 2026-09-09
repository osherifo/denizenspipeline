/** Preprocessing outputs store — manifests on disk and "collect" existing derivatives.
 *
 * Runs and pipelines live in ``preproc-runs-store.ts`` / ``preproc-pipeline-store.ts``;
 * what stays here is the read side used by the Outputs tab (ManifestBrowser,
 * ManifestDetail, CollectForm).
 */
import { create } from 'zustand'
import type {
  ManifestSummary,
  ManifestDetail,
  CollectResult,
  ConfigSummary,
} from '../api/types'
import {
  fetchManifests,
  rescanManifests,
  fetchManifestDetail,
  validateManifest,
  collectPreprocOutputs,
  fetchConfigs,
} from '../api/client'

type Tab = 'manifests' | 'collect'

interface PreprocState {
  tab: Tab

  // Manifests
  manifests: ManifestSummary[]
  manifestsLoading: boolean
  selectedSubject: string | null
  selectedManifest: ManifestDetail | null
  validationErrors: string[] | null
  validating: boolean

  // Analysis configs, for "validate against config"
  configs: ConfigSummary[]

  // Collect
  collectResult: CollectResult | null
  collecting: boolean
  collectError: string | null

  setTab: (tab: Tab) => void
  loadManifests: () => Promise<void>
  rescan: () => Promise<void>
  selectManifest: (subject: string) => Promise<void>
  validateSelected: (configFilename?: string) => Promise<void>
  loadConfigs: () => Promise<void>
  collect: (params: Parameters<typeof collectPreprocOutputs>[0]) => Promise<void>
  clearCollect: () => void
}

export const usePreprocStore = create<PreprocState>((set, get) => ({
  tab: 'manifests',
  manifests: [],
  manifestsLoading: false,
  selectedSubject: null,
  selectedManifest: null,
  validationErrors: null,
  validating: false,
  configs: [],
  collectResult: null,
  collecting: false,
  collectError: null,

  setTab: (tab) => set({ tab }),

  loadManifests: async () => {
    set({ manifestsLoading: true })
    try {
      const manifests = await fetchManifests()
      set({ manifests, manifestsLoading: false })
    } catch {
      set({ manifestsLoading: false })
    }
  },

  rescan: async () => {
    set({ manifestsLoading: true })
    try {
      const manifests = await rescanManifests()
      set({ manifests, manifestsLoading: false })
    } catch {
      set({ manifestsLoading: false })
    }
  },

  selectManifest: async (subject) => {
    set({ selectedSubject: subject, selectedManifest: null, validationErrors: null })
    try {
      const detail = await fetchManifestDetail(subject)
      set({ selectedManifest: detail })
    } catch {
      set({ selectedManifest: null })
    }
  },

  validateSelected: async (configFilename) => {
    const subject = get().selectedSubject
    if (!subject) return
    set({ validating: true, validationErrors: null })
    try {
      const result = await validateManifest(subject, configFilename)
      set({ validationErrors: result.errors, validating: false })
    } catch (e) {
      set({ validationErrors: [String(e)], validating: false })
    }
  },

  loadConfigs: async () => {
    try {
      const configs = await fetchConfigs()
      set({ configs })
    } catch {
      // ignore
    }
  },

  collect: async (params) => {
    set({ collecting: true, collectError: null, collectResult: null })
    try {
      const result = await collectPreprocOutputs(params)
      set({ collectResult: result, collecting: false })
      // Refresh manifests so the newly-collected one shows up.
      get().rescan()
    } catch (e) {
      set({ collectError: String(e), collecting: false })
    }
  },

  clearCollect: () => set({ collectResult: null, collectError: null }),
}))
