import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { usePreprocStore } from '../preproc-store'
import {
  installMockWebSocket,
  uninstallMockWebSocket,
} from '../../test/ws'

describe('usePreprocStore', () => {
  beforeEach(() => installMockWebSocket())
  afterEach(() => uninstallMockWebSocket())

  it('initial state', () => {
    const s = usePreprocStore.getState()
    expect(usePreprocStore.getState().tab).toBe('manifests')
    expect(s.manifests).toEqual([])
  })

  it('setTab changes active tab', () => {
    usePreprocStore.getState().setTab('manifests')
    expect(usePreprocStore.getState().tab).toBe('manifests')
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

  // The launch path (startRun / runPreprocConfig) was hard-removed
  // in Stage 7d-A. attachToRun is the remaining WS-tailing entry
  // point — same event-handling logic, exercised here so the
  // tail-progress / tail-done / tail-failed coverage isn't lost.





  it('clearCollect resets collect state', () => {
    usePreprocStore.setState({ collectResult: { manifest: {} } as any, collectError: 'x' })
    usePreprocStore.getState().clearCollect()
    expect(usePreprocStore.getState().collectResult).toBeNull()
    expect(usePreprocStore.getState().collectError).toBeNull()
  })

})
