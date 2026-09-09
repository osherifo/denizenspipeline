import { describe, expect, it } from 'vitest'
import { tabsFor, type NodePopupContext } from '../index'
import { buildRunNode, FMRIPREP_RUN_NODE } from '../../../../test/mocks/handlers.preproc-pipelines'

const ctx = (over: Partial<NodePopupContext> = {}): NodePopupContext => ({ runId: 'r', nodeId: 'smooth', record: buildRunNode(), checkpoints: [], isRunning: false, ...over })

describe('tabsFor', () => {
  it('a plain node gets only the generic tabs', () => {
    expect(tabsFor(ctx()).map((t) => t.id)).toEqual(['overview', 'outputs'])
  })
  it('capabilities unlock tabs; checkpoints show when any exist', () => {
    const ids = tabsFor(ctx({ nodeId: 'fp', record: FMRIPREP_RUN_NODE })).map((t) => t.id)
    expect(ids).toEqual(['overview', 'outputs', 'checkpoints', 'inner', 'log', 'summary', 'report', 'structural_qc'])
    const withCp = tabsFor(ctx({ checkpoints: [{ node: 'w.smooth' } as never] })).map((t) => t.id)
    expect(withCp).toContain('checkpoints')
  })
  it('an app override replaces the tab with the same id in place', () => {
    const tabs = tabsFor(ctx({ nodeId: 'fp', record: FMRIPREP_RUN_NODE }))
    expect(tabs.filter((t) => t.id === 'summary')).toHaveLength(1)
    expect(tabs.findIndex((t) => t.id === 'summary')).toBeLessThan(tabs.findIndex((t) => t.id === 'report'))
  })
  it('a node with a log on disk gets the Log tab even without declaring it', () => {
    expect(tabsFor(ctx({ record: buildRunNode({ has_log: true }) })).map((t) => t.id)).toContain('log')
  })
})
