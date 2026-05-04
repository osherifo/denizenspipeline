import { http, HttpResponse } from 'msw'
import { buildRunSummary } from '../factories'

export const runsHandlers = [
  http.get('/api/runs', ({ request }) => {
    const url = new URL(request.url)
    const subject = url.searchParams.get('subject')
    const experiment = url.searchParams.get('experiment')
    const runs = [
      buildRunSummary(),
      buildRunSummary({ subject: 'sub-02', experiment: 'reading_en' }),
    ]
    const filtered = runs.filter(
      (r) =>
        (!subject || r.subject === subject) && (!experiment || r.experiment === experiment),
    )
    return HttpResponse.json(filtered)
  }),

  http.get('/api/runs/in-flight', () => HttpResponse.json({ runs: [] })),

  http.get('/api/runs/in-flight/:runId', ({ params }) =>
    HttpResponse.json({
      run_id: String(params.runId),
      experiment: 'reading_en',
      subject: 'sub-01',
      status: 'running',
      pid: 1,
      started_at: 0,
      finished_at: 0,
      is_reattached: false,
      error: null,
      config_path: null,
      output_dir: null,
      log_path: null,
    }),
  ),

  http.post('/api/runs/in-flight/:runId/cancel', () =>
    HttpResponse.json({ cancelled: true }),
  ),

  http.delete('/api/runs/in-flight/:runId', () =>
    HttpResponse.json({ deleted: true }),
  ),

  http.get('/api/runs/:runId', ({ params }) =>
    HttpResponse.json(buildRunSummary({ run_id: String(params.runId) })),
  ),

  http.post('/api/runs', () =>
    HttpResponse.json({ run_id: 'run-launched', status: 'started' }),
  ),

  http.post('/api/runs/from-config', () =>
    HttpResponse.json({ run_id: 'run-from-config', status: 'started' }),
  ),

  http.delete('/api/runs/:runId/artifacts/:name', () =>
    HttpResponse.json({ deleted: true, path: '/tmp/x' }),
  ),
]
