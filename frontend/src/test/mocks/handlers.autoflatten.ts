import { http, HttpResponse } from 'msw'
import { buildAutoflattenRun } from '../factories'

export const autoflattenHandlers = [
  http.get('/api/autoflatten/doctor', () =>
    HttpResponse.json({ tools: [{ name: 'mris_flatten', available: true, detail: '' }] }),
  ),
  http.post('/api/autoflatten/status', () =>
    HttpResponse.json({
      subject: 'sub-01',
      subject_dir_exists: true,
      has_surfaces: true,
      surfaces: { lh: true, rh: true },
      flat_patches: {},
      has_flat_patches: false,
      pycortex_surface: null,
    }),
  ),
  http.get('/api/autoflatten/runs', () =>
    HttpResponse.json({ runs: [buildAutoflattenRun()] }),
  ),
  http.get('/api/autoflatten/runs/:runId', ({ params }) =>
    HttpResponse.json({
      run_id: String(params.runId),
      subject: 'sub-01',
      status: 'done',
      result: null,
      error: null,
      started_at: 0,
      finished_at: 0,
      events: [],
    }),
  ),
  http.post('/api/autoflatten/runs/:runId/cancel', () =>
    HttpResponse.json({ cancelled: true }),
  ),
  http.delete('/api/autoflatten/runs/:runId', () =>
    HttpResponse.json({ deleted: true }),
  ),
  http.get('/api/autoflatten/configs', () => HttpResponse.json([])),
  http.get('/api/autoflatten/configs/:filename', ({ params }) =>
    HttpResponse.json({
      filename: String(params.filename),
      path: '/tmp/x.yaml',
      config: {},
      yaml_string: '',
    }),
  ),
  http.post('/api/autoflatten/configs/:filename/run', () =>
    HttpResponse.json({ run_id: 'af-cfg', status: 'started', config: 'x.yaml' }),
  ),
  http.put('/api/autoflatten/configs/:filename', () =>
    HttpResponse.json({ saved: true, path: '/tmp/x.yaml', errors: [] }),
  ),
  http.post('/api/autoflatten/configs/:filename/copy', ({ params }) =>
    HttpResponse.json({
      saved: true,
      path: `/tmp/${params.filename}-copy.yaml`,
      filename: `${params.filename}-copy.yaml`,
      errors: [],
    }),
  ),
  http.post('/api/autoflatten/run', () =>
    HttpResponse.json({ run_id: 'af-1', status: 'started' }),
  ),
  http.get('/api/autoflatten/visualizations', () =>
    HttpResponse.json({ images: {} }),
  ),
]
