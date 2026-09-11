import { describe, expect, it } from 'vitest'
import type { AnalysisGraphDoc, AnalysisNodeInfo } from '../../../api/types'
import { latticeFrom } from '../../graph/connection'
import { replaceNodeType, replacementsFor } from '../replace'
import { ANALYSIS_NODES, PORT_TYPES } from '../../../test/mocks/handlers.analysis-graphs'

const lattice = latticeFrom(PORT_TYPES)
const node = (id: string, type: string, params: Record<string, unknown> = {}) => ({ id, type, data: { params }, position: { x: 0, y: 0 } })
const edge = (source: string, sourceHandle: string, target: string, targetHandle: string) => ({ id: `${source}-${target}-${targetHandle}`, source, sourceHandle, target, targetHandle })
const graphOf = (nodes: AnalysisGraphDoc['nodes'], edges: AnalysisGraphDoc['edges']): AnalysisGraphDoc => ({ name: 'g', scope: 'subject', inputs: {}, globals: {}, nodes, edges })

describe('replacementsFor', () => {
  it('offers the other implementations of the same kind that fit the connections', () => {
    const graph = graphOf([node('prepare', 'preparer:default'), node('bootstrap_ridge', 'model:bootstrap_ridge')],
      [edge('prepare', 'prepared', 'bootstrap_ridge', 'prepared')])
    expect(replacementsFor(graph, 'bootstrap_ridge', ANALYSIS_NODES, lattice)).toEqual([{ type: 'model:himalaya_ridge', missingRequired: [] }])
  })

  it('treats extracted and precomputed features as one kind and says what still needs connecting', () => {
    const connected = graphOf([node('skip', 'stimulus_loader:skip'), node('fs', 'feature_source:filesystem')],
      [edge('skip', 'stimuli', 'fs', 'stimuli')])
    expect(replacementsFor(connected, 'fs', ANALYSIS_NODES, lattice)).toEqual([{ type: 'feature_extractor:numwords', missingRequired: [] }])
    const alone = graphOf([node('fs', 'feature_source:filesystem')], [])
    expect(replacementsFor(alone, 'fs', ANALYSIS_NODES, lattice)).toEqual([{ type: 'feature_extractor:numwords', missingRequired: ['stimuli'] }])
  })

  it('leaves out implementations whose ports would break a connection', () => {
    const catalog: AnalysisNodeInfo[] = [
      ...ANALYSIS_NODES,
      { ...ANALYSIS_NODES.find((n) => n.type === 'model:himalaya_ridge')!, type: 'model:odd', module: 'odd', inputs: { data: { type: 'PreparedData', required: true } } },
    ]
    const graph = graphOf([node('prepare', 'preparer:default'), node('m', 'model:bootstrap_ridge')], [edge('prepare', 'prepared', 'm', 'prepared')])
    expect(replacementsFor(graph, 'm', catalog, lattice).map((r) => r.type)).toEqual(['model:himalaya_ridge'])
  })
})

describe('replaceNodeType', () => {
  const graph = graphOf(
    [node('prepare', 'preparer:default'), node('bootstrap_ridge', 'model:bootstrap_ridge', { n_boots: 5, alphas: 'logspace(0,2,5)' }), node('model:bootstrap_ridge', 'model:bootstrap_ridge'), node('mine', 'model:bootstrap_ridge')],
    [edge('prepare', 'prepared', 'bootstrap_ridge', 'prepared'), edge('prepare', 'prepared', 'model:bootstrap_ridge', 'prepared')],
  )

  it('keeps connections, carries over params the new module declares, and renames a derived id', () => {
    const { graph: next, nodeId } = replaceNodeType(graph, 'bootstrap_ridge', 'model:himalaya_ridge', ANALYSIS_NODES)
    expect(nodeId).toBe('himalaya_ridge')
    const swapped = next.nodes.find((n) => n.id === 'himalaya_ridge')!
    expect(swapped.type).toBe('model:himalaya_ridge')
    expect(swapped.data.params).toEqual({ alphas: 'logspace(0,2,5)' })
    expect(next.edges.some((e) => e.target === 'himalaya_ridge' && e.targetHandle === 'prepared')).toBe(true)
  })

  it('follows compiled ids and keeps ids the user chose', () => {
    expect(replaceNodeType(graph, 'model:bootstrap_ridge', 'model:himalaya_ridge', ANALYSIS_NODES).nodeId).toBe('model:himalaya_ridge')
    expect(replaceNodeType(graph, 'mine', 'model:himalaya_ridge', ANALYSIS_NODES).nodeId).toBe('mine')
  })
})
