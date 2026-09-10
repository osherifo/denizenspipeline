/** dagre layout for pipeline graphs — left-to-right, sized by port count. */
import dagre from 'dagre'
import type { PipelineDoc } from '../../api/types'

export const NODE_WIDTH = 210
export const HEADER_H = 34
export const ROW_H = 20

export function nodeHeight(nInputs: number, nOutputs: number): number {
  return HEADER_H + Math.max(nInputs, nOutputs, 1) * ROW_H + 10
}

export function layoutPositions(
  pipeline: PipelineDoc,
  ports: (type: string) => { inputs: number; outputs: number },
): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 90, marginx: 20, marginy: 20 })
  for (const n of pipeline.nodes) {
    const p = ports(n.type)
    g.setNode(n.id, { width: NODE_WIDTH, height: nodeHeight(p.inputs, p.outputs) })
  }
  for (const e of pipeline.edges) {
    if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target)
  }
  dagre.layout(g)
  const out: Record<string, { x: number; y: number }> = {}
  for (const n of pipeline.nodes) {
    const pos = g.node(n.id)
    if (!pos) continue
    out[n.id] = { x: pos.x - NODE_WIDTH / 2, y: pos.y - pos.height / 2 }
  }
  return out
}

/** True when every node still sits at the default (0,0) — i.e. never laid out. */
export function needsLayout(pipeline: PipelineDoc): boolean {
  return pipeline.nodes.length > 1 && pipeline.nodes.every((n) => (n.position?.x ?? 0) === 0 && (n.position?.y ?? 0) === 0)
}
