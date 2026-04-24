/** Autoflatten manager store. */
import { create } from 'zustand'
import {
  fetchAutoflattenDoctor,
  fetchAutoflattenStatus,
  startAutoflatten,
  fetchAutoflattenRun,
  connectAutoflattenWs,
} from '../api/client'

type Tab = 'status' | 'run' | 'import' | 'configs'

interface ToolInfo {
  name: string
  available: boolean
  detail: string
}

interface SubjectStatus {
  subject: string
  subject_dir_exists: boolean
  has_surfaces: boolean
  surfaces: Record<string, boolean>
  flat_patches: Record<string, string>
  has_flat_patches: boolean
  pycortex_surface: string | null
}

interface RunResult {
  subject: string
  source: string
  hemispheres: string[]
  flat_patches: Record<string, string>
  visualizations: Record<string, string>
  pycortex_surface: string | null
  elapsed_s: number
}

export interface AutoflattenEvent {
  event: string
  level?: string
  message?: string
  error?: string
  timestamp?: number
  source?: string
  pycortex_surface?: string | null
  elapsed?: number
}

interface AutoflattenState {
  tab: Tab

  // Doctor
  tools: ToolInfo[]
  toolsLoading: boolean

  // Status
  subjectStatus: SubjectStatus | null
  statusLoading: boolean
  statusError: string | null

  // Run
  runId: string | null
  running: boolean
  runResult: RunResult | null
  runError: string | null
  runEvents: AutoflattenEvent[]
  runStartTime: number | null

  // Actions
  setTab: (tab: Tab) => void
  loadTools: () => Promise<void>
  checkStatus: (subjectsDir: string, subject: string) => Promise<void>
  startRun: (params: Parameters<typeof startAutoflatten>[0]) => Promise<void>
  attachToRun: (runId: string) => void
  clearRun: () => void
  clearStatus: () => void
}

export const useAutoflattenStore = create<AutoflattenState>((set, get) => ({
  tab: 'status',

  tools: [],
  toolsLoading: false,

  subjectStatus: null,
  statusLoading: false,
  statusError: null,

  runId: null,
  running: false,
  runResult: null,
  runError: null,
  runEvents: [],
  runStartTime: null,

  setTab: (tab) => set({ tab }),

  loadTools: async () => {
    set({ toolsLoading: true })
    try {
      const data = await fetchAutoflattenDoctor()
      set({ tools: data.tools, toolsLoading: false })
    } catch {
      set({ toolsLoading: false })
    }
  },

  checkStatus: async (subjectsDir, subject) => {
    set({ statusLoading: true, statusError: null, subjectStatus: null })
    try {
      const status = await fetchAutoflattenStatus({ subjects_dir: subjectsDir, subject })
      set({ subjectStatus: status, statusLoading: false })
    } catch (e) {
      set({ statusError: String(e), statusLoading: false })
    }
  },

  startRun: async (params) => {
    set({
      running: true,
      runError: null,
      runResult: null,
      runEvents: [],
      runStartTime: Date.now(),
      runId: null,
    })
    try {
      const { run_id } = await startAutoflatten(params)
      set({ runId: run_id })

      // Open WebSocket for live log streaming
      const ws = connectAutoflattenWs(run_id)
      ws.onmessage = (msg) => {
        const event: AutoflattenEvent = JSON.parse(msg.data)
        set((s) => ({ runEvents: [...s.runEvents, event] }))

        if (event.event === 'done' || event.event === 'failed') {
          // Fetch final result to populate runResult
          fetchAutoflattenRun(run_id)
            .then((data) => {
              set({
                running: false,
                runResult: data.result?.result ?? null,
                runError: event.event === 'failed' ? (event.error ?? 'failed') : null,
              })
            })
            .catch(() => {
              set({
                running: false,
                runError: event.event === 'failed' ? (event.error ?? 'failed') : null,
              })
            })
          ws.close()
        }
      }
      ws.onerror = () => {
        // WebSocket errored — fall back to polling the REST endpoint
        const poll = async () => {
          try {
            const data = await fetchAutoflattenRun(run_id)
            set({ runEvents: data.events as AutoflattenEvent[] })
            if (data.status !== 'running') {
              set({
                running: false,
                runResult: data.result?.result ?? null,
                runError: data.status === 'failed' ? (data.error ?? 'failed') : null,
              })
              return
            }
          } catch {
            set({ running: false, runError: 'Connection lost' })
            return
          }
          setTimeout(poll, 1000)
        }
        poll()
      }
    } catch (e) {
      set({ runError: String(e), running: false })
    }
  },

  attachToRun: (runId) => {
    set({
      running: true,
      runError: null,
      runResult: null,
      runEvents: [],
      runStartTime: Date.now(),
      runId,
    })
    const ws = connectAutoflattenWs(runId)
    ws.onmessage = (msg) => {
      const event: AutoflattenEvent = JSON.parse(msg.data)
      set((s) => ({ runEvents: [...s.runEvents, event] }))
      if (event.event === 'done' || event.event === 'failed') {
        fetchAutoflattenRun(runId)
          .then((data) => {
            set({
              running: false,
              runResult: data.result?.result ?? null,
              runError: event.event === 'failed' ? (event.error ?? 'failed') : null,
            })
          })
          .catch(() => {
            set({
              running: false,
              runError: event.event === 'failed' ? (event.error ?? 'failed') : null,
            })
          })
        ws.close()
      }
    }
    ws.onerror = () => {
      // WebSocket errored — fall back to polling the REST endpoint
      const poll = async () => {
        try {
          const data = await fetchAutoflattenRun(runId)
          set({ runEvents: data.events as AutoflattenEvent[] })
          if (data.status !== 'running') {
            set({
              running: false,
              runResult: data.result?.result ?? null,
              runError: data.status === 'failed' ? (data.error ?? 'failed') : null,
            })
            return
          }
        } catch {
          set({ running: false, runError: 'Connection lost' })
          return
        }
        setTimeout(poll, 1000)
      }
      poll()
    }
  },

  clearRun: () => set({
    runId: null,
    runResult: null,
    runError: null,
    runEvents: [],
    runStartTime: null,
    running: false,
  }),
  clearStatus: () => set({ subjectStatus: null, statusError: null }),
}))
