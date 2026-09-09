import { http, HttpResponse } from 'msw'
import { buildManifestSummary } from '../factories'

export const preprocHandlers = [
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

]
