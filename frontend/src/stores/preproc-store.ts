/** Legacy preprocessing-manager store — manifest browsing only.
 *
 * The launch surface (RunForm, validate-config, run-from-saved-config)
 * was hard-removed in Stage 7d-A. All new launches go through the
 * preproc-stack store in ``preproc-stack-store.ts``. What stays here
 * is read-side state used by the surviving views: BackendStatus,
 * ManifestBrowser, CollectForm, InFlightRuns.
 */
import { create } from 'zustand'
import type {
  BackendInfo,
  ManifestSummary,
  ManifestDetail,
  PreprocEvent,
  CollectResult,
  ConfigSummary,
  PreprocRunSummary,
} from '../api/types'
import {
  fetchPreprocBackends,
  fetchManifests,
  rescanManifests,
  fetchManifestDetail,
  validateManifest,
  collectPreprocOutputs,
  connectPreprocWs,
  fetchConfigs,
  fetchPreprocRuns,
  cancelPreprocRun,
} from '../api/client'

type Tab = 'backends' | 'manifests' | 'collect'

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

  // Analysis configs (for the validate-against dropdown).
  configs: ConfigSummary[]

  // In-flight + recent runs (read-only browsing; launches happen on
  // the preproc-stack page).
  preprocRuns: PreprocRunSummary[]
  preprocRunsLoading: boolean

  // Collect
  collectResult: CollectResult | null
  collecting: boolean
  collectError: string | null

  // Attached-run state (for tailing an in-flight run from
  // InFlightRuns).
  runId: string | null
  runEvents: PreprocEvent[]
  runStartTime: number | null
  runError: string | null
  running: boolean

  // Actions
  setTab: (tab: Tab) => void
  loadBackends: () => Promise<void>
  loadManifests: () => Promise<void>
  rescan: () => Promise<void>
  selectManifest: (subject: string) => Promise<void>
  validateSelected: (configFilename?: string) => Promise<void>
  loadConfigs: () => Promise<void>
  collect: (params: Parameters<typeof collectPreprocOutputs>[0]) => Promise<void>
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
      // Refresh manifests so the newly-collected one shows up.
      get().rescan()
    } catch (e) {
      set({ collectError: String(e), collecting: false })
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
    // Open a WebSocket to an in-flight job. Used for reattached runs
    // or clicking into an active run from the In-Flight panel.
    set({
      running: true, runError: null, runEvents: [],
      runStartTime: startedAt ? startedAt * 1000 : Date.now(),
      runId,
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
      get().loadPreprocRuns()
      throw e
    }
  },

  clearRun: () => set({
    runId: null, runEvents: [], runStartTime: null,
    runError: null, running: false,
  }),

  clearCollect: () => set({ collectResult: null, collectError: null }),
}))
