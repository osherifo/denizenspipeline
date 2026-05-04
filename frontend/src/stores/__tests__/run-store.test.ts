import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { useRunStore } from '../run-store'
import {
  installMockWebSocket,
  uninstallMockWebSocket,
  mockWsServer,
  runEventStream,
  runFailureStream,
  playEventStream,
} from '../../test/ws'
import { buildPipelineConfig } from '../../test/factories'

const WS_URL = 'ws://localhost:5173/ws/runs/run-launched'

describe('useRunStore', () => {
  beforeEach(() => installMockWebSocket())
  afterEach(() => uninstallMockWebSocket())

  it('initial state is empty', () => {
    const s = useRunStore.getState()
    expect(s.runs).toEqual([])
    expect(s.selectedRun).toBeNull()
    expect(s.liveRunId).toBeNull()
    expect(s.liveEvents).toEqual([])
    expect(s.compareIds).toEqual([])
  })

  it('loadRuns fetches and stores runs', async () => {
    await useRunStore.getState().loadRuns()
    const s = useRunStore.getState()
    expect(s.runs.length).toBe(2)
    expect(s.loading).toBe(false)
  })

  it('loadRuns passes filters to API', async () => {
    let received: URL | null = null
    server.use(
      http.get('/api/runs', ({ request }) => {
        received = new URL(request.url)
        return HttpResponse.json([])
      }),
    )
    await useRunStore.getState().loadRuns({ experiment: 'reading_en', subject: 'sub-01' })
    expect(received!.searchParams.get('experiment')).toBe('reading_en')
    expect(received!.searchParams.get('subject')).toBe('sub-01')
  })

  it('loadRuns sets error on failure', async () => {
    server.use(http.get('/api/runs', () => HttpResponse.text('x', { status: 500 })))
    await useRunStore.getState().loadRuns()
    expect(useRunStore.getState().error).toMatch(/500/)
  })

  it('selectRun fetches single run and sets selectedRun', async () => {
    await useRunStore.getState().selectRun('run-1')
    expect(useRunStore.getState().selectedRun?.run_id).toBe('run-1')
  })

  it('clearSelection clears selectedRun', async () => {
    await useRunStore.getState().selectRun('run-1')
    useRunStore.getState().clearSelection()
    expect(useRunStore.getState().selectedRun).toBeNull()
  })

  it('launchRun starts run + sets liveRunId', async () => {
    mockWsServer(WS_URL)
    const id = await useRunStore.getState().launchRun(buildPipelineConfig())
    expect(id).toBe('run-launched')
    expect(useRunStore.getState().liveRunId).toBe('run-launched')
  })

  it('subscribeLive appends incoming events to liveEvents', async () => {
    const conn = mockWsServer(WS_URL)
    await useRunStore.getState().launchRun(buildPipelineConfig())
    await new Promise((r) => setTimeout(r, 10))
    playEventStream(conn, [{ event: 'stage_start', stage: 'features' }])
    await new Promise((r) => setTimeout(r, 10))
    expect(useRunStore.getState().liveEvents).toHaveLength(1)
    expect(useRunStore.getState().liveEvents[0].stage).toBe('features')
  })

  it('subscribeLive auto-closes on run_done and refreshes runs', async () => {
    const conn = mockWsServer(WS_URL)
    await useRunStore.getState().launchRun(buildPipelineConfig())
    await new Promise((r) => setTimeout(r, 10))
    playEventStream(conn, runEventStream())
    await new Promise((r) => setTimeout(r, 30))
    const s = useRunStore.getState()
    expect(s.liveRunId).toBeNull()
    expect(s.runs.length).toBeGreaterThan(0)
  })

  it('subscribeLive auto-closes on run_failed', async () => {
    const conn = mockWsServer(WS_URL)
    await useRunStore.getState().launchRun(buildPipelineConfig())
    await new Promise((r) => setTimeout(r, 10))
    playEventStream(conn, runFailureStream())
    await new Promise((r) => setTimeout(r, 30))
    expect(useRunStore.getState().liveRunId).toBeNull()
  })

  describe('comparison', () => {
    it('toggleCompare adds id when not present', () => {
      useRunStore.getState().toggleCompare('a')
      expect(useRunStore.getState().compareIds).toEqual(['a'])
    })

    it('toggleCompare removes id when present', () => {
      useRunStore.getState().toggleCompare('a')
      useRunStore.getState().toggleCompare('a')
      expect(useRunStore.getState().compareIds).toEqual([])
    })

    it('clearCompare resets ids and selection', () => {
      useRunStore.getState().toggleCompare('a')
      useRunStore.getState().toggleCompare('b')
      useRunStore.getState().clearCompare()
      expect(useRunStore.getState().compareIds).toEqual([])
      expect(useRunStore.getState().compareSelection).toBeNull()
    })

    it('openComparison no-ops with fewer than 2 ids', async () => {
      useRunStore.getState().toggleCompare('a')
      await useRunStore.getState().openComparison()
      expect(useRunStore.getState().compareSelection).toBeNull()
    })

    it('openComparison fetches all selected runs', async () => {
      useRunStore.getState().toggleCompare('a')
      useRunStore.getState().toggleCompare('b')
      await useRunStore.getState().openComparison()
      expect(useRunStore.getState().compareSelection).toHaveLength(2)
    })

    it('closeComparison clears compareSelection', async () => {
      useRunStore.getState().toggleCompare('a')
      useRunStore.getState().toggleCompare('b')
      await useRunStore.getState().openComparison()
      useRunStore.getState().closeComparison()
      expect(useRunStore.getState().compareSelection).toBeNull()
    })
  })
})
