import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { useDashboardStore } from '../dashboard-store'
import {
  installMockWebSocket,
  uninstallMockWebSocket,
  mockWsServer,
  runEventStream,
  playEventStream,
} from '../../test/ws'

describe('useDashboardStore', () => {
  beforeEach(() => installMockWebSocket())
  afterEach(() => uninstallMockWebSocket())

  it('initial state', () => {
    const s = useDashboardStore.getState()
    expect(s.configs).toEqual([])
    expect(s.selectedConfig).toBeNull()
    expect(s.liveRunId).toBeNull()
  })

  it('loadConfigs fetches and stores configs', async () => {
    await useDashboardStore.getState().loadConfigs()
    expect(useDashboardStore.getState().configs.length).toBe(2)
  })

  it('loadConfigs sets error on failure', async () => {
    server.use(http.get('/api/configs', () => HttpResponse.text('x', { status: 500 })))
    await useDashboardStore.getState().loadConfigs()
    expect(useDashboardStore.getState().configsError).toMatch(/500/)
  })

  it('selectConfig fetches detail and triggers run history load', async () => {
    await useDashboardStore.getState().selectConfig('reading_en/sub-01.yaml')
    await new Promise((r) => setTimeout(r, 0))
    const s = useDashboardStore.getState()
    expect(s.selectedConfig?.filename).toBe('reading_en/sub-01.yaml')
    expect(s.selectedFilename).toBe('reading_en/sub-01.yaml')
  })

  it('clearSelection resets all selection state', async () => {
    await useDashboardStore.getState().selectConfig('reading_en/sub-01.yaml')
    useDashboardStore.getState().clearSelection()
    const s = useDashboardStore.getState()
    expect(s.selectedConfig).toBeNull()
    expect(s.selectedFilename).toBeNull()
    expect(s.selectedRun).toBeNull()
  })

  it('selectRun sets selectedRun', async () => {
    await useDashboardStore.getState().selectRun('run-1')
    expect(useDashboardStore.getState().selectedRun?.run_id).toBe('run-1')
  })

  it('validateConfig stores returned errors', async () => {
    await useDashboardStore.getState().validateConfig('reading_en/sub-01.yaml')
    expect(useDashboardStore.getState().validationErrors).toEqual([])
    expect(useDashboardStore.getState().validating).toBe(false)
  })

  it('validateConfig captures fetch errors as a single-element list', async () => {
    server.use(
      http.post('/api/configs/:filename/validate', () =>
        HttpResponse.text('x', { status: 500 }),
      ),
    )
    await useDashboardStore.getState().validateConfig('reading_en/sub-01.yaml')
    expect(useDashboardStore.getState().validationErrors?.length).toBe(1)
  })

  it('rescan refreshes configs', async () => {
    await useDashboardStore.getState().rescan()
    expect(useDashboardStore.getState().configs.length).toBe(2)
  })

  it('runConfig launches run and tracks live progress', async () => {
    const conn = mockWsServer('ws://localhost:5173/ws/runs/run-from-config')
    await useDashboardStore.getState().runConfig('reading_en/sub-01.yaml')
    await new Promise((r) => setTimeout(r, 10))
    expect(useDashboardStore.getState().liveRunId).toBe('run-from-config')

    playEventStream(conn, [{ event: 'stage_start', stage: 'features' }])
    await new Promise((r) => setTimeout(r, 10))
    expect(useDashboardStore.getState().stageStatuses.features.status).toBe('running')
  })

  it('runConfig clears liveRunId on run_done', async () => {
    const conn = mockWsServer('ws://localhost:5173/ws/runs/run-from-config')
    await useDashboardStore.getState().runConfig('reading_en/sub-01.yaml')
    await new Promise((r) => setTimeout(r, 10))
    playEventStream(conn, runEventStream())
    await new Promise((r) => setTimeout(r, 30))
    expect(useDashboardStore.getState().liveRunId).toBeNull()
    expect(useDashboardStore.getState().stageStatuses.features.status).toBe('done')
  })

  it('deriveStageStatuses (via runConfig) marks failed stage', async () => {
    const conn = mockWsServer('ws://localhost:5173/ws/runs/run-from-config')
    await useDashboardStore.getState().runConfig('reading_en/sub-01.yaml')
    await new Promise((r) => setTimeout(r, 10))
    playEventStream(conn, [
      { event: 'stage_start', stage: 'model' },
      { event: 'stage_fail', stage: 'model', error: 'NaN' },
    ])
    await new Promise((r) => setTimeout(r, 10))
    expect(useDashboardStore.getState().stageStatuses.model.status).toBe('failed')
    expect(useDashboardStore.getState().stageStatuses.model.detail).toBe('NaN')
  })

  it('deriveStageStatuses marks warning', async () => {
    const conn = mockWsServer('ws://localhost:5173/ws/runs/run-from-config')
    await useDashboardStore.getState().runConfig('reading_en/sub-01.yaml')
    await new Promise((r) => setTimeout(r, 10))
    playEventStream(conn, [
      { event: 'stage_warn', stage: 'analyze', detail: 'low SNR' },
    ])
    await new Promise((r) => setTimeout(r, 10))
    expect(useDashboardStore.getState().stageStatuses.analyze.status).toBe('warning')
  })
})
