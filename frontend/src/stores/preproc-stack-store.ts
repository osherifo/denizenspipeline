/** Preproc-stack store — composition + active-run state.
 *
 * State splits cleanly into three parts:
 * - **Catalogue** (registered workflows + transforms, loaded once).
 * - **Recipe** (stack composition: bootstrap stage + transform list).
 * - **Run binding + active run** (subject/paths, the run currently
 *   executing, events streamed over WS).
 *
 * Phase 6a ships this as one store for simplicity. If complexity
 * grows, the catalogue half can move to its own store later.
 */

import { create } from 'zustand'
import type {
  BootstrapKind,
  BootstrapStageBody,
  PreflightResult,
  StackEvent,
  StackResultPayload,
  StackRunSummary,
  TransformInfo,
  TransformStageBody,
  WorkflowInfo,
} from '../api/types'
import {
  cancelStackRun,
  fetchStackRun,
  fetchStackRuns,
  fetchStackTransforms,
  fetchStackWorkflows,
  launchStackRun,
  openStackEventsSocket,
  transformPreflight,
  workflowPreflight,
} from '../api/client'


interface PreprocStackState {
  // ── Catalogue ────────────────────────────────────────────────
  workflows: WorkflowInfo[]
  transforms: TransformInfo[]
  catalogueLoaded: boolean
  catalogueError: string | null

  // ── Bootstrap selection ──────────────────────────────────────
  bootstrap: BootstrapStageBody
  bootstrapPreflight: PreflightResult | null

  // ── Transform list ───────────────────────────────────────────
  transformsStack: TransformStageBody[]

  // ── Run binding ──────────────────────────────────────────────
  subject: string
  outputDir: string
  bidsDir: string
  derivativesDir: string
  dataset: string
  task: string
  useCache: boolean

  // ── Active run ───────────────────────────────────────────────
  activeRunId: string | null
  activeStatus: string | null     // running / done / failed / cancelled / lost
  activeEvents: StackEvent[]
  activeResult: StackResultPayload | null
  activeError: string | null
  websocket: WebSocket | null
  runHistory: StackRunSummary[]

  // ── Actions ──────────────────────────────────────────────────
  loadCatalogue: () => Promise<void>
  setBootstrap: (b: Partial<BootstrapStageBody>) => void
  checkBootstrapPreflight: () => Promise<void>

  addTransform: (name: string) => void
  removeTransform: (index: number) => void
  moveTransformUp: (index: number) => void
  moveTransformDown: (index: number) => void
  setTransformParams: (index: number, params: Record<string, unknown>) => void

  setRunBinding: (patch: Partial<{
    subject: string
    outputDir: string
    bidsDir: string
    derivativesDir: string
    dataset: string
    task: string
    useCache: boolean
  }>) => void

  launch: () => Promise<void>
  cancel: () => Promise<void>
  refreshActiveRun: () => Promise<void>
  refreshHistory: () => Promise<void>
  clearActiveRun: () => void
}


function defaultBootstrap(): BootstrapStageBody {
  return { kind: 'nipype', workflow: 'identity', params: {} }
}


