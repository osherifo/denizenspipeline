/** Pipeline graph store — nodes, edges, layout, selection. */
import { create } from 'zustand'
import {
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
  type EdgeChange,
  applyNodeChanges,
  applyEdgeChanges,
  MarkerType,
} from '@xyflow/react'
import dagre from 'dagre'
import yaml from 'js-yaml'

// ── Handle / data types ─────────────────────────────────────────────────

/** Data types that flow between nodes. Used for connection validation. */
export type DataType =
  | 'dicom'
  | 'bids'
  | 'bold'
  | 'freesurfer'
  | 'surface'
  | 'manifest'
  | 'responses'
  | 'features'
  | 'prepared'
  | 'results'

export type StageType =
  | 'source'
  | 'convert'
  | 'preproc'
  | 'autoflatten'
  | 'response_loader'
  | 'features'
  | 'prepare'
  | 'model'
  | 'report'

export interface StageNodeData extends Record<string, unknown> {
  stageType: StageType
  label: string
  status: 'pending' | 'running' | 'done' | 'error' | 'skipped'
  config: Record<string, unknown>
  /** Short summary shown on the node body */
  summary: string[]
}

// ── Connection rules ────────────────────────────────────────────────────

/** Which output handle types can connect to which input handle types. */
const VALID_CONNECTIONS: Record<string, string[]> = {
  dicom: ['dicom'],
  bids: ['bids'],
  bold: ['bold', 'manifest'],
  freesurfer: ['freesurfer'],
  surface: ['surface'],
  manifest: ['manifest'],
  responses: ['responses'],
  features: ['features'],
  prepared: ['prepared'],
  results: ['results'],
}

export function isValidConnection(connection: Connection | Edge, nodes: Node[]): boolean {
  const sourceHandle = connection.sourceHandle ?? null
  const targetHandle = connection.targetHandle ?? null
  if (!sourceHandle || !targetHandle) return false
  // Prevent self-connections
  if (connection.source === connection.target) return false
  // Extract data type from handle id (format: "output-bold", "input-bids")
  const sourceType = sourceHandle.replace('output-', '')
  const targetType = targetHandle.replace('input-', '')
  const allowed = VALID_CONNECTIONS[sourceType]
  return allowed ? allowed.includes(targetType) : false
}

// ── Auto-layout ─────────────────────────────────────────────────────────

const NODE_WIDTH = 220
const NODE_HEIGHT = 120

type Measured = { width?: number; height?: number } | undefined

function _sizeOf(node: Node): { w: number; h: number } {
  // xyflow v12 fills `measured` after the first render with the real
  // DOM size. Fall back to defaults on the first pass.
  const m = (node as Node & { measured?: Measured }).measured
  return {
    w: m?.width && m.width > 0 ? m.width : NODE_WIDTH,
    h: m?.height && m.height > 0 ? m.height : NODE_HEIGHT,
  }
}

export function autoLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  // Generous separators so even worst-case nodes have breathing room;
  // dagre uses these as minimums, not maximums.
  g.setGraph({ rankdir: 'TB', ranksep: 120, nodesep: 80 })

  const sizes = new Map<string, { w: number; h: number }>()
  nodes.forEach((node) => {
    const s = _sizeOf(node)
    sizes.set(node.id, s)
    g.setNode(node.id, { width: s.w, height: s.h })
  })
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  return nodes.map((node) => {
    const pos = g.node(node.id)
    const s = sizes.get(node.id) ?? { w: NODE_WIDTH, h: NODE_HEIGHT }
    return {
      ...node,
      position: {
        x: pos.x - s.w / 2,
        y: pos.y - s.h / 2,
      },
    }
  })
}

/** Signature of all nodes' measured sizes; changes when the DOM
 *  measures something new. Used by callers to decide whether a
 *  re-layout pass is worth running. */
export function measuredSignature(nodes: Node[]): string {
  return nodes
    .map((n) => {
      const m = (n as Node & { measured?: Measured }).measured
      return `${n.id}:${m?.width ?? 0}x${m?.height ?? 0}`
    })
    .join('|')
}

