import { http, HttpResponse } from 'msw'
import { buildConvertRun } from '../factories'

export const convertHandlers = [
  http.get('/api/convert/heuristics', () =>
    HttpResponse.json({
      heuristics: [
        { name: 'reading_heuristic', path: '/tmp/h.py', is_default: true, registered: true,
          description: 'Reads stories', scanner_pattern: null, version: '2.1', tasks: ['story', 'rest'], notes: null },
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
  http.post('/api/convert/heuristics/:name/copy', async ({ params, request }) => {
    const b = (await request.json()) as { new_name: string }
    return HttpResponse.json({ copied: true, source: params.name, name: b.new_name, path: `/tmp/${b.new_name}.py` })
  }),
  http.delete('/api/convert/heuristics/:name', ({ params }) =>
    HttpResponse.json({ deleted: true, name: params.name }),
  ),
  http.get('/api/convert/manifests', () => HttpResponse.json({ manifests: [] })),
  http.post('/api/convert/manifests/rescan', () => HttpResponse.json({ manifests: [] })),
  http.delete('/api/convert/manifests/:subject', ({ params }) =>
    HttpResponse.json({ deleted: true, subject: params.subject, path: `/tmp/bids/convert_manifest.json` }),
  ),
  http.get('/api/convert/manifests/:subject', ({ params }) =>
    HttpResponse.json({ subject: params.subject, sessions: [], runs: [] }),
  ),
  http.post('/api/convert/manifests/:subject/validate', () =>
    HttpResponse.json({ errors: [] }),
  ),
  http.post('/api/convert/scan', () =>
    HttpResponse.json({
      scan_id: 'scan_1', source_dir: '/tmp/dicom', status: 'running', started_at: 0, finished_at: null,
      progress: { files_seen: 0, dicoms_seen: 0, series_found: 0, current_dir: '' }, result: null, error: null,
    }),
  ),
  http.get('/api/convert/scan/:id', () =>
    HttpResponse.json({
      scan_id: 'scan_1', source_dir: '/tmp/dicom', status: 'done', started_at: 0, finished_at: 1,
      progress: { files_seen: 10, dicoms_seen: 10, series_found: 1, current_dir: '/tmp/dicom' },
      result: {
        scanner: null,
        series: [{ number: 1, description: 'T1w', n_images: 10, modality: 'MR', image_type: 'ORIGINAL\\PRIMARY\\M\\ND', manufacturer: 'Siemens', model: 'Prisma', field_strength: 3, station_name: 'MR1', study_date: '20260101' }],
        matching_heuristic: null,
      },
      error: null,
    }),
  ),
  http.post('/api/convert/scan/:id/cancel', () => HttpResponse.json({ cancelled: true })),
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
