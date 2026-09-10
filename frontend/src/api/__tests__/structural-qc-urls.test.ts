import { describe, expect, it } from 'vitest'
import { fsFileUrl, qcBase, reportUrl } from '../structural-qc'

describe('structural-qc URLs', () => {
  it('a bare subject keeps the subject route', () => {
    expect(reportUrl('sub01')).toBe('/api/preproc/subjects/sub01/structural-qc/report')
    expect(fsFileUrl('sub01', 'mri/T1.mgz')).toBe('/api/preproc/subjects/sub01/structural-qc/fs-file?rel=mri%2FT1.mgz')
  })
  it('a run source is scoped to the run and node, with a trailing slash on the report', () => {
    const src = { kind: 'run' as const, runId: 'pp 1', nodeId: 'fp', subject: '01' }
    expect(qcBase(src)).toBe('/api/preproc/runs/pp%201/nodes/fp')
    expect(reportUrl(src)).toBe('/api/preproc/runs/pp%201/nodes/fp/report/')
    expect(fsFileUrl(src, 'surf/lh.pial')).toBe('/api/preproc/runs/pp%201/nodes/fp/fs-file?rel=surf%2Flh.pial')
  })
})
