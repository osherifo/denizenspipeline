import { http, HttpResponse } from 'msw'

export const fsHandlers = [
  http.post('/api/fs/mkdir', async ({ request }) => {
    const b = (await request.json()) as { parent: string; name: string }
    return HttpResponse.json({ created: true, path: `${b.parent}/${b.name}` })
  }),
  http.get('/api/fs/roots', () => HttpResponse.json({
    roots: [
      { label: 'data', path: '/workspace/data', kind: 'data' },
      { label: 'home', path: '/workspace', kind: 'home' },
    ],
    extra_roots_env: 'FMRIFLOW_BROWSE_ROOTS',
  })),
  http.get('/api/fs/list', ({ request }) => {
    const p = new URL(request.url).searchParams.get('path') ?? ''
    if (p === '/workspace/data') {
      return HttpResponse.json({ path: p, parent: '/workspace', entries: [
        { name: 'dicoms', path: '/workspace/data/dicoms', is_dir: true },
        { name: 'bids', path: '/workspace/data/bids', is_dir: true },
      ], truncated: false })
    }
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
    // Matches the real backend: listing a file 400s (only a directory can be listed).
    if (p === '/workspace/data/dicoms/README.txt') {
      return HttpResponse.json({ detail: `not a directory: ${p}` }, { status: 400 })
    }
    return HttpResponse.json({ detail: 'path is outside the browsable roots' }, { status: 403 })
  }),
  http.get('/api/fs/exists', ({ request }) => {
    const p = new URL(request.url).searchParams.get('path') ?? ''
    const exists = p.startsWith('/workspace/data')
    const is_dir = exists && p !== '/workspace/data/dicoms/README.txt'
    return HttpResponse.json({ path: p, exists, is_dir, resolved: exists ? p : null })
  }),
]
