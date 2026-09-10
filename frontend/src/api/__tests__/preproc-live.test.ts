/** API client coverage for the new endpoints landed on this branch:
 *  - GET /preproc/runs/{id}      (run detail with live nipype-node status)
 *  - Structural-QC review         (in-browser structural sign-off)
 */

import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { fetchPreprocRunLive } from '../client'
import {
  fetchReview,
  saveReview,
  fetchFreeviewCommand,
  reportUrl,
  fsFileUrl,
} from '../structural-qc'


describe('preproc /live endpoint', () => {
  it('fetches a live status block', async () => {
    server.use(
      http.get('/api/preproc/runs/abc', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('nipype')).toBe('true')
        return HttpResponse.json({
          run_id: 'abc',
          subject: 'sub01',
          backend: 'fmriprep',
          status: 'running',
          pid: 1234,
          started_at: 0,
          finished_at: 0,
          is_reattached: false,
          manifest_path: null,
          error: null,
          config_path: null,
          log_path: null,
          nipype_status: {
            counts: { running: 2, ok: 5, failed: 1, total_seen: 8 },
            recent_nodes: [],
          },
        })
      }),
    )
    const r = await fetchPreprocRunLive('abc')
    expect(r.nipype_status.counts.ok).toBe(5)
    expect(r.nipype_status.counts.failed).toBe(1)
  })

  it('throws on a 404', async () => {
    server.use(
      http.get('/api/preproc/runs/missing', () => new HttpResponse(null, { status: 404 })),
    )
    await expect(fetchPreprocRunLive('missing')).rejects.toThrow(/404/)
  })
})


describe('structural-qc API client', () => {
  it('fetches a review', async () => {
    server.use(
      http.get('/api/preproc/subjects/sub01/structural-qc', () =>
        HttpResponse.json({
          dataset: 'ds', subject: 'sub01', status: 'approved',
          reviewer: 'omar', timestamp: '2026-05-04', notes: '',
          freeview_command_used: null,
        })),
    )
    const r = await fetchReview('sub01')
    expect(r.status).toBe('approved')
    expect(r.reviewer).toBe('omar')
  })

  it('saves a review with the right body', async () => {
    let captured: any = null
    server.use(
      http.post('/api/preproc/subjects/sub01/structural-qc', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({
          saved: true,
          path: '/tmp/r.yaml',
          review: {
            dataset: 'ds', subject: 'sub01', status: captured.status,
            reviewer: captured.reviewer, timestamp: '2026-05-04',
            notes: captured.notes ?? '', freeview_command_used: null,
          },
        })
      }),
    )
    const r = await saveReview('sub01', {
      status: 'needs_edits', reviewer: 'omar', notes: 'fix the pial',
    })
    expect(r.saved).toBe(true)
    expect(captured.status).toBe('needs_edits')
    expect(captured.notes).toBe('fix the pial')
  })

  it('fetches a freeview command', async () => {
    server.use(
      http.get('/api/preproc/subjects/sub01/structural-qc/freeview-command', () =>
        HttpResponse.json({
          command: 'freeview -v T1.mgz',
          fs_subject_dir: '/fs/sub01',
        })),
    )
    const r = await fetchFreeviewCommand('sub01')
    expect(r.command).toContain('freeview')
  })

  it('builds a report URL', () => {
    expect(reportUrl('sub01')).toBe('/api/preproc/subjects/sub01/structural-qc/report')
  })

  it('builds an FS-file URL with encoded rel param', () => {
    expect(fsFileUrl('sub01', 'mri/T1.mgz'))
      .toBe('/api/preproc/subjects/sub01/structural-qc/fs-file?rel=mri%2FT1.mgz')
  })
})
