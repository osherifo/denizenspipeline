import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

// The run socket is not under test; a stub keeps launch() off the network.
class FakeSocket {
  onmessage: ((msg: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  constructor(public url: string) {}
  close() { this.onclose?.() }
}
beforeAll(() => { vi.stubGlobal('WebSocket', FakeSocket) })
afterAll(() => { vi.unstubAllGlobals() })

import { formatInputValue, nodeIdFor, parseInputValue, useAnalysisGraphStore } from '../analysis-graph-store'
import { analysisRequests } from '../../test/mocks/handlers.analysis-graphs'

const get = () => useAnalysisGraphStore.getState()

describe('analysis graph store', () => {
  it('parses run-panel values without turning ids into numbers', () => {
    expect(parseInputValue('01')).toBe('01')
    expect(parseInputValue('[run1, run2]')).toEqual(['run1', 'run2'])
    expect(formatInputValue(['a'])).toBe('["a"]')
    expect(nodeIdFor('model:bootstrap_ridge')).toBe('bootstrap_ridge')
    expect(nodeIdFor('qa_reporter:model.score_histogram')).toBe('score_histogram')
  })

  it('loads the catalog and a template with its input defaults', async () => {
    await Promise.all([get().loadCatalog(), get().loadTemplates()])
    await get().loadTemplate('analyze')
    expect(get().catalog.map((n) => n.type)).toContain('model:bootstrap_ridge')
    expect(get().templates[0].name).toBe('analyze')
    expect(get().graph.nodes.map((n) => n.id)).toEqual(['prepare', 'bootstrap_ridge'])
    expect(get().inputValues).toEqual({ subject: '', output_dir: '', test_runs: '["run1"]' })
    expect(get().dirty).toBe(true)
  })

  it('adds nodes, fans in feature spaces in order and replaces single feeds', async () => {
    await get().loadCatalog()
    get().newGraph()
    expect([
      get().addNode('feature_source:filesystem'), get().addNode('feature_source:filesystem'), get().addNode('utility:bundle_features'),
    ]).toEqual(['filesystem', 'filesystem_2', 'bundle_features'])
    get().addEdge({ source: 'filesystem', sourceHandle: 'feature', target: 'bundle_features', targetHandle: 'features' })
    get().addEdge({ source: 'filesystem_2', sourceHandle: 'feature', target: 'bundle_features', targetHandle: 'features' })
    const into = () => get().graph.edges.filter((e) => e.target === 'bundle_features').map((e) => e.source)
    expect(into()).toEqual(['filesystem', 'filesystem_2'])
    get().moveEdge(get().graph.edges[1].id, -1)
    expect(into()).toEqual(['filesystem_2', 'filesystem'])

    get().addNode('response_loader:local')
    get().addNode('response_loader:local')
    get().addNode('preparer:default')
    get().addEdge({ source: 'local', sourceHandle: 'responses', target: 'default', targetHandle: 'responses' })
    get().addEdge({ source: 'local_2', sourceHandle: 'responses', target: 'default', targetHandle: 'responses' })
    expect(get().graph.edges.filter((e) => e.target === 'default').map((e) => e.source)).toEqual(['local_2'])

    get().removeNode('bundle_features')
    expect(get().graph.edges.some((e) => e.source === 'bundle_features' || e.target === 'bundle_features')).toBe(false)
    expect(get().addNode('model:not_in_catalog')).toBeNull()
  })

  it('saves input values with the graph, validates, launches and tracks node events', async () => {
    get().newGraph()
    get().setInputValue('subject', 'sub01')
    get().setInputValue('output_dir', '/data/out')
    await get().save('mine')
    expect((analysisRequests.saved as { graph: { run_defaults: unknown } }).graph.run_defaults)
      .toEqual({ inputs: { subject: 'sub01', output_dir: '/data/out' } })
    expect(get().graphName).toBe('mine')
    expect(get().dirty).toBe(false)

    await get().validate()
    expect(get().validation).toEqual({ ok: true, errors: [] })

    expect(await get().launch()).toBe('graph-run-1')
    expect((analysisRequests.run as { inputs: unknown }).inputs).toEqual({ subject: 'sub01', output_dir: '/data/out' })
    get().applyRunEvent({ event: 'node_start', node_id: 'x' })
    expect(get().runStatus.x.status).toBe('running')
    get().applyRunEvent({ event: 'node_fail', node_id: 'x', elapsed: 2, error: 'boom' })
    expect(get().runStatus.x).toEqual({ status: 'failed', durationS: 2, error: 'boom' })
    get().applyRunEvent({ event: 'run_done' })
    expect(get().runState).toBe('done')
  })

  it('opens a saved graph with its run values', async () => {
    await get().loadGraph('saved_graph')
    expect(get().graphName).toBe('saved_graph')
    expect(get().inputValues.subject).toBe('sub01')
    expect(get().dirty).toBe(false)
  })
})
