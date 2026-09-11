import { describe, expect, it } from 'vitest'
import { describeAnalysisNode, nodeTypeForModule, PORT_TYPE_COLORS } from '../describe'
import { ANALYSIS_NODES } from '../../../test/mocks/handlers.analysis-graphs'

const catalog = new Map(ANALYSIS_NODES.map((n) => [n.type, n]))

describe('nodeTypeForModule', () => {
  it('maps a module category and name to its node type', () => {
    expect(nodeTypeForModule({ category: 'models', name: 'bootstrap_ridge', stage: 'model' })).toBe('model:bootstrap_ridge')
    expect(nodeTypeForModule({ category: 'qa_reporters', name: 'alpha_histogram', stage: 'model' })).toBe('qa_reporter:model.alpha_histogram')
  })
})

describe('describeAnalysisNode', () => {
  it('shows the category tag, typed ports and run status', () => {
    const describe_ = describeAnalysisNode(catalog, { ridge: { status: 'ok', durationS: 4 } })
    const card = describe_({ id: 'ridge', type: 'model:bootstrap_ridge' })
    expect(card.tag).toBe('model')
    expect(card.inputs).toEqual([{ name: 'prepared', color: PORT_TYPE_COLORS.PreparedData, title: 'PreparedData · required' }])
    expect(card.outputs.map((p) => p.name)).toEqual(['result'])
    expect(card.status).toBe('ok')
    expect(card.durationS).toBe(4)
  })

  it('marks isolated nodes, failures and unknown types', () => {
    const describe_ = describeAnalysisNode(catalog, { m: { status: 'failed', error: 'boom' } })
    expect(describe_({ id: 'm', type: 'reporter:metrics' }).badges?.map((b) => b.key)).toEqual(['isolate', 'error'])
    const unknown = describe_({ id: 'x', type: 'model:nope' })
    expect(unknown.badges?.[0].key).toBe('unknown')
    expect(unknown.inputs).toEqual([])
  })
})
