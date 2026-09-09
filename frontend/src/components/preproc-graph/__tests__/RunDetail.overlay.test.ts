import { describe, expect, it } from 'vitest'
import { checkpointOverlay, statusOverlay } from '../RunDetail'
import { buildRunDetail } from '../../../test/mocks/handlers.preproc-pipelines'

describe('run overlays', () => {
  it('maps events onto top-level node status', () => {
    const detail = buildRunDetail()
    const wf = detail.workflow!
    const out = statusOverlay(detail, [
      { event: 'node_start', node: `${wf}.source` },
      { event: 'node_done', node: `${wf}.source`, cached: true, duration_s: 0.5 },
      { event: 'node_start', node: `${wf}.smooth` },
      { event: 'node_start', node: `${wf}.smooth.inner` },   // nested: does not finish the parent
      { event: 'node_done', node: `${wf}.smooth.inner` },
    ])
    expect(out.source).toEqual({ status: 'cached', durationS: 0.5 })
    expect(out.smooth.status).toBe('running')
  })

  it('prefers the final result records over events', () => {
    const detail = buildRunDetail({
      status: 'done',
      result: { status: 'completed', duration_s: 2, errors: [], nodes: [
        { node_id: 'source', node_type: 'derivatives_source', kind: 'source', status: 'ok', duration_s: 1, work_dir: '', outputs: {}, error: null },
        { node_id: 'smooth', node_type: 'smooth', kind: 'interface', status: 'failed', duration_s: 1, work_dir: '', outputs: {}, error: 'boom' },
      ] },
    })
    const out = statusOverlay(detail, [])
    expect(out.smooth.status).toBe('failed')
  })

  it('aggregates checkpoints per node with the worst verdict', () => {
    const cps = [
      { node: 'wf.fp', verdict: 'ok' }, { node: 'wf.fp', verdict: 'bad' }, { node: 'wf.sm', verdict: 'suspicious' },
    ].map((c) => ({ ...c, stage: 'preproc', run_id: 'r', step: 's', subject: '01', metrics: {}, expectations: {}, soft_expectations: {}, thumbnail: null, detail: {}, t: 0, artifact: null, reasons: [] })) as never
    const out = checkpointOverlay(cps, 'wf')
    expect(out.fp).toEqual({ worst: 'bad', count: 2 })
    expect(out.sm).toEqual({ worst: 'suspicious', count: 1 })
  })
})
