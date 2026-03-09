/** Run history store. */
import { create } from 'zustand'
import type { RunSummary, RunEvent, PipelineConfig } from '../api/types'
import { fetchRuns, fetchRun, startRun, connectRunWs } from '../api/client'

interface RunState {
  runs: RunSummary[]
  selectedRun: RunSummary | null
  liveRunId: string | null
  liveEvents: RunEvent[]
  loading: boolean
  error: string | null

  loadRuns: (opts?: { experiment?: string; subject?: string }) => Promise<void>
  selectRun: (runId: string) => Promise<void>
  clearSelection: () => void
  launchRun: (config: PipelineConfig) => Promise<string>
  subscribeLive: (runId: string) => void
}

export const useRunStore = create<RunState>((set, get) => ({
  runs: [],
  selectedRun: null,
  liveRunId: null,
  liveEvents: [],
  loading: false,
  error: null,

  loadRuns: async (opts) => {
    set({ loading: true, error: null })
    try {
      const runs = await fetchRuns(opts)
      set({ runs, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  selectRun: async (runId) => {
    set({ loading: true })
    try {
      const run = await fetchRun(runId)
      set({ selectedRun: run, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  clearSelection: () => set({ selectedRun: null }),

  launchRun: async (config) => {
    const result = await startRun(config)
    set({ liveRunId: result.run_id, liveEvents: [] })
    get().subscribeLive(result.run_id)
    return result.run_id
  },

  subscribeLive: (runId) => {
    const ws = connectRunWs(runId)
    ws.onmessage = (msg) => {
      const event: RunEvent = JSON.parse(msg.data)
      set((s) => ({ liveEvents: [...s.liveEvents, event] }))
      if (event.event === 'run_done' || event.event === 'run_failed') {
        ws.close()
        set({ liveRunId: null })
        get().loadRuns()
      }
    }
    ws.onerror = () => {
      set({ liveRunId: null })
    }
  },
}))
