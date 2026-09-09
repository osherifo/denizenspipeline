/** Build tab state: node library, templates, saved pipelines, the pipeline being edited. */
import { create } from 'zustand'
import {
  deletePipeline,
  fetchNodeLibrary,
  fetchPipeline,
  fetchPipelineTemplate,
  fetchPipelineTemplates,
  fetchPipelines,
  runPipeline,
  savePipeline,
  validatePipeline,
} from '../api/preproc'
import type {
  PipelineDoc,
  PipelineEdgeDoc,
  PipelineNodeDoc,
  PipelineRunRequestBody,
  PipelineSummary,
  PipelineTemplateSummary,
  PreprocNodeInfo,
} from '../api/types'

export type BuildView = 'simple' | 'graph'

export interface RunBinding {
  subject: string
  output_dir: string
  bids_dir: string
  derivatives_dir: string
  work_dir: string
  dataset: string
  plugin: 'Linear' | 'MultiProc'
  n_procs: number | null
  use_cache: boolean
  rerun_from: string[]
  abort_on_bad: boolean
}

export const EMPTY_PIPELINE: PipelineDoc = {
  schema_version: 1,
  name: 'untitled',
  description: '',
  inputs: {},
  nodes: [],
  edges: [],
  manifest: {},
}

const DEFAULT_BINDING: RunBinding = {
  subject: '', output_dir: '', bids_dir: '', derivatives_dir: '', work_dir: '', dataset: 'unknown',
  plugin: 'Linear', n_procs: null, use_cache: true, rerun_from: [], abort_on_bad: false,
}

/** True when every node has at most one incoming and one outgoing edge along a single chain. */
export function isLinear(p: PipelineDoc): boolean {
  if (p.nodes.length === 0) return true
  if (p.edges.length !== p.nodes.length - 1) return false
  const inC = new Map<string, number>()
  const outC = new Map<string, number>()
  for (const n of p.nodes) { inC.set(n.id, 0); outC.set(n.id, 0) }
  for (const e of p.edges) {
    if (!inC.has(e.target) || !outC.has(e.source)) return false
    inC.set(e.target, (inC.get(e.target) ?? 0) + 1)
    outC.set(e.source, (outC.get(e.source) ?? 0) + 1)
  }
  return [...inC.values()].every((c) => c <= 1) && [...outC.values()].every((c) => c <= 1)
}

/** Topological order (Kahn); falls back to declaration order on a cycle. */
export function topoOrder(p: PipelineDoc): PipelineNodeDoc[] {
  const indeg = new Map<string, number>(p.nodes.map((n) => [n.id, 0]))
  const adj = new Map<string, string[]>(p.nodes.map((n) => [n.id, []]))
  for (const e of p.edges) {
    if (indeg.has(e.target)) indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1)
    adj.get(e.source)?.push(e.target)
  }
  const queue = p.nodes.filter((n) => indeg.get(n.id) === 0).map((n) => n.id)
  const out: string[] = []
  while (queue.length) {
    const id = queue.shift()!
    out.push(id)
    for (const nxt of adj.get(id) ?? []) {
      indeg.set(nxt, (indeg.get(nxt) ?? 0) - 1)
      if (indeg.get(nxt) === 0) queue.push(nxt)
    }
  }
  if (out.length !== p.nodes.length) return p.nodes
  const byId = new Map(p.nodes.map((n) => [n.id, n]))
  return out.map((id) => byId.get(id)!)
}

function uniqueId(base: string, taken: Set<string>): string {
  if (!taken.has(base)) return base
  let i = 2
  while (taken.has(`${base}_${i}`)) i += 1
  return `${base}_${i}`
}

interface PipelineState {
  library: PreprocNodeInfo[]
  libraryLoading: boolean
  templates: PipelineTemplateSummary[]
  pipelines: PipelineSummary[]
  legacy: { name: string; path: string; hint: string }[]
  pipeline: PipelineDoc
  pipelineName: string | null      // saved-as name, null for unsaved
  dirty: boolean
  view: BuildView
  selectedNodeId: string | null
  validation: { ok: boolean; errors: string[] } | null
  binding: RunBinding
  launching: boolean
  lastRunId: string | null
  error: string | null

