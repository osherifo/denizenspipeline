/** Pure edits on a node-graph document, shared by the pipeline and analysis graph stores.
 *  Every function returns a new document and leaves its argument untouched. */

export interface EditableNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: { params: Record<string, unknown> }
}

export interface EditableEdge {
  id: string
  source: string
  target: string
  sourceHandle: string
  targetHandle: string
}

export interface EditableDoc<N extends EditableNode = EditableNode> {
  nodes: N[]
  edges: EditableEdge[]
}

export function uniqueId(base: string, taken: Set<string>): string {
  if (!taken.has(base)) return base
  let i = 2
  while (taken.has(`${base}_${i}`)) i += 1
  return `${base}_${i}`
}

/** Topological order (Kahn); falls back to declaration order on a cycle. */
export function topoOrder<N extends EditableNode>(doc: EditableDoc<N>): N[] {
  const indeg = new Map<string, number>(doc.nodes.map((n) => [n.id, 0]))
  const adj = new Map<string, string[]>(doc.nodes.map((n) => [n.id, []]))
  for (const e of doc.edges) {
    if (indeg.has(e.target)) indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1)
    adj.get(e.source)?.push(e.target)
  }
  const queue = doc.nodes.filter((n) => indeg.get(n.id) === 0).map((n) => n.id)
  const out: string[] = []
  while (queue.length) {
    const id = queue.shift() as string
    out.push(id)
    for (const nxt of adj.get(id) ?? []) {
      indeg.set(nxt, (indeg.get(nxt) ?? 0) - 1)
      if (indeg.get(nxt) === 0) queue.push(nxt)
    }
  }
  if (out.length !== doc.nodes.length) return doc.nodes
  const byId = new Map(doc.nodes.map((n) => [n.id, n]))
  return out.map((id) => byId.get(id) as N)
}

export function addNodeTo<N extends EditableNode, D extends EditableDoc<N>>(doc: D, node: N): D {
  return { ...doc, nodes: [...doc.nodes, node] }
}

/** Remove a node and every edge touching it. */
export function removeNodeFrom<D extends EditableDoc>(doc: D, id: string): D {
  return {
    ...doc,
    nodes: doc.nodes.filter((n) => n.id !== id),
    edges: doc.edges.filter((e) => e.source !== id && e.target !== id),
  }
}

export function setNodeParams<D extends EditableDoc>(doc: D, id: string, params: Record<string, unknown>): D {
  return { ...doc, nodes: doc.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, params } } : n)) }
}

export function patchNodeData<D extends EditableDoc>(doc: D, id: string, patch: Record<string, unknown>): D {
  return { ...doc, nodes: doc.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)) }
}

export function moveNodeTo<D extends EditableDoc>(doc: D, id: string, position: { x: number; y: number }): D {
  return { ...doc, nodes: doc.nodes.map((n) => (n.id === id ? { ...n, position } : n)) }
}

/** Add an edge. An input takes one feed unless ``fanIn`` is set, in which case
 *  edges into it accumulate in order. An identical edge is not added twice. */
export function connect<D extends EditableDoc>(doc: D, edge: Omit<EditableEdge, 'id'>, opts: { fanIn?: boolean } = {}): D {
  const same = (e: EditableEdge) => e.source === edge.source && e.target === edge.target
    && e.sourceHandle === edge.sourceHandle && e.targetHandle === edge.targetHandle
  if (doc.edges.some(same)) return doc
  const kept = opts.fanIn
    ? doc.edges
    : doc.edges.filter((e) => !(e.target === edge.target && e.targetHandle === edge.targetHandle))
  const id = uniqueId(`e_${edge.source}_${edge.target}_${edge.targetHandle}`, new Set(kept.map((e) => e.id)))
  return { ...doc, edges: [...kept, { id, ...edge }] }
}

export function disconnect<D extends EditableDoc>(doc: D, id: string): D {
  return { ...doc, edges: doc.edges.filter((e) => e.id !== id) }
}

/** Move an edge one place earlier (-1) or later (+1) among the edges into the same input. */
export function moveFanInEdge<D extends EditableDoc>(doc: D, id: string, delta: -1 | 1): D {
  const edge = doc.edges.find((e) => e.id === id)
  if (!edge) return doc
  const siblings = doc.edges
    .map((e, i) => ({ e, i }))
    .filter(({ e }) => e.target === edge.target && e.targetHandle === edge.targetHandle)
  const pos = siblings.findIndex(({ e }) => e.id === id)
  const other = siblings[pos + delta]
  if (!other) return doc
  const edges = [...doc.edges]
  const i = siblings[pos].i
  ;[edges[i], edges[other.i]] = [edges[other.i], edges[i]]
  return { ...doc, edges }
}
