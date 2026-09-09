/** Runs tab state: the run list, the selected run's detail, live events + checkpoints. */
import { create } from 'zustand'
import {
  cancelPipelineRun,
  deletePipelineRun,
  fetchPipelineRun,
  fetchPipelineRuns,
  fetchRunCheckpoints,
  openPipelineRunSocket,
  restartPipelineRun,
  resumePipelineRun,
} from '../api/preproc'
import type { CheckpointRecord, PipelineEvent, PipelineRunDetail, PipelineRunSummary } from '../api/types'

const TERMINAL = new Set(['done', 'failed', 'cancelled', 'lost'])

interface RunsState {
  runs: PipelineRunSummary[]
  runsLoading: boolean
  selectedRunId: string | null
  detail: PipelineRunDetail | null
  events: PipelineEvent[]
  checkpoints: CheckpointRecord[]
  socket: WebSocket | null
  error: string | null

  loadRuns: () => Promise<void>
  select: (runId: string | null) => Promise<void>
  refreshDetail: () => Promise<void>
  cancel: (runId: string) => Promise<void>
  resume: (runId: string) => Promise<string | null>
  restart: (runId: string) => Promise<string | null>
  remove: (runId: string) => Promise<void>
  disconnect: () => void
}

export const usePreprocRunsStore = create<RunsState>((set, get) => ({
  runs: [],
  runsLoading: false,
  selectedRunId: null,
  detail: null,
  events: [],
  checkpoints: [],
  socket: null,
  error: null,

  loadRuns: async () => {
    set({ runsLoading: true })
    try {
      const { runs } = await fetchPipelineRuns()
      set({ runs, runsLoading: false })
    } catch (e) {
      set({ runsLoading: false, error: (e as Error).message })
    }
  },

  select: async (runId) => {
    get().disconnect()
    if (!runId) {
      set({ selectedRunId: null, detail: null, events: [], checkpoints: [] })
      return
    }
    set({ selectedRunId: runId, detail: null, events: [], checkpoints: [], error: null })
    try {
      const [detail, cps] = await Promise.all([fetchPipelineRun(runId), fetchRunCheckpoints(runId)])
      set({ detail, checkpoints: cps.checkpoints })
    } catch (e) {
      set({ error: (e as Error).message })
      return
    }
    // The socket replays events.jsonl from the start, then tails it while the run is live.
    let ws: WebSocket
    try {
      ws = openPipelineRunSocket(runId)
    } catch {
      return
    }
    ws.onmessage = (msg) => {
      let ev: PipelineEvent
      try {
        ev = JSON.parse(msg.data)
      } catch {
        return
      }
      if (get().selectedRunId !== runId) return
      if (ev.event === '_close') {
        void get().refreshDetail()
        return
      }
      set({ events: [...get().events, ev] })
      if (ev.event === 'checkpoint' || ev.event === 'node_done' || ev.event === 'node_fail') {
        // Cheap: refresh the detail block so the graph's status overlay follows.
        void get().refreshDetail()
      }
    }
    ws.onclose = () => {
      if (get().socket === ws) set({ socket: null })
    }
    set({ socket: ws })
  },

  refreshDetail: async () => {
    const runId = get().selectedRunId
    if (!runId) return
    try {
      const [detail, cps] = await Promise.all([fetchPipelineRun(runId), fetchRunCheckpoints(runId)])
      if (get().selectedRunId !== runId) return
      set({ detail, checkpoints: cps.checkpoints })
      if (TERMINAL.has(detail.status)) {
        set({ runs: get().runs.map((r) => (r.run_id === runId ? { ...r, status: detail.status } : r)) })
      }
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  cancel: async (runId) => {
    try {
      await cancelPipelineRun(runId)
      await get().loadRuns()
      if (get().selectedRunId === runId) await get().refreshDetail()
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  resume: async (runId) => {
    try {
      const { run_id } = await resumePipelineRun(runId)
      await get().loadRuns()
      await get().select(run_id)
      return run_id
    } catch (e) {
      set({ error: (e as Error).message })
      return null
    }
  },

  restart: async (runId) => {
    try {
      const { run_id } = await restartPipelineRun(runId)
      await get().loadRuns()
      await get().select(run_id)
      return run_id
    } catch (e) {
      set({ error: (e as Error).message })
      return null
    }
  },

  remove: async (runId) => {
    try {
      await deletePipelineRun(runId)
      if (get().selectedRunId === runId) await get().select(null)
      await get().loadRuns()
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  disconnect: () => {
    const ws = get().socket
    if (ws) {
      try { ws.close() } catch { /* ignore */ }
    }
    set({ socket: null })
  },
}))
