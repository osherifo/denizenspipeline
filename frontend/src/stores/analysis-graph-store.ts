/** Analysis builder state: node catalog and port types, templates, saved graphs, the graph
 *  being edited, the run-panel input values and the live node status of the last run. */
import { create } from 'zustand'
import { load as loadYaml } from 'js-yaml'
import {
  compileAnalysisConfig,
  deleteAnalysisGraph,
  deleteAnalysisTemplate,
  fetchAnalysisGraph,
  fetchAnalysisGraphs,
  fetchAnalysisNodes,
  fetchAnalysisTemplate,
  fetchAnalysisTemplates,
  fetchPortTypes,
  runAnalysisGraph,
  saveAnalysisGraph,
  saveAnalysisTemplate,
  validateAnalysisGraph,
} from '../api/analysis'
import { connectRunWs } from '../api/client'
import type {
  AnalysisGraphDoc,
  AnalysisGraphInputSpec,
  AnalysisGraphNodeDoc,
  AnalysisGraphSummary,
  AnalysisNodeInfo,
  AnalysisPortType,
  AnalysisTemplateSummary,
  RunEvent,
} from '../api/types'
import type { GraphConnection } from '../components/graph/GraphCanvas'
import type { NodeRunStatus } from '../components/graph/GraphNodeCard'
import {
  connect as connectEdge,
  disconnect as disconnectEdge,
  moveFanInEdge,
  moveNodeTo,
  removeNodeFrom,
  setNodeParams,
  uniqueId,
} from './graph-edit-slice'

export const EMPTY_GRAPH: AnalysisGraphDoc = {
  schema_version: 1,
  name: 'untitled',
  description: '',
  scope: 'subject',
  inputs: {
    subject: { kind: 'str', description: 'subject id' },
    output_dir: { kind: 'dir', description: 'where reports are written' },
  },
  globals: { experiment: 'untitled', subject: '$inputs.subject', reporting: { output_dir: '$inputs.output_dir' } },
  nodes: [],
  edges: [],
}

/** A run-panel value as typed: lists and mappings parse as YAML; anything else stays text, so "01" stays "01". */
export function parseInputValue(text: string): unknown {
  const t = text.trim()
  if (t.startsWith('[') || t.startsWith('{')) {
    try { return loadYaml(t) } catch { return text }
  }
  return text
}

export function formatInputValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

/** Default node id for a node type: the module name (``model:bootstrap_ridge`` → ``bootstrap_ridge``). */
export function nodeIdFor(type: string): string {
  const tail = type.includes(':') ? type.slice(type.indexOf(':') + 1) : type
  return tail.includes('.') ? tail.slice(tail.lastIndexOf('.') + 1) : tail
}

function inputValuesFor(graph: AnalysisGraphDoc, saved?: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [name, spec] of Object.entries(graph.inputs ?? {})) out[name] = formatInputValue(saved?.[name] ?? spec.default)
  return out
}

function opened(graph: AnalysisGraphDoc, saved?: Record<string, unknown>) {
  return { graph, selectedNodeId: null, validation: null, error: null, inputValues: inputValuesFor(graph, saved) }
}

export type RunState = 'idle' | 'running' | 'done' | 'failed'

let activeWs: WebSocket | null = null

interface AnalysisGraphState {
  catalog: AnalysisNodeInfo[]
  portTypes: AnalysisPortType[]
  templates: AnalysisTemplateSummary[]
  graphs: AnalysisGraphSummary[]
  graph: AnalysisGraphDoc
  graphName: string | null
  dirty: boolean
  selectedNodeId: string | null
  validation: { ok: boolean; errors: string[] } | null
  inputValues: Record<string, string>
  launching: boolean
  lastRunId: string | null
  runState: RunState
  runStatus: Record<string, NodeRunStatus>
  error: string | null