export const usePreprocStackStore = create<PreprocStackState>((set, get) => ({
  workflows: [],
  transforms: [],
  catalogueLoaded: false,
  catalogueError: null,

  bootstrap: defaultBootstrap(),
  bootstrapPreflight: null,

  transformsStack: [],

  subject: '',
  outputDir: '',
  bidsDir: '',
  derivativesDir: '',
  dataset: 'unknown',
  task: '',
  useCache: true,

  activeRunId: null,
  activeStatus: null,
  activeEvents: [],
  activeResult: null,
  activeError: null,
  websocket: null,
  runHistory: [],

  async loadCatalogue() {
    try {
      const [wfRes, txRes] = await Promise.all([
        fetchStackWorkflows(),
        fetchStackTransforms(),
      ])
      set({
        workflows: wfRes.workflows,
        transforms: txRes.transforms,
        catalogueLoaded: true,
        catalogueError: null,
      })
      // Preflight the currently-selected bootstrap workflow.
      const { bootstrap } = get()
      const name = resolveWorkflowName(bootstrap)
      if (name) {
        try {
          const pre = await workflowPreflight(name)
          set({ bootstrapPreflight: pre })
        } catch {
          set({ bootstrapPreflight: null })
        }
      }
    } catch (e) {
      set({
        catalogueError: (e as Error).message,
        catalogueLoaded: true,
      })
    }
  },

  setBootstrap(patch) {
    const merged = { ...get().bootstrap, ...patch }
    // If kind switched away from nipype, drop the workflow name so the
    // resolver picks the kind-name workflow automatically.
    if (patch.kind && patch.kind !== 'nipype') {
      merged.workflow = null
    }
    if (patch.kind === 'nipype' && !merged.workflow) {
      merged.workflow = 'identity'
    }
    set({ bootstrap: merged, bootstrapPreflight: null })
  },

  async checkBootstrapPreflight() {
    const name = resolveWorkflowName(get().bootstrap)
    if (!name) {
      set({ bootstrapPreflight: null })
      return
    }
    try {
      const pre = await workflowPreflight(name)
      set({ bootstrapPreflight: pre })
    } catch (e) {
      set({
        bootstrapPreflight: {
          ok: false,
          errors: [(e as Error).message],
          warnings: [],
        },
      })
    }
  },

  addTransform(name) {
    const stack = [...get().transformsStack, { name, params: {} }]
    set({ transformsStack: stack })
  },

  removeTransform(index) {
    const next = get().transformsStack.filter((_, i) => i !== index)
    set({ transformsStack: next })
  },

  moveTransformUp(index) {
    if (index <= 0) return
    const next = [...get().transformsStack]
    ;[next[index - 1], next[index]] = [next[index], next[index - 1]]
    set({ transformsStack: next })
  },

  moveTransformDown(index) {
    const stack = get().transformsStack
    if (index >= stack.length - 1) return
    const next = [...stack]
    ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
    set({ transformsStack: next })
  },

  setTransformParams(index, params) {
    const next = get().transformsStack.map(
      (t, i) => (i === index ? { ...t, params } : t),
    )
    set({ transformsStack: next })
  },

  setRunBinding(patch) {
    set(patch as Partial<PreprocStackState>)
  },

  async launch() {
    const s = get()
    if (!s.subject || !s.outputDir) {
      set({ activeError: 'Subject and output_dir are required.' })
      return
    }

    // Close any prior socket before launching a new run.
    s.websocket?.close()

    set({
      activeRunId: null,
      activeStatus: 'launching',
      activeEvents: [],
      activeResult: null,
      activeError: null,
      websocket: null,
    })

    try {
      const result = await launchStackRun({
        stack: {
          bootstrap: s.bootstrap,
          transforms: s.transformsStack,
        },
        subject: s.subject,
        output_dir: s.outputDir,
        bids_dir: s.bidsDir || null,
        derivatives_dir: s.derivativesDir || null,
        dataset: s.dataset || 'unknown',
        sessions: [],
        task: s.task || null,
        use_cache: s.useCache,
      })

      const ws = openStackEventsSocket(result.run_id)
      ws.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data) as StackEvent
          // Append to events log.
          set((st) => ({ activeEvents: [...st.activeEvents, ev] }))
          // Terminal _close event → fetch final status snapshot.
          if (ev.event === '_close') {
            void get().refreshActiveRun()
          }
        } catch {
          // Ignore malformed frames.
        }
      }
      ws.onerror = () => {
        // Connection lost — fall back to polling.
        void get().refreshActiveRun()
      }
      ws.onclose = () => {
        void get().refreshActiveRun()
      }

      set({
        activeRunId: result.run_id,
        activeStatus: 'running',
        websocket: ws,
      })
    } catch (e) {
      set({
        activeStatus: 'failed',
        activeError: (e as Error).message,
        websocket: null,
      })
    }
  },

  async cancel() {
    const { activeRunId } = get()
    if (!activeRunId) return
    try {
      const res = await cancelStackRun(activeRunId)
      if (!res.cancelled && res.reason) {
        set({ activeError: `Cancel refused: ${res.reason}` })
      }
    } catch (e) {
      set({ activeError: (e as Error).message })
    }
  },

  async refreshActiveRun() {
    const { activeRunId } = get()
    if (!activeRunId) return
    try {
      const summary = await fetchStackRun(activeRunId)
      set({
        activeStatus: summary.status,
        activeResult: summary.result,
        activeError: summary.error,
      })
    } catch {
      /* keep current state — transient errors shouldn't blank the UI */
    }
  },

  async refreshHistory() {
    try {
      const res = await fetchStackRuns()
      set({ runHistory: res.runs })
    } catch (e) {
      set({ activeError: (e as Error).message })
    }
  },

  clearActiveRun() {
    get().websocket?.close()
    set({
      activeRunId: null,
      activeStatus: null,
      activeEvents: [],
      activeResult: null,
      activeError: null,
      websocket: null,
    })
  },
}))


function resolveWorkflowName(b: BootstrapStageBody): string | null {
  if (b.kind === 'nipype') return b.workflow || null
  return b.kind
}