  loadLibrary: () => Promise<void>
  loadTemplates: () => Promise<void>
  loadPipelines: () => Promise<void>
  loadTemplate: (name: string) => Promise<void>
  loadPipeline: (name: string) => Promise<void>
  newPipeline: () => void
  setPipeline: (p: PipelineDoc) => void
  setView: (v: BuildView) => void
  selectNode: (id: string | null) => void
  addNode: (type: string, position?: { x: number; y: number }) => string | null
  removeNode: (id: string) => void
  updateNodeParams: (id: string, params: Record<string, unknown>) => void
  updateNodeData: (id: string, patch: Partial<PipelineNodeDoc['data']>) => void
  moveNode: (id: string, position: { x: number; y: number }) => void
  addEdge: (edge: Omit<PipelineEdgeDoc, 'id'>) => void
  removeEdge: (id: string) => void
  appendAfter: (afterId: string | null, type: string) => string | null
  setPipelineMeta: (patch: Partial<Pick<PipelineDoc, 'name' | 'description' | 'inputs' | 'manifest'>>) => void
  validate: () => Promise<void>
  save: (name: string) => Promise<void>
  remove: (name: string) => Promise<void>
  setBinding: (patch: Partial<RunBinding>) => void
  launch: () => Promise<string | null>
}

