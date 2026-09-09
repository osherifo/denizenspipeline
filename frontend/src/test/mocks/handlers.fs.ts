import { http, HttpResponse } from 'msw'

export const fsHandlers = [
  http.post('/api/fs/mkdir', async ({ request }) => {
    const b = (await request.json()) as { parent: string; name: string }
    return HttpResponse.json({ created: true, path: `${b.parent}/${b.name}` })
  }),
  http.get('/api/fs/roots', () => HttpResponse.json({
    roots: [
      { label: 'dicoms', path: '/workspace/data/dicoms', kind: 'data' },
      { label: 'bids', path: '/workspace/data/bids', kind: 'data' },
    ],
    extra_roots_env: 'FMRIFLOW_BROWSE_ROOTS',
  })),
  http.get('/api/fs/list', ({ request }) => {
    const p = new URL(request.url).searchParams.get('path') ?? ''
    if (p === '/workspace/data/dicoms') {
      return HttpResponse.json({ path: p, parent: '/workspace/data', entries: [
        { name: 'sub01', path: '/workspace/data/dicoms/sub01', is_dir: true },
        { name: 'README.txt', path: '/workspace/data/dicoms/README.txt', is_dir: false, size: 12 },
      ], truncated: false })
    }
    if (p === '/workspace/data/dicoms/sub01') {
      return HttpResponse.json({ path: p, parent: '/workspace/data/dicoms', entries: [
        { name: 'ses1', path: '/workspace/data/dicoms/sub01/ses1', is_dir: true },
      ], truncated: false })
    }
    return HttpResponse.json({ detail: 'path is outside the browsable roots' }, { status: 403 })
  }),
  http.get('/api/fs/exists', ({ request }) => {
    const p = new URL(request.url).searchParams.get('path') ?? ''
    const exists = p.startsWith('/workspace/data')
    return HttpResponse.json({ path: p, exists, is_dir: exists, resolved: exists ? p : null })
  }),
]
