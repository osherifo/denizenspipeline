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

export function autoLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', ranksep: 80, nodesep: 60 })

  nodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  return nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })
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

// ── Store ───────────────────────────────────────────────────────────────

interface GraphState {
  nodes: Node[]
  edges: Edge[]
  selectedNodeId: string | null
  detailOpen: boolean

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
}

let nodeCounter = 100

export const useGraphStore = create<GraphState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  detailOpen: false,

  onNodesChange: (changes) => {
    set({ nodes: applyNodeChanges(changes, get().nodes) })
  },

  onEdgesChange: (changes) => {
    set({ edges: applyEdgeChanges(changes, get().edges) })
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
    set({ nodes, edges, selectedNodeId: null, detailOpen: false })
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
  },

  removeNode: (id) => {
    set({
      nodes: get().nodes.filter((n) => n.id !== id),
      edges: get().edges.filter((e) => e.source !== id && e.target !== id),
      selectedNodeId: get().selectedNodeId === id ? null : get().selectedNodeId,
      detailOpen: get().selectedNodeId === id ? false : get().detailOpen,
    })
  },
}))