  loadCatalog: () => Promise<void>
  loadTemplates: () => Promise<void>
  loadGraphs: () => Promise<void>
  loadTemplate: (name: string) => Promise<void>
  loadGraph: (name: string) => Promise<void>
  newGraph: () => void
  /** Compile a stage config (saved file name or inline config) and open the result; false on error. */
  openStageConfig: (source: { filename?: string; config?: Record<string, unknown> }) => Promise<boolean>
  setGraph: (graph: AnalysisGraphDoc) => void
  selectNode: (id: string | null) => void
  addNode: (type: string, position?: { x: number; y: number }) => string | null
  removeNode: (id: string) => void
  updateNodeParams: (id: string, params: Record<string, unknown>) => void
  moveNode: (id: string, position: { x: number; y: number }) => void
  addEdge: (edge: GraphConnection) => void
  removeEdge: (id: string) => void
  moveEdge: (id: string, delta: -1 | 1) => void
  setMeta: (patch: Partial<Pick<AnalysisGraphDoc, 'name' | 'description' | 'globals'>>) => void
  /** Declare (or, with null, remove) a graph input. */
  setInput: (name: string, spec: AnalysisGraphInputSpec | null) => void
  setInputValue: (name: string, value: string) => void
  parsedInputs: () => Record<string, unknown>
  validate: () => Promise<void>
  save: (name: string) => Promise<void>
  remove: (name: string) => Promise<void>
  saveTemplate: (name: string) => Promise<string[] | null>
  removeTemplate: (name: string) => Promise<void>
  launch: () => Promise<string | null>
  applyRunEvent: (event: RunEvent) => void
  disconnect: () => void
}

