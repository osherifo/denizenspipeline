/** Preprocessing manager store. */
import { create } from 'zustand'
import type {
  BackendInfo,
  ManifestSummary,
  ManifestDetail,
  PreprocEvent,
  CollectResult,
  ConfigSummary,
} from '../api/types'
import {
  fetchPreprocBackends,
  fetchManifests,
  rescanManifests,
  fetchManifestDetail,
  validateManifest,
  collectPreprocOutputs,
  startPreprocRun,
  validatePreprocConfig,
  connectPreprocWs,
  fetchConfigs,
} from '../api/client'

type Tab = 'backends' | 'manifests' | 'collect' | 'run'

interface PreprocState {
  tab: Tab

  // Backends
  backends: BackendInfo[]
  backendsLoading: boolean

  // Manifests
  manifests: ManifestSummary[]
  manifestsLoading: boolean
  selectedSubject: string | null
  selectedManifest: ManifestDetail | null
  validationErrors: string[] | null
  validating: boolean

  // Configs (for validate-against dropdown)
  configs: ConfigSummary[]

  // Collect
  collectResult: CollectResult | null
  collecting: boolean
  collectError: string | null

  // Run
  runId: string | null
  runEvents: PreprocEvent[]
  runStartTime: number | null
  runError: string | null
  running: boolean
  configErrors: string[] | null

  // Actions
  setTab: (tab: Tab) => void
  loadBackends: () => Promise<void>
  loadManifests: () => Promise<void>
  rescan: () => Promise<void>
  selectManifest: (subject: string) => Promise<void>
  validateSelected: (configFilename?: string) => Promise<void>
  loadConfigs: () => Promise<void>
  collect: (params: Parameters<typeof collectPreprocOutputs>[0]) => Promise<void>
  startRun: (params: Parameters<typeof startPreprocRun>[0]) => Promise<void>
  validateConfig: (params: Parameters<typeof validatePreprocConfig>[0]) => Promise<void>
  clearRun: () => void
  clearCollect: () => void
}

export const usePreprocStore = create<PreprocState>((set, get) => ({
  tab: 'backends',

  backends: [],
  backendsLoading: false,

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

  runId: null,
  runEvents: [],
  runStartTime: null,
  runError: null,
  running: false,
  configErrors: null,

  setTab: (tab) => set({ tab }),

  loadBackends: async () => {
    set({ backendsLoading: true })
    try {
      const backends = await fetchPreprocBackends()
      set({ backends, backendsLoading: false })
    } catch {
      set({ backendsLoading: false })
    }
  },

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
      // Refresh manifests
      get().rescan()
    } catch (e) {
      set({ collectError: String(e), collecting: false })
    }
  },

  startRun: async (params) => {
    set({ running: true, runError: null, runEvents: [], runStartTime: Date.now(), runId: null, configErrors: null })
    try {
      const result = await startPreprocRun(params)
      set({ runId: result.run_id })

      const ws = connectPreprocWs(result.run_id)
      ws.onmessage = (msg) => {
        const event: PreprocEvent = JSON.parse(msg.data)
        set((s) => ({ runEvents: [...s.runEvents, event] }))
        if (event.event === 'done' || event.event === 'failed') {
          ws.close()
          set({
            running: false,
            runError: event.event === 'failed' ? (event.error || 'failed') : null,
          })
          get().rescan()
        }
      }
      ws.onerror = () => {
        set({ running: false, runError: 'WebSocket connection failed' })
      }
    } catch (e) {
      set({ running: false, runError: String(e) })
    }
  },

  validateConfig: async (params) => {
    set({ configErrors: null })
    try {
      const result = await validatePreprocConfig(params)
      set({ configErrors: result.errors })
    } catch (e) {
      set({ configErrors: [String(e)] })
    }
  },

  clearRun: () => set({ runId: null, runEvents: [], runStartTime: null, runError: null, running: false, configErrors: null }),

  clearCollect: () => set({ collectResult: null, collectError: null }),
}))