export const usePreprocPipelineStore = create<PipelineState>((set, get) => ({
  library: [],
  libraryLoading: false,
  templates: [],
  pipelines: [],
  legacy: [],
  pipeline: EMPTY_PIPELINE,
  pipelineName: null,
  dirty: false,
  view: 'simple',
  selectedNodeId: null,
  validation: null,
  binding: DEFAULT_BINDING,
  launching: false,
  lastRunId: null,
  error: null,

  loadLibrary: async () => {
    set({ libraryLoading: true })
    try {
      const { nodes } = await fetchNodeLibrary()
      set({ library: nodes, libraryLoading: false })
    } catch (e) {
      set({ libraryLoading: false, error: (e as Error).message })
    }
  },

  loadTemplates: async () => {
    try {
      const { templates } = await fetchPipelineTemplates()
      set({ templates })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  loadPipelines: async () => {
    try {
      const { pipelines, legacy } = await fetchPipelines()
      set({ pipelines, legacy })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  loadTemplate: async (name) => {
    try {
      const { pipeline } = await fetchPipelineTemplate(name)
      set({
        pipeline, pipelineName: null, dirty: true, selectedNodeId: pipeline.nodes[0]?.id ?? null,
        validation: null, view: isLinear(pipeline) ? 'simple' : 'graph', error: null,
      })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  loadPipeline: async (name) => {
    try {
      const { pipeline } = await fetchPipeline(name)
      set({
        pipeline, pipelineName: name, dirty: false, selectedNodeId: pipeline.nodes[0]?.id ?? null,
        validation: null, view: isLinear(pipeline) ? 'simple' : 'graph', error: null,
      })
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  newPipeline: () => set({
    pipeline: { ...EMPTY_PIPELINE, inputs: {} }, pipelineName: null, dirty: false,
    selectedNodeId: null, validation: null, view: 'simple', error: null,
  }),

  setPipeline: (p) => set({ pipeline: p, dirty: true, validation: null }),
  setView: (view) => set({ view }),
  selectNode: (selectedNodeId) => set({ selectedNodeId }),

  addNode: (type, position) => {
    const info = get().library.find((n) => n.name === type)
    if (!info) return null
    const p = get().pipeline
    const id = uniqueId(type, new Set(p.nodes.map((n) => n.id)))
    const node: PipelineNodeDoc = {
      id, type, kind: info.kind,
      data: { params: {}, literal_inputs: {}, bindings: {} },
      position: position ?? { x: 80 + p.nodes.length * 260, y: 80 },
    }
    set({ pipeline: { ...p, nodes: [...p.nodes, node] }, dirty: true, selectedNodeId: id, validation: null })
    return id
  },

  removeNode: (id) => {
    const p = get().pipeline
    const manifest = { ...p.manifest }
    if (manifest.backend_node === id) delete manifest.backend_node
    for (const k of ['bold_from', 'confounds_from'] as const) {
      if ((manifest[k] ?? '').split('.')[0] === id) delete manifest[k]
    }
    set({
      pipeline: {
        ...p,
        nodes: p.nodes.filter((n) => n.id !== id),
        edges: p.edges.filter((e) => e.source !== id && e.target !== id),
        manifest,
      },
      dirty: true,
      selectedNodeId: get().selectedNodeId === id ? null : get().selectedNodeId,
      validation: null,
    })
  },

  updateNodeParams: (id, params) => {
    const p = get().pipeline
    set({
      pipeline: { ...p, nodes: p.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, params } } : n)) },
      dirty: true, validation: null,
    })
  },

  updateNodeData: (id, patch) => {
    const p = get().pipeline
    set({
      pipeline: { ...p, nodes: p.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)) },
      dirty: true, validation: null,
    })
  },

  moveNode: (id, position) => {
    const p = get().pipeline
    set({ pipeline: { ...p, nodes: p.nodes.map((n) => (n.id === id ? { ...n, position } : n)) } })
  },

  addEdge: (edge) => {
    const p = get().pipeline
    // One feed per input port: replace an existing edge into the same target handle.
    const kept = p.edges.filter((e) => !(e.target === edge.target && e.targetHandle === edge.targetHandle))
    const id = uniqueId(`e_${edge.source}_${edge.target}_${edge.targetHandle}`, new Set(kept.map((e) => e.id)))
    set({ pipeline: { ...p, edges: [...kept, { id, ...edge }] }, dirty: true, validation: null })
  },

  removeEdge: (id) => {
    const p = get().pipeline
    set({ pipeline: { ...p, edges: p.edges.filter((e) => e.id !== id) }, dirty: true, validation: null })
  },

  /** Simple view: append a node after ``afterId`` (or at the end) and wire the first
   *  file-like output of the predecessor into the first file-like input of the new node. */
  appendAfter: (afterId, type) => {
    const state = get()
    const order = topoOrder(state.pipeline)
    const prev = afterId ? order.find((n) => n.id === afterId) ?? null : order[order.length - 1] ?? null
    const id = state.addNode(type)
    if (!id) return null
    if (prev) {
      const lib = state.library
      const prevInfo = lib.find((n) => n.name === prev.type)
      const info = lib.find((n) => n.name === type)
      const fileish = (spec: { kind: string }) => !['str', 'int', 'float', 'bool', 'dir', 'any'].includes(spec.kind)
      const srcPorts = Object.entries(prevInfo?.outputs ?? {})
      const dstPorts = Object.entries(info?.inputs ?? {})
      const src = srcPorts.find(([, s]) => fileish(s)) ?? srcPorts[0]
      const dst = dstPorts.find(([, s]) => fileish(s)) ?? dstPorts[0]
      if (src && dst) {
        get().addEdge({ source: prev.id, target: id, sourceHandle: src[0], targetHandle: dst[0] })
      }
    }
    return id
  },

  setPipelineMeta: (patch) => set({ pipeline: { ...get().pipeline, ...patch }, dirty: true, validation: null }),

  validate: async () => {
    try {
      const res = await validatePipeline(get().pipeline)
      set({ validation: { ok: res.ok, errors: res.errors } })
    } catch (e) {
      set({ validation: { ok: false, errors: [(e as Error).message] } })
    }
  },

  save: async (name) => {
    try {
      const res = await savePipeline(name, { ...get().pipeline, name })
      set({ pipelineName: name, dirty: false, pipeline: { ...get().pipeline, name }, validation: { ok: res.errors.length === 0, errors: res.errors }, error: null })
      await get().loadPipelines()
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  remove: async (name) => {
    try {
      await deletePipeline(name)
      if (get().pipelineName === name) get().newPipeline()
      await get().loadPipelines()
    } catch (e) {
      set({ error: (e as Error).message })
    }
  },

  setBinding: (patch) => set({ binding: { ...get().binding, ...patch } }),

  launch: async () => {
    const { pipeline, pipelineName, binding } = get()
    set({ launching: true, error: null })
    const body: PipelineRunRequestBody = {
      pipeline,
      pipeline_name: pipelineName ?? undefined,
      subject: binding.subject,
      output_dir: binding.output_dir,
      bids_dir: binding.bids_dir || null,
      derivatives_dir: binding.derivatives_dir || null,
      work_dir: binding.work_dir || null,
      dataset: binding.dataset || 'unknown',
      plugin: binding.plugin,
      n_procs: binding.n_procs,
      use_cache: binding.use_cache,
      rerun_from: binding.rerun_from,
      abort_on_bad: binding.abort_on_bad,
    }
    try {
      const { run_id } = await runPipeline(body)
      set({ launching: false, lastRunId: run_id })
      return run_id
    } catch (e) {
      set({ launching: false, error: (e as Error).message })
      return null
    }
  },
}))
