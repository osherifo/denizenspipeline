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

// Not store state — bumping it must never trigger a re-render. Every select()
// and disconnect() call increments this; a select() in flight captures the
// value right after it calls disconnect() and treats a mismatch at each
// post-await checkpoint as "superseded" (a later select(), or a disconnect()
// from elsewhere, such as a modal's unmount cleanup) — it backs off instead
// of clobbering fresher state or leaving an untracked socket connected.
let selectToken = 0

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
    const token = ++selectToken
    if (!runId) {
      set({ selectedRunId: null, detail: null, events: [], checkpoints: [] })
      return
    }
    set({ selectedRunId: runId, detail: null, events: [], checkpoints: [], error: null })
    try {
      const [detail, cps] = await Promise.all([fetchPipelineRun(runId), fetchRunCheckpoints(runId)])
      if (token !== selectToken) return   // superseded while these were in flight
      set({ detail, checkpoints: cps.checkpoints })
    } catch (e) {
      if (token === selectToken) set({ error: (e as Error).message })
      return
    }
    // The socket replays events.jsonl from the start, then tails it while the run is live.
    let ws: WebSocket
    try {
      ws = openPipelineRunSocket(runId)
    } catch {
      return
    }
    if (token !== selectToken) {
      // Superseded (a newer select(), or a disconnect() — e.g. the owning
      // modal unmounted) while the socket was being created. Nothing will
      // track or close this one otherwise, so close it here.
      try { ws.close() } catch { /* ignore */ }
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
    selectToken++   // invalidate any select() currently in flight
    const ws = get().socket
    if (ws) {
      try { ws.close() } catch { /* ignore */ }
    }
    set({ socket: null })
  },
}))
