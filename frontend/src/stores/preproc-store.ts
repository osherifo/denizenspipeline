/** Preprocessing manager store. */
import { create } from 'zustand'
import type {
  BackendInfo,
  ManifestSummary,
  ManifestDetail,
  PreprocEvent,
  CollectResult,
  ConfigSummary,
  PreprocConfigSummary,
  PreprocConfigDetail,
  PreprocRunSummary,
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
  fetchPreprocConfigs,
  fetchPreprocConfigDetail,
  runPreprocConfigFile,
  fetchPreprocRuns,
  cancelPreprocRun,
} from '../api/client'

type Tab = 'backends' | 'manifests' | 'collect' | 'run' | 'configs'

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

  // Preproc configs (YAML files with preproc: section)
  preprocConfigs: PreprocConfigSummary[]
  preprocConfigsLoading: boolean
  selectedPreprocConfig: PreprocConfigDetail | null
  selectedPreprocConfigLoading: boolean

  // In-flight + recent runs
  preprocRuns: PreprocRunSummary[]
  preprocRunsLoading: boolean

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
  loadPreprocConfigs: () => Promise<void>
  selectPreprocConfig: (filename: string) => Promise<void>
  runPreprocConfig: (filename: string) => Promise<void>
  loadPreprocRuns: (includeFinished?: boolean) => Promise<void>
  attachToRun: (runId: string, startedAt?: number) => void
  cancelRun: (runId: string) => Promise<void>
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

  preprocConfigs: [],
  preprocConfigsLoading: false,
  selectedPreprocConfig: null,
  selectedPreprocConfigLoading: false,

  preprocRuns: [],
  preprocRunsLoading: false,

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

  loadPreprocConfigs: async () => {
    set({ preprocConfigsLoading: true })
    try {
      const preprocConfigs = await fetchPreprocConfigs()
      set({ preprocConfigs, preprocConfigsLoading: false })
    } catch {
      set({ preprocConfigsLoading: false })
    }
  },

  selectPreprocConfig: async (filename) => {
    set({ selectedPreprocConfig: null, selectedPreprocConfigLoading: true })
    try {
      const detail = await fetchPreprocConfigDetail(filename)
      set({ selectedPreprocConfig: detail, selectedPreprocConfigLoading: false })
    } catch {
      set({ selectedPreprocConfigLoading: false })
    }
  },

  runPreprocConfig: async (filename) => {
    set({
      running: true, runError: null, runEvents: [],
      runStartTime: Date.now(), runId: null, configErrors: null,
    })
    try {
      const result = await runPreprocConfigFile(filename)
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

  loadPreprocRuns: async (includeFinished: boolean = true) => {
    set({ preprocRunsLoading: true })
    try {
      const runs = await fetchPreprocRuns(includeFinished)
      set({ preprocRuns: runs, preprocRunsLoading: false })
    } catch {
      set({ preprocRunsLoading: false })
    }
  },

  attachToRun: (runId, startedAt) => {
    // Open a WebSocket to a running job. Used for reattached runs or
    // clicking into an active run from the In-Flight panel.
    set({
      running: true, runError: null, runEvents: [],
      runStartTime: startedAt ? startedAt * 1000 : Date.now(),
      runId, configErrors: null,
    })
    const ws = connectPreprocWs(runId)
    ws.onmessage = (msg) => {
      const event: PreprocEvent = JSON.parse(msg.data)
      set((s) => ({ runEvents: [...s.runEvents, event] }))
      if (event.event === 'done' || event.event === 'failed' || event.event === 'cancelled') {
        ws.close()
        set({
          running: false,
          runError: event.event === 'failed' ? (event.error || 'failed') : null,
        })
        get().rescan()
        get().loadPreprocRuns()
      }
    }
    ws.onerror = () => {
      set({ running: false, runError: 'WebSocket connection failed' })
    }
  },

  cancelRun: async (runId) => {
    try {
      await cancelPreprocRun(runId)
      get().loadPreprocRuns()
    } catch (e) {
      // Leave the caller to surface; still refresh the list.
      get().loadPreprocRuns()
      throw e
    }
  },

  clearRun: () => set({ runId: null, runEvents: [], runStartTime: null, runError: null, running: false, configErrors: null }),

  clearCollect: () => set({ collectResult: null, collectError: null }),
}))
