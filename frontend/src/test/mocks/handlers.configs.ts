import { http, HttpResponse } from 'msw'
import { buildConfigSummary, buildConfigDetail } from '../factories'

export const configsHandlers = [
  http.get('/api/configs', () =>
    HttpResponse.json([
      buildConfigSummary(),
      buildConfigSummary({ filename: 'reading_en/sub-02.yaml', subject: 'sub-02' }),
    ]),
  ),

  http.get('/api/configs/field-values', () =>
    HttpResponse.json({ experiment: ['reading_en'], subject: ['sub-01', 'sub-02'] }),
  ),

  http.get('/api/configs/:filename', ({ params }) =>
    HttpResponse.json(buildConfigDetail({ filename: String(params.filename) })),
  ),

  http.post('/api/configs/:filename/validate', () =>
    HttpResponse.json({ valid: true, errors: [] }),
  ),

  http.put('/api/configs/:filename', () =>
    HttpResponse.json({ saved: true, path: '/tmp/x.yaml', errors: [] }),
  ),

  http.post('/api/configs/:filename/copy', ({ params }) =>
    HttpResponse.json({
      saved: true,
      path: `/tmp/${params.filename}-copy.yaml`,
      filename: `${params.filename}-copy.yaml`,
      errors: [],
    }),
  ),

  http.post('/api/config/validate', () =>
    HttpResponse.json({ valid: true, errors: [] }),
  ),

  http.post('/api/config/from-yaml', async ({ request }) => {
    const yaml = await request.text()
    if (yaml.includes('INVALID')) {
      return HttpResponse.json({ config: {}, errors: ['bad yaml'] })
    }
    return HttpResponse.json({
      config: { experiment: 'reading_en', subject: 'sub-01' },
      errors: [],
    })
  }),

  http.post('/api/config/to-yaml', () =>
    HttpResponse.text('experiment: reading_en\n'),
  ),

  http.post('/api/config/defaults', () =>
    HttpResponse.json({ params: { delay: 0 } }),
  ),
]
