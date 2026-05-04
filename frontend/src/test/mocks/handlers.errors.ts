import { http, HttpResponse } from 'msw'

export const errorsHandlers = [
  http.get('/api/errors', () =>
    HttpResponse.json({
      errors: [
        {
          id: '0001',
          title: 'Mock error',
          stage: 'features',
          tags: ['mock'],
          root_cause: 'mocked',
          fix: 'fix it',
          references: [],
        },
      ],
      total: 1,
    }),
  ),
  http.get('/api/triage/:runId', ({ params }) => {
    if (params.runId === 'missing') return new HttpResponse(null, { status: 404 })
    return HttpResponse.json({ run_id: params.runId, captured_at: 0, errors: [] })
  }),
  http.post('/api/triage/:runId/rescan', ({ params }) =>
    HttpResponse.json({ run_id: params.runId, captured_at: 0, errors: [] }),
  ),
  http.post('/api/errors/from-capture', () =>
    HttpResponse.json({ saved: true, slug: 'new-error', path: '/tmp/e.yaml' }),
  ),
]