// ── Default edge style ──────────────────────────────────────────────────

function makeEdge(id: string, source: string, sourceHandle: string, target: string, targetHandle: string): Edge {
  return {
    id,
    source,
    sourceHandle,
    target,
    targetHandle,
    type: 'smoothstep',
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { stroke: '#4a4a6a', strokeWidth: 2 },
  }
}

// ── Templates ───────────────────────────────────────────────────────────

function makeNode(id: string, stageType: StageType, label: string, summary: string[]): Node {
  return {
    id,
    type: 'stage',
    position: { x: 0, y: 0 },
    data: { stageType, label, status: 'pending', config: {}, summary },
  }
}

export interface GraphTemplate {
  name: string
  description: string
  build: () => { nodes: Node[]; edges: Edge[] }
}

export const TEMPLATES: GraphTemplate[] = [
  {
    name: 'Full Pipeline',
    description: 'DICOM → BIDS → fmriprep → Autoflatten → Analysis',
    build: () => {
      const nodes = [
        makeNode('source', 'source', 'DICOM Source', ['path: /data/dicoms/']),
        makeNode('convert', 'convert', 'DICOM → BIDS', ['heuristic: (select)']),
        makeNode('preproc', 'preproc', 'Preprocessing', ['mode: full', 'backend: fmriprep']),
        makeNode('autoflatten', 'autoflatten', 'Autoflatten', ['backend: pyflatten']),
        makeNode('response', 'response_loader', 'Response Loader', ['loader: preproc']),
        makeNode('features', 'features', 'Features', ['(add features)']),
        makeNode('prepare', 'prepare', 'Prepare', ['trim → zscore → concat']),
        makeNode('model', 'model', 'Model', ['type: bootstrap_ridge']),
        makeNode('report', 'report', 'Report', ['flatmap, metrics']),
      ]
      const edges = [
        makeEdge('e-src-cnv', 'source', 'output-dicom', 'convert', 'input-dicom'),
        makeEdge('e-cnv-pre', 'convert', 'output-bids', 'preproc', 'input-bids'),
        makeEdge('e-pre-af', 'preproc', 'output-freesurfer', 'autoflatten', 'input-freesurfer'),
        makeEdge('e-pre-rsp', 'preproc', 'output-manifest', 'response', 'input-manifest'),
        makeEdge('e-af-mod', 'autoflatten', 'output-surface', 'model', 'input-surface'),
        makeEdge('e-rsp-pp', 'response', 'output-responses', 'prepare', 'input-responses'),
        makeEdge('e-feat-pp', 'features', 'output-features', 'prepare', 'input-features'),
        makeEdge('e-pp-mod', 'prepare', 'output-prepared', 'model', 'input-prepared'),
        makeEdge('e-mod-rpt', 'model', 'output-results', 'report', 'input-results'),
      ]
      return { nodes: autoLayout(nodes, edges), edges }
    },
  },
  {
    name: 'Analysis Only',
    description: 'From existing preprocessed data → Analysis',
    build: () => {
      const nodes = [
        makeNode('response', 'response_loader', 'Response Loader', ['loader: preproc']),
        makeNode('features', 'features', 'Features', ['(add features)']),
        makeNode('prepare', 'prepare', 'Prepare', ['trim → zscore → concat']),
        makeNode('model', 'model', 'Model', ['type: bootstrap_ridge']),
        makeNode('report', 'report', 'Report', ['flatmap, metrics']),
      ]
      const edges = [
        makeEdge('e-rsp-pp', 'response', 'output-responses', 'prepare', 'input-responses'),
        makeEdge('e-feat-pp', 'features', 'output-features', 'prepare', 'input-features'),
        makeEdge('e-pp-mod', 'prepare', 'output-prepared', 'model', 'input-prepared'),
        makeEdge('e-mod-rpt', 'model', 'output-results', 'report', 'input-results'),
      ]
      return { nodes: autoLayout(nodes, edges), edges }
    },
  },
  {
    name: 'Preprocessing Only',
    description: 'DICOM → BIDS → fmriprep → Autoflatten',
    build: () => {
      const nodes = [
        makeNode('source', 'source', 'DICOM Source', ['path: /data/dicoms/']),
        makeNode('convert', 'convert', 'DICOM → BIDS', ['heuristic: (select)']),
        makeNode('preproc', 'preproc', 'Preprocessing', ['mode: full', 'backend: fmriprep']),
        makeNode('autoflatten', 'autoflatten', 'Autoflatten', ['backend: pyflatten']),
      ]
      const edges = [
        makeEdge('e-src-cnv', 'source', 'output-dicom', 'convert', 'input-dicom'),
        makeEdge('e-cnv-pre', 'convert', 'output-bids', 'preproc', 'input-bids'),
        makeEdge('e-pre-af', 'preproc', 'output-freesurfer', 'autoflatten', 'input-freesurfer'),
      ]
      return { nodes: autoLayout(nodes, edges), edges }
    },
  },
]