export const useAnalysisGraphStore = create<AnalysisGraphState>((set, get) => ({
  catalog: [],
  portTypes: [],
  templates: [],
  graphs: [],
  graph: EMPTY_GRAPH,
  graphName: null,
  dirty: false,
  selectedNodeId: null,
  validation: null,
  inputValues: inputValuesFor(EMPTY_GRAPH),
  launching: false,
  lastRunId: null,
  runState: 'idle',
  runStatus: {},
  error: null,

  loadCatalog: async () => {
    try {
      const [{ nodes }, { types }] = await Promise.all([fetchAnalysisNodes(), fetchPortTypes()])
      set({ catalog: nodes, portTypes: types })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  loadTemplates: async () => {
    try {
      const { templates } = await fetchAnalysisTemplates()
      set({ templates })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  loadGraphs: async () => {
    try {
      const { graphs } = await fetchAnalysisGraphs()
      set({ graphs })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  loadTemplate: async (name) => {
    try {
      const { graph } = await fetchAnalysisTemplate(name)
      set({ ...opened(graph), graphName: null, dirty: true })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  loadGraph: async (name) => {
    try {
      const { graph } = await fetchAnalysisGraph(name)
      // A saved graph brings its run-panel values back with it.
      set({ ...opened(graph, graph.run_defaults?.inputs), graphName: name, dirty: false })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  newGraph: () => set({ ...opened(EMPTY_GRAPH), graphName: null, dirty: false }),

  openStageConfig: async (source) => {
    try {
      const { graph } = await compileAnalysisConfig(source)
      set({ ...opened(graph), graphName: null, dirty: true })
      return true
    } catch (e) {
      set({ error: (e as Error).message })
      return false
    }
  },

  setGraph: (graph) => {
    const previous = get().inputValues
    const inputValues = inputValuesFor(graph)
    for (const name of Object.keys(inputValues)) if (previous[name]) inputValues[name] = previous[name]
    const selected = get().selectedNodeId
    set({
      graph, dirty: true, validation: null, inputValues,
      selectedNodeId: graph.nodes.some((n) => n.id === selected) ? selected : null,
    })
  },

  selectNode: (selectedNodeId) => set({ selectedNodeId }),

  addNode: (type, position) => {
    if (!get().catalog.some((n) => n.type === type)) return null
    const g = get().graph
    const id = uniqueId(nodeIdFor(type), new Set(g.nodes.map((n) => n.id)))
    const k = g.nodes.length
    const node: AnalysisGraphNodeDoc = {
      id, type, data: { params: {} },
      position: position ?? { x: 80 + (k % 6) * 260, y: 80 + Math.floor(k / 6) * 170 },
    }
    set({ graph: { ...g, nodes: [...g.nodes, node] }, dirty: true, selectedNodeId: id, validation: null })
    return id
  },

  removeNode: (id) => set({
    graph: removeNodeFrom(get().graph, id), dirty: true, validation: null,
    selectedNodeId: get().selectedNodeId === id ? null : get().selectedNodeId,
  }),

  updateNodeParams: (id, params) => set({ graph: setNodeParams(get().graph, id, params), dirty: true, validation: null }),

  moveNode: (id, position) => set({ graph: moveNodeTo(get().graph, id, position) }),

  addEdge: (edge) => {
    const g = get().graph
    const target = g.nodes.find((n) => n.id === edge.target)
    const info = target ? get().catalog.find((n) => n.type === target.type) : undefined
    // Fan-in inputs (e.g. the feature bundle) keep every edge, in order; others take one feed.
    const fanIn = Boolean(info?.inputs[edge.targetHandle]?.multiple)
    set({ graph: connectEdge(g, edge, { fanIn }), dirty: true, validation: null })
  },

  removeEdge: (id) => set({ graph: disconnectEdge(get().graph, id), dirty: true, validation: null }),

  moveEdge: (id, delta) => set({ graph: moveFanInEdge(get().graph, id, delta), dirty: true, validation: null }),

  setMeta: (patch) => set({ graph: { ...get().graph, ...patch }, dirty: true, validation: null }),

  setInput: (name, spec) => {
    const g = get().graph
    const inputs = { ...g.inputs }
    const inputValues = { ...get().inputValues }
    if (spec === null) {
      delete inputs[name]
      delete inputValues[name]
    } else {
      inputs[name] = spec
      inputValues[name] = inputValues[name] ?? ''
    }
    set({ graph: { ...g, inputs }, inputValues, dirty: true, validation: null })
  },

  setInputValue: (name, value) => set({ inputValues: { ...get().inputValues, [name]: value } }),

  parsedInputs: () => Object.fromEntries(
    Object.entries(get().inputValues).filter(([, v]) => v.trim() !== '').map(([k, v]) => [k, parseInputValue(v)]),
  ),

  validate: async () => {
    try {
      const res = await validateAnalysisGraph(get().graph, get().parsedInputs())
      set({ validation: { ok: res.ok, errors: res.errors } })
    } catch (e) {
      set({ validation: { ok: false, errors: [(e as Error).message] } })
    }
  },

  save: async (name) => {
    try {
      const g = get().graph
      // The run panel travels with the saved graph, so reopening it needs no retyping.
      const doc: AnalysisGraphDoc = { ...g, run_defaults: { ...(g.run_defaults ?? {}), inputs: get().parsedInputs() } }
      const res = await saveAnalysisGraph(name, doc)
      set({ graph: doc, graphName: name, dirty: false, validation: { ok: res.errors.length === 0, errors: res.errors }, error: null })
      await get().loadGraphs()
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  remove: async (name) => {
    try {
      await deleteAnalysisGraph(name)
      if (get().graphName === name) get().newGraph()
      await get().loadGraphs()
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  saveTemplate: async (name) => {
    try {
      const { warnings } = await saveAnalysisTemplate(name, get().graph)
      await get().loadTemplates()
      return warnings
    } catch (e) {
      set({ error: (e as Error).message })
      return null
    }
  },

  removeTemplate: async (name) => {
    try {
      await deleteAnalysisTemplate(name)
      await get().loadTemplates()
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  launch: async () => {
    const { graph, graphName } = get()
    get().disconnect()
    set({ launching: true, error: null, runStatus: {}, runState: 'idle' })
    try {
      const { run_id } = await runAnalysisGraph({ graph, graph_name: graphName ?? undefined, inputs: get().parsedInputs() })
      set({ launching: false, lastRunId: run_id, runState: 'running' })
      try {
        const ws = connectRunWs(run_id)
        activeWs = ws
        ws.onmessage = (msg) => {
          if (activeWs !== ws) return
          try { get().applyRunEvent(JSON.parse(msg.data) as RunEvent) } catch { /* not an event */ }
        }
        ws.onclose = () => { if (activeWs === ws) activeWs = null }
      } catch { /* live node status is best effort; the run itself has started */ }
      return run_id
    } catch (e) {
      set({ launching: false, error: (e as Error).message })
      return null
    }
  },

  applyRunEvent: (event) => {
    const id = event.node_id
    const put = (st: NodeRunStatus) => { if (id) set({ runStatus: { ...get().runStatus, [id]: st } }) }
    switch (event.event) {
      case 'node_start': put({ status: 'running' }); break
      case 'node_done': put({ status: 'ok', durationS: event.elapsed ?? null }); break
      case 'node_fail': put({ status: 'failed', durationS: event.elapsed ?? null, error: event.error }); break
      case 'node_skipped': put({ status: 'skipped' }); break
      case 'run_done': set({ runState: 'done' }); break
      case 'run_failed': set({ runState: 'failed', error: event.error ?? event.message ?? 'run failed' }); break
      default: break
    }
  },

  disconnect: () => {
    if (activeWs) {
      try { activeWs.close() } catch { /* already closed */ }
      activeWs = null
    }
  },
}))
