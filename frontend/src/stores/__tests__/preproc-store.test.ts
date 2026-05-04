import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { usePreprocStore } from '../preproc-store'
import {
  installMockWebSocket,
  uninstallMockWebSocket,
  mockWsServer,
} from '../../test/ws'

describe('usePreprocStore', () => {
  beforeEach(() => installMockWebSocket())
  afterEach(() => uninstallMockWebSocket())

  it('initial state', () => {
    const s = usePreprocStore.getState()
    expect(s.tab).toBe('backends')
    expect(s.backends).toEqual([])
    expect(s.manifests).toEqual([])
    expect(s.runId).toBeNull()
  })

  it('setTab changes active tab', () => {
    usePreprocStore.getState().setTab('manifests')
    expect(usePreprocStore.getState().tab).toBe('manifests')
  })

  it('loadBackends populates list', async () => {
    await usePreprocStore.getState().loadBackends()
    expect(usePreprocStore.getState().backends.length).toBe(2)
    expect(usePreprocStore.getState().backendsLoading).toBe(false)
  })

  it('loadManifests populates list', async () => {
    await usePreprocStore.getState().loadManifests()
    expect(usePreprocStore.getState().manifests.length).toBe(1)
  })

  it('rescan refetches manifests', async () => {
    await usePreprocStore.getState().rescan()
    expect(usePreprocStore.getState().manifests.length).toBe(1)
  })

  it('selectManifest fetches detail', async () => {
    await usePreprocStore.getState().selectManifest('sub-01')
    expect(usePreprocStore.getState().selectedManifest?.subject).toBe('sub-01')
  })

  it('validateSelected requires a selected subject', async () => {
    await usePreprocStore.getState().validateSelected()
    expect(usePreprocStore.getState().validationErrors).toBeNull()
  })

  it('validateSelected returns errors for selected subject', async () => {
    server.use(
      http.post('/api/preproc/manifests/:subject/validate', () =>
        HttpResponse.json({ errors: ['no manifest'] }),
      ),
    )
    await usePreprocStore.getState().selectManifest('sub-01')
    await usePreprocStore.getState().validateSelected()
    expect(usePreprocStore.getState().validationErrors).toEqual(['no manifest'])
  })

  it('collect populates result', async () => {
    await usePreprocStore.getState().collect({
      backend: 'mock',
      output_dir: '/tmp',
      subject: 'sub-01',
    })
    expect(usePreprocStore.getState().collectResult).not.toBeNull()
    expect(usePreprocStore.getState().collecting).toBe(false)
  })

  it('startRun sets runId and tracks events via WS', async () => {
    const conn = mockWsServer('ws://localhost:5173/ws/preproc/preproc-1')
    await usePreprocStore.getState().startRun({
      backend: 'mock',
      output_dir: '/tmp',
      subject: 'sub-01',
    })
    await new Promise((r) => setTimeout(r, 10))
    conn.send({ event: 'progress', message: 'half' })
    await new Promise((r) => setTimeout(r, 10))
    expect(usePreprocStore.getState().runEvents).toHaveLength(1)
    expect(usePreprocStore.getState().runId).toBe('preproc-1')
  })

  it('startRun handles done event', async () => {
    const conn = mockWsServer('ws://localhost:5173/ws/preproc/preproc-1')
    await usePreprocStore.getState().startRun({
      backend: 'mock',
      output_dir: '/tmp',
      subject: 'sub-01',
    })
    await new Promise((r) => setTimeout(r, 10))
    conn.send({ event: 'done' })
    await new Promise((r) => setTimeout(r, 10))
    expect(usePreprocStore.getState().running).toBe(false)
  })

  it('startRun handles failed event with error', async () => {
    const conn = mockWsServer('ws://localhost:5173/ws/preproc/preproc-1')
    await usePreprocStore.getState().startRun({
      backend: 'mock',
      output_dir: '/tmp',
      subject: 'sub-01',
    })
    await new Promise((r) => setTimeout(r, 10))
    conn.send({ event: 'failed', error: 'oom' })
    await new Promise((r) => setTimeout(r, 10))
    expect(usePreprocStore.getState().runError).toBe('oom')
  })

  it('clearRun resets run state', () => {
    usePreprocStore.setState({ runId: 'x', runEvents: [{ event: 'progress' }], running: true })
    usePreprocStore.getState().clearRun()
    expect(usePreprocStore.getState().runId).toBeNull()
    expect(usePreprocStore.getState().runEvents).toEqual([])
    expect(usePreprocStore.getState().running).toBe(false)
  })

  it('clearCollect resets collect state', () => {
    usePreprocStore.setState({ collectResult: { manifest: {} } as any, collectError: 'x' })
    usePreprocStore.getState().clearCollect()
    expect(usePreprocStore.getState().collectResult).toBeNull()
    expect(usePreprocStore.getState().collectError).toBeNull()
  })

  it('loadPreprocRuns populates run list', async () => {
    await usePreprocStore.getState().loadPreprocRuns()
    expect(usePreprocStore.getState().preprocRuns.length).toBe(1)
  })
})