// ── Graph <-> YAML serialization ────────────────────────────────────────

interface GraphYaml {
  workflow?: string
  nodes: Record<string, { type: StageType; label?: string; config?: Record<string, unknown> }>
  edges: Array<{ from: string; out: string; to: string; in: string }>
}

export function graphToYaml(nodes: Node[], edges: Edge[], workflowName?: string): string {
  const doc: GraphYaml = {
    ...(workflowName ? { workflow: workflowName } : {}),
    nodes: {},
    edges: [],
  }
  for (const n of nodes) {
    const data = n.data as StageNodeData
    const cfg = data.config || {}
    doc.nodes[n.id] = {
      type: data.stageType,
      ...(data.label && data.label !== data.stageType ? { label: data.label } : {}),
      ...(Object.keys(cfg).length > 0 ? { config: cfg } : {}),
    }
  }
  for (const e of edges) {
    doc.edges.push({
      from: e.source,
      out: (e.sourceHandle || '').replace('output-', ''),
      to: e.target,
      in: (e.targetHandle || '').replace('input-', ''),
    })
  }
  return yaml.dump(doc, { indent: 2, lineWidth: 100, noRefs: true, sortKeys: false })
}

export function yamlToGraph(
  yamlString: string,
): { nodes: Node[]; edges: Edge[]; workflow?: string } {
  const doc = yaml.load(yamlString) as GraphYaml | null
  if (!doc || typeof doc !== 'object') {
    throw new Error('YAML root must be an object')
  }
  if (!doc.nodes || typeof doc.nodes !== 'object') {
    throw new Error("YAML must contain a 'nodes' mapping")
  }

  const nodes: Node[] = Object.entries(doc.nodes).map(([id, spec]) => {
    const stageType = spec.type as StageType
    const label = spec.label || stageType
    const config = spec.config || {}
    return {
      id,
      type: 'stage',
      position: { x: 0, y: 0 },
      data: {
        stageType,
        label,
        status: 'pending',
        config,
        summary: [],
      },
    }
  })

  const edges: Edge[] = (doc.edges || []).map((e, i) => {
    const sourceHandle = `output-${e.out}`
    const targetHandle = `input-${e.in}`
    return makeEdge(`e-${e.from}-${e.to}-${i}`, e.from, sourceHandle, e.to, targetHandle)
  })

  return { nodes: autoLayout(nodes, edges), edges, workflow: doc.workflow }
}

// ── Store ───────────────────────────────────────────────────────────────

interface GraphState {
  nodes: Node[]
  edges: Edge[]
  selectedNodeId: string | null
  detailOpen: boolean

  // YAML panel
  yamlString: string
  yamlErrors: string[]
  yamlEditing: boolean
  workflowName: string

