import { http, HttpResponse } from 'msw'
import { buildManifestSummary, buildPreprocRun } from '../factories'

export const preprocHandlers = [
  http.get('/api/preproc/backends', () =>
    HttpResponse.json({
      backends: [
        { name: 'fmriprep', available: true, detail: '24.0.0' },
        { name: 'mock', available: true, detail: 'stub' },
      ],
    }),
  ),

  http.get('/api/preproc/manifests', () =>
    HttpResponse.json({ manifests: [buildManifestSummary()] }),
  ),

  http.post('/api/preproc/manifests/rescan', () =>
    HttpResponse.json({ manifests: [buildManifestSummary()] }),
  ),

  http.get('/api/preproc/manifests/:subject', ({ params }) =>
    HttpResponse.json({
      subject: params.subject,
      dataset: 'reading_en',
      sessions: ['ses-01'],
      runs: [],
      backend: 'fmriprep',
      backend_version: '24.0.0',
      parameters: {},
      space: 'MNI152NLin2009cAsym',
      resolution: null,
      confounds_applied: [],
      additional_steps: [],
      output_dir: '/tmp',
      output_format: 'nifti',
      file_pattern: '*.nii.gz',
      created: '2026-05-04',
      pipeline_version: null,
      checksum: null,
      manifest_version: 1,
    }),
  ),

  http.post('/api/preproc/manifests/:subject/validate', () =>
    HttpResponse.json({ errors: [] }),
  ),

  http.post('/api/preproc/collect', () =>
    HttpResponse.json({ manifest: {}, manifest_path: '/tmp/m.json' }),
  ),

  http.post('/api/preproc/run', () =>
    HttpResponse.json({ run_id: 'preproc-1', status: 'started' }),
  ),

  http.post('/api/preproc/validate-config', () =>
    HttpResponse.json({ valid: true, errors: [] }),
  ),

  http.get('/api/preproc/configs', () => HttpResponse.json([])),
  http.get('/api/preproc/configs/:filename', ({ params }) =>
    HttpResponse.json({
      filename: String(params.filename),
      path: '/tmp/x.yaml',
      config: {},
      yaml_string: '',
    }),
  ),
  http.post('/api/preproc/configs/:filename/run', () =>
    HttpResponse.json({ run_id: 'preproc-cfg', status: 'started', config: 'x.yaml' }),
  ),
  http.get('/api/preproc/runs', () => HttpResponse.json({ runs: [buildPreprocRun()] })),
  http.get('/api/preproc/runs/:runId', ({ params }) =>
    HttpResponse.json(buildPreprocRun({ run_id: String(params.runId) })),
  ),
  http.post('/api/preproc/runs/:runId/cancel', () =>
    HttpResponse.json({ cancelled: true }),
  ),
  http.delete('/api/preproc/runs/:runId', () => HttpResponse.json({ deleted: true })),
]
