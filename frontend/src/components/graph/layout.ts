/** dagre layout for node graphs: left to right, each node sized by its port count. */
import dagre from 'dagre'

export const NODE_WIDTH = 210
export const HEADER_H = 34
export const ROW_H = 20

export interface LayoutNode { id: string; type: string; position?: { x: number; y: number } }
export interface LayoutDoc { nodes: LayoutNode[]; edges: { source: string; target: string }[] }

export function nodeHeight(nInputs: number, nOutputs: number): number {
  return HEADER_H + Math.max(nInputs, nOutputs, 1) * ROW_H + 10
}

export function layoutPositions(
  doc: LayoutDoc,
  ports: (node: LayoutNode) => { inputs: number; outputs: number },
): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 90, marginx: 20, marginy: 20 })
  for (const n of doc.nodes) {
    const p = ports(n)
    g.setNode(n.id, { width: NODE_WIDTH, height: nodeHeight(p.inputs, p.outputs) })
  }
  for (const e of doc.edges) {
    if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target)
  }
  dagre.layout(g)
  const out: Record<string, { x: number; y: number }> = {}
  for (const n of doc.nodes) {
    const pos = g.node(n.id)
    if (!pos) continue
    out[n.id] = { x: pos.x - NODE_WIDTH / 2, y: pos.y - pos.height / 2 }
  }
  return out
}

/** True when every node still sits at the default (0,0), i.e. was never laid out. */
export function needsLayout(doc: LayoutDoc): boolean {
  return doc.nodes.length > 1 && doc.nodes.every((n) => (n.position?.x ?? 0) === 0 && (n.position?.y ?? 0) === 0)
}