  // Actions
  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  selectNode: (id: string | null) => void
  closeDetail: () => void
  updateNodeConfig: (id: string, config: Record<string, unknown>) => void
  updateNodeSummary: (id: string, summary: string[]) => void
  loadTemplate: (name: string) => void
  relayout: () => void
  addNode: (stageType: StageType, label: string) => void
  removeNode: (id: string) => void

  // YAML sync
  syncYamlFromGraph: () => void
  setYamlDirect: (yaml: string) => void
  applyYaml: () => void
  setWorkflowName: (name: string) => void
}

let nodeCounter = 100

export const useGraphStore = create<GraphState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  detailOpen: false,

  yamlString: '',
  yamlErrors: [],
  yamlEditing: false,
  workflowName: '',

  onNodesChange: (changes) => {
    set({ nodes: applyNodeChanges(changes, get().nodes) })
    get().syncYamlFromGraph()
  },

  onEdgesChange: (changes) => {
    set({ edges: applyEdgeChanges(changes, get().edges) })
    get().syncYamlFromGraph()
  },

  onConnect: (connection) => {
    if (!isValidConnection(connection, get().nodes)) return
    const id = `e-${connection.source}-${connection.target}-${Date.now()}`
    const edge = makeEdge(
      id,
      connection.source!,
      connection.sourceHandle!,
      connection.target!,
      connection.targetHandle!,
    )
    set({ edges: [...get().edges, edge] })
    get().syncYamlFromGraph()
  },

  selectNode: (id) => {
    set({ selectedNodeId: id, detailOpen: id !== null })
  },

  closeDetail: () => {
    set({ selectedNodeId: null, detailOpen: false })
  },

  updateNodeConfig: (id, config) => {
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, config } } : n,
      ),
    })
    get().syncYamlFromGraph()
  },

  updateNodeSummary: (id, summary) => {
    set({
      nodes: get().nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, summary } } : n,
      ),
    })
  },

  loadTemplate: (name) => {
    const tmpl = TEMPLATES.find((t) => t.name === name)
    if (!tmpl) return
    const { nodes, edges } = tmpl.build()
    set({ nodes, edges, selectedNodeId: null, detailOpen: false, yamlErrors: [] })
    get().syncYamlFromGraph()
  },

  relayout: () => {
    const { nodes, edges } = get()
    set({ nodes: autoLayout(nodes, edges) })
  },

  addNode: (stageType, label) => {
    const id = `node-${++nodeCounter}`
    const node = makeNode(id, stageType, label, [])
    // Place new node below existing ones
    const maxY = get().nodes.reduce((max, n) => Math.max(max, n.position.y), 0)
    node.position = { x: 200, y: maxY + 160 }
    set({ nodes: [...get().nodes, node] })
    get().syncYamlFromGraph()
  },

  removeNode: (id) => {
    set({
      nodes: get().nodes.filter((n) => n.id !== id),
      edges: get().edges.filter((e) => e.source !== id && e.target !== id),
      selectedNodeId: get().selectedNodeId === id ? null : get().selectedNodeId,
      detailOpen: get().selectedNodeId === id ? false : get().detailOpen,
    })
    get().syncYamlFromGraph()
  },

  syncYamlFromGraph: () => {
    const { nodes, edges, workflowName, yamlEditing } = get()
    if (yamlEditing) return
    try {
      const yamlString = graphToYaml(nodes, edges, workflowName || undefined)
      set({ yamlString, yamlErrors: [] })
    } catch (e) {
      set({ yamlErrors: [String(e)] })
    }
  },

  setYamlDirect: (yamlString) => {
    set({ yamlString, yamlEditing: true })
  },

  applyYaml: () => {
    try {
      const { nodes, edges, workflow } = yamlToGraph(get().yamlString)
      set({
        nodes,
        edges,
        workflowName: workflow ?? get().workflowName,
        yamlErrors: [],
        yamlEditing: false,
      })
    } catch (e) {
      set({ yamlErrors: [String(e)] })
    }
  },

  setWorkflowName: (name) => {
    set({ workflowName: name })
    get().syncYamlFromGraph()
  },
}))
