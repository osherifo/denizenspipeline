/** API client coverage for the new endpoints landed on this branch:
 *  - GET /preproc/runs/{id}/live  (live nipype-node monitoring)
 *  - Post-preproc CRUD            (saved nipype workflows)
 *  - Structural-QC review         (in-browser structural sign-off)
 */

import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { fetchPreprocRunLive } from '../client'
import {
  fetchNipypeNodes,
  fetchWorkflows,
  fetchWorkflow,
  saveWorkflow,
  deleteWorkflow,
  validateGraph,
  startRun,
  getRun,
} from '../post-preproc'
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
      http.get('/api/preproc/runs/abc/live', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('cap')).toBe('200')
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

  it('passes a custom cap as query param', async () => {
    let observedCap: string | null = null
    server.use(
      http.get('/api/preproc/runs/xyz/live', ({ request }) => {
        observedCap = new URL(request.url).searchParams.get('cap')
        return HttpResponse.json({
          run_id: 'xyz', subject: 's', backend: 'fmriprep',
          status: 'done', pid: null, started_at: 0, finished_at: 0,
          is_reattached: false, manifest_path: null, error: null,
          config_path: null, log_path: null,
          nipype_status: { counts: { running: 0, ok: 0, failed: 0, total_seen: 0 }, recent_nodes: [] },
        })
      }),
    )
    await fetchPreprocRunLive('xyz', 50)
    expect(observedCap).toBe('50')
  })

  it('throws on a 404', async () => {
    server.use(
      http.get('/api/preproc/runs/missing/live',
        () => new HttpResponse('not found', { status: 404 }),
      ),
    )
    await expect(fetchPreprocRunLive('missing')).rejects.toThrow(/404/)
  })
})


describe('post-preproc API client', () => {
  it('fetches the registered nipype-node palette', async () => {
    server.use(
      http.get('/api/post-preproc/nodes', () =>
        HttpResponse.json([
          { name: 'smooth', docstring: '', inputs: ['in_file'], outputs: ['out_file'], params: {} },
          { name: 'mask_apply', docstring: '', inputs: ['in_file', 'mask_file'], outputs: ['out_file'], params: {} },
        ])),
    )
    const nodes = await fetchNipypeNodes()
    expect(nodes.map((n) => n.name)).toEqual(['smooth', 'mask_apply'])
  })

  it('lists saved workflows', async () => {
    server.use(
      http.get('/api/post-preproc/workflows', () =>
        HttpResponse.json([
          { name: 'smooth_only', description: '', inputs: ['in_file'], outputs: ['out_file'], n_nodes: 1 },
        ])),
    )
    const wfs = await fetchWorkflows()
    expect(wfs).toHaveLength(1)
    expect(wfs[0].name).toBe('smooth_only')
  })

  it('fetches a workflow by name (URL-encoded)', async () => {
    let observed = ''
    server.use(
      http.get('/api/post-preproc/workflows/:name', ({ params }) => {
        observed = String(params.name)
        return HttpResponse.json({
          name: observed,
          description: '',
          inputs: { in_file: { from: 'smo.in_file' } },
          outputs: { out_file: { from: 'smo.out_file' } },
          graph: { nodes: [], edges: [] },
        })
      }),
    )
    await fetchWorkflow('smooth/only')
    expect(observed).toBe('smooth/only')
  })

  it('saves a workflow with the right body', async () => {
    let captured: any = null
    server.use(
      http.post('/api/post-preproc/workflows', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({ saved: true, path: '/tmp/wf.yaml', name: 'wf' })
      }),
    )
    const result = await saveWorkflow({
      name: 'wf',
      description: 'd',
      graph: { nodes: [], edges: [] },
      inputs: { in_file: { from: 'a.in_file' } },
      outputs: {},
    })
    expect(result.saved).toBe(true)
    expect(captured.name).toBe('wf')
    expect(captured.description).toBe('d')
    expect(captured.inputs.in_file.from).toBe('a.in_file')
  })

  it('deletes a workflow', async () => {
    server.use(
      http.delete('/api/post-preproc/workflows/wf', () =>
        HttpResponse.json({ deleted: true, name: 'wf' }),
      ),
    )
    const r = await deleteWorkflow('wf')
    expect(r.deleted).toBe(true)
  })

  it('validates a graph', async () => {
    server.use(
      http.post('/api/post-preproc/graphs/validate', () =>
        HttpResponse.json({ valid: false, errors: ['Cycle detected'] })),
    )
    const result = await validateGraph({ nodes: [], edges: [] })
    expect(result.valid).toBe(false)
    expect(result.errors).toContain('Cycle detected')
  })

  it('starts a run', async () => {
    server.use(
      http.post('/api/post-preproc/run', () =>
        HttpResponse.json({
          run_id: 'r1',
          status: 'pending',
          output_dir: '/tmp/out/r1',
        })),
    )
    const handle = await startRun({
      subject: 'sub01',
      source_manifest_path: '/m.json',
      graph: { nodes: [], edges: [] },
      output_dir: '/tmp/out',
    })
    expect(handle.run_id).toBe('r1')
    expect(handle.status).toBe('pending')
  })

  it('gets a run', async () => {
    server.use(
      http.get('/api/post-preproc/runs/r1', () =>
        HttpResponse.json({
          run_id: 'r1', status: 'done', output_dir: '/tmp/out/r1',
          error: null, manifest: null,
        })),
    )
    const r = await getRun('r1')
    expect(r.status).toBe('done')
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
