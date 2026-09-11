/** Swapping a node for another implementation of its kind (another model, another loader, ...). */
import type { AnalysisGraphDoc, AnalysisNodeInfo } from '../../api/types'
import { uniqueId } from '../../stores/graph-edit-slice'
import { ANY, compatible, type Lattice } from '../graph/connection'
import { categoryOf, nodeIdFor } from './describe'

/** Categories that fill the same place in a graph: extracted and precomputed features both yield a feature space. */
const FAMILIES: Record<string, string> = { feature_extractor: 'features', feature_source: 'features' }

export function familyOf(type: string): string {
  const category = categoryOf(type)
  return FAMILIES[category] ?? category
}

export interface Replacement {
  type: string
  /** Required inputs of the replacement that nothing feeds yet. */
  missingRequired: string[]
}

/** Node types of the same family that keep every current connection of ``nodeId`` type-compatible. */
export function replacementsFor(
  graph: AnalysisGraphDoc, nodeId: string, catalog: AnalysisNodeInfo[], lattice: Lattice,
): Replacement[] {
  const node = graph.nodes.find((n) => n.id === nodeId)
  if (!node) return []
  const infoOf = (id: string) => {
    const other = graph.nodes.find((n) => n.id === id)
    return other ? catalog.find((c) => c.type === other.type) : undefined
  }
  const incoming = graph.edges.filter((e) => e.target === nodeId)
  const outgoing = graph.edges.filter((e) => e.source === nodeId)
  const feeds: Record<string, number> = {}
  for (const e of incoming) feeds[e.targetHandle] = (feeds[e.targetHandle] ?? 0) + 1
  const fed = new Set([
    ...incoming.map((e) => e.targetHandle),
    ...Object.keys(node.data.literal_inputs ?? {}),
    ...Object.keys(node.data.bindings ?? {}),
  ])
  const family = familyOf(node.type)

  const fits = (candidate: AnalysisNodeInfo) => {
    for (const e of incoming) {
      const spec = candidate.inputs[e.targetHandle]
      const source = infoOf(e.source)?.outputs[e.sourceHandle]?.type ?? ANY
      if (!spec || !compatible(lattice, source, spec.type ?? ANY)) return false
      if (feeds[e.targetHandle] > 1 && !spec.multiple) return false
    }
    for (const e of outgoing) {
      const spec = candidate.outputs[e.sourceHandle]
      const target = infoOf(e.target)?.inputs[e.targetHandle]?.type ?? ANY
      if (!spec || !compatible(lattice, spec.type ?? ANY, target)) return false
    }
    return true
  }

  return catalog
    .filter((c) => c.type !== node.type && !c.hidden && familyOf(c.type) === family && fits(c))
    .map((c) => ({
      type: c.type,
      missingRequired: Object.entries(c.inputs).filter(([port, spec]) => spec.required && !fed.has(port)).map(([port]) => port),
    }))
    .sort((a, b) => nodeIdFor(a.type).localeCompare(nodeIdFor(b.type)))
}

/** Swap node ``nodeId`` to ``newType``: edges stay, params the new module also declares carry over,
 *  and an id derived from the old module name follows the new one. Returns the graph and the node's id. */
export function replaceNodeType(
  graph: AnalysisGraphDoc, nodeId: string, newType: string, catalog: AnalysisNodeInfo[],
): { graph: AnalysisGraphDoc; nodeId: string } {
  const node = graph.nodes.find((n) => n.id === nodeId)
  if (!node || node.type === newType) return { graph, nodeId }
  const oldModule = nodeIdFor(node.type)
  const newModule = nodeIdFor(newType)
  let base = nodeId
  if (nodeId === oldModule || new RegExp(`^${oldModule}_\\d+$`).test(nodeId)) base = newModule
  else if (nodeId.endsWith(`:${oldModule}`)) base = `${nodeId.slice(0, -oldModule.length)}${newModule}`
  const newId = base === nodeId ? nodeId : uniqueId(base, new Set(graph.nodes.filter((n) => n.id !== nodeId).map((n) => n.id)))

  const schema = catalog.find((c) => c.type === newType)?.params_schema ?? {}
  const params = Object.fromEntries(Object.entries(node.data.params ?? {}).filter(([key]) => key in schema))
  const rename = (id: string) => (id === nodeId ? newId : id)
  return {
    nodeId: newId,
    graph: {
      ...graph,
      nodes: graph.nodes.map((n) => (n.id === nodeId ? { ...n, id: newId, type: newType, data: { ...n.data, params } } : n)),
      edges: graph.edges.map((e) => ({ ...e, source: rename(e.source), target: rename(e.target) })),
    },
  }
}
