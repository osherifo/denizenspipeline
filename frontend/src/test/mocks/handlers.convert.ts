import { http, HttpResponse } from 'msw'
import { buildConvertRun } from '../factories'

export const convertHandlers = [
  http.get('/api/convert/heuristics', () =>
    HttpResponse.json({
      heuristics: [
        { name: 'reading_heuristic', path: '/tmp/h.py', is_default: true, registered: true },
      ],
    }),
  ),
  http.get('/api/convert/heuristics/:name/code', ({ params }) =>
    HttpResponse.json({ name: params.name, code: '# heuristic' }),
  ),
  http.post('/api/convert/heuristics/save', () =>
    HttpResponse.json({ saved: true, name: 'h', path: '/tmp/h.py' }),
  ),
  http.post('/api/convert/heuristics/template', () =>
    HttpResponse.json({ code: '# template', name: 'my_study' }),
  ),
  http.delete('/api/convert/heuristics/:name', ({ params }) =>
    HttpResponse.json({ deleted: true, name: params.name }),
  ),
  http.get('/api/convert/tools', () =>
    HttpResponse.json({
      tools: [{ name: 'heudiconv', available: true, detail: '0.13.0' }],
    }),
  ),
  http.get('/api/convert/manifests', () => HttpResponse.json({ manifests: [] })),
  http.post('/api/convert/manifests/rescan', () => HttpResponse.json({ manifests: [] })),
  http.get('/api/convert/manifests/:subject', ({ params }) =>
    HttpResponse.json({ subject: params.subject, sessions: [], runs: [] }),
  ),
  http.post('/api/convert/manifests/:subject/validate', () =>
    HttpResponse.json({ errors: [] }),
  ),
  http.post('/api/convert/scan', () =>
    HttpResponse.json({
      source_dir: '/tmp',
      n_files: 10,
      subjects: ['01'],
      sessions: ['ses-01'],
      sample_dicoms: [],
    }),
  ),
  http.post('/api/convert/collect', () =>
    HttpResponse.json({ manifest: {}, manifest_path: '/tmp/m.json' }),
  ),
  http.post('/api/convert/run', () =>
    HttpResponse.json({ run_id: 'convert-1', status: 'started' }),
  ),
  http.post('/api/convert/batch/run', () =>
    HttpResponse.json({ batch_id: 'batch-1', status: 'started', n_jobs: 3 }),
  ),
  http.get('/api/convert/batch/:batchId', ({ params }) =>
    HttpResponse.json({ batch_id: params.batchId, status: 'running', jobs: [] }),
  ),
  http.post('/api/convert/batch/:batchId/retry-failed', () =>
    HttpResponse.json({ failed_jobs: [] }),
  ),
  http.post('/api/convert/batch/parse-yaml', () =>
    HttpResponse.json({ source_dir: '/tmp', bids_dir: '/tmp/bids', subjects: [] }),
  ),
  http.get('/api/convert/configs', () => HttpResponse.json({ configs: [] })),
  http.get('/api/convert/configs/:filename', ({ params }) =>
    HttpResponse.json({ filename: String(params.filename) }),
  ),
  http.post('/api/convert/configs/save-run', () =>
    HttpResponse.json({ filename: 'x.yaml', name: 'x', kind: 'single' }),
  ),
  http.post('/api/convert/configs/save-batch', () =>
    HttpResponse.json({ filename: 'b.yaml', name: 'b', kind: 'batch' }),
  ),
  http.post('/api/convert/configs/:filename/run', () =>
    HttpResponse.json({ kind: 'single', run_id: 'c1', status: 'started', config: 'x.yaml' }),
  ),
  http.delete('/api/convert/configs/:filename', () =>
    HttpResponse.json({ deleted: true }),
  ),
  http.get('/api/convert/runs', () =>
    HttpResponse.json({ runs: [buildConvertRun()] }),
  ),
  http.get('/api/convert/runs/:runId', ({ params }) =>
    HttpResponse.json(buildConvertRun({ run_id: String(params.runId) })),
  ),
  http.post('/api/convert/runs/:runId/cancel', () =>
    HttpResponse.json({ cancelled: true }),
  ),
  http.delete('/api/convert/runs/:runId', () => HttpResponse.json({ deleted: true })),
]
