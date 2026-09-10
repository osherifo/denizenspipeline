import { afterEach, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { usePreprocRunsStore } from '../preproc-runs-store'
import { mockWsServer, uninstallMockWebSocket } from '../../test/ws'
import { server } from '../../test/mocks/server'
import { buildRunDetail } from '../../test/mocks/handlers.preproc-pipelines'

afterEach(() => uninstallMockWebSocket())

const flush = () => new Promise((r) => setTimeout(r, 30))

describe('preproc runs store', () => {
  it('lists runs and selects one, opening the event socket', async () => {
    const conn = mockWsServer('ws://localhost:5173/ws/preproc/pp_abc')
    const s = usePreprocRunsStore.getState()
    await s.loadRuns()
    expect(usePreprocRunsStore.getState().runs[0].run_id).toBe('pp_abc')

    await s.select('pp_abc')
    await flush()
    const st = usePreprocRunsStore.getState()
    expect(st.detail?.run_id).toBe('pp_abc')
    expect(st.detail?.job?.pipeline.nodes).toHaveLength(2)
    expect(st.socket).not.toBeNull()

    conn.send({ event: 'started', n_nodes: 2, timestamp: 1 })
    conn.send({ event: 'node_start', node: 'derivatives_smooth__sub_01.source', leaf: 'source', t: 2 })
    conn.send({ event: 'node_done', node: 'derivatives_smooth__sub_01.source', leaf: 'source', t: 3, cached: false, duration_s: 1 })
    await flush()
    const events = usePreprocRunsStore.getState().events
    expect(events.map((e) => e.event)).toEqual(['started', 'node_start', 'node_done'])

    conn.send({ event: '_close', status: 'done' })
    await flush()
    usePreprocRunsStore.getState().disconnect()
    expect(usePreprocRunsStore.getState().socket).toBeNull()
  })

  it('a stale select() cannot overwrite a newer selection\'s detail or socket', async () => {
    // pp_slow's detail fetch hangs until we resolve it by hand; pp_fast resolves
    // immediately, the way a real second click would race ahead of a slow first one.
    let releaseSlow!: () => void
    const slow = new Promise<void>((resolve) => { releaseSlow = resolve })
    server.use(
      http.get('/api/preproc/runs/pp_slow', async () => {
        await slow
        return HttpResponse.json(buildRunDetail({ run_id: 'pp_slow' }))
      }),
    )
    mockWsServer('ws://localhost:5173/ws/preproc/pp_slow')
    const connFast = mockWsServer('ws://localhost:5173/ws/preproc/pp_fast')

    const s = usePreprocRunsStore.getState()
    const slowSelect = s.select('pp_slow')   // not awaited: still in flight
    await s.select('pp_fast')                // races ahead and finishes first
    const afterFast = usePreprocRunsStore.getState()
    expect(afterFast.selectedRunId).toBe('pp_fast')
    expect(afterFast.detail?.run_id).toBe('pp_fast')
    const fastSocket = afterFast.socket
    expect(fastSocket).not.toBeNull()
    await new Promise((r) => setTimeout(r, 30))   // let mock-socket finish its handshake
    expect(connFast.client).toBeDefined()

    // Now let the stale pp_slow request resolve; it must not clobber pp_fast's
    // detail, nor replace pp_fast's socket with one of its own.
    releaseSlow()
    await new Promise((r) => setTimeout(r, 30))
    await slowSelect
    const after = usePreprocRunsStore.getState()
    expect(after.selectedRunId).toBe('pp_fast')
    expect(after.detail?.run_id).toBe('pp_fast')
    expect(after.socket).toBe(fastSocket)

    usePreprocRunsStore.getState().disconnect()
  })

  it('disconnect() invalidates a select() already in flight — no orphaned socket', async () => {
    // Models a modal unmounting (disconnect() in its cleanup) while its own
    // select() from mount is still awaiting the run detail fetch.
    let release!: () => void
    const pending = new Promise<void>((resolve) => { release = resolve })
    server.use(
      http.get('/api/preproc/runs/pp_abc', async () => {
        await pending
        return HttpResponse.json(buildRunDetail({ run_id: 'pp_abc' }))
      }),
    )
    mockWsServer('ws://localhost:5173/ws/preproc/pp_abc')

    const s = usePreprocRunsStore.getState()
    const selecting = s.select('pp_abc')
    usePreprocRunsStore.getState().disconnect()   // fires before the fetch resolves
    release()
    await new Promise((r) => setTimeout(r, 30))
    await selecting

    // The superseded select() must not have opened (and left untracked) a socket.
    expect(usePreprocRunsStore.getState().socket).toBeNull()
  })

  it('resume and restart select the new run', async () => {
    mockWsServer('ws://localhost:5173/ws/preproc/pp_abc')
    mockWsServer('ws://localhost:5173/ws/preproc/pp_resumed')
    mockWsServer('ws://localhost:5173/ws/preproc/pp_restarted')
    const s = usePreprocRunsStore.getState()
    await s.select('pp_abc')
    expect(await usePreprocRunsStore.getState().resume('pp_abc')).toBe('pp_resumed')
    expect(usePreprocRunsStore.getState().selectedRunId).toBe('pp_resumed')
    expect(await usePreprocRunsStore.getState().restart('pp_abc')).toBe('pp_restarted')
    expect(usePreprocRunsStore.getState().selectedRunId).toBe('pp_restarted')
    usePreprocRunsStore.getState().disconnect()
  })
})
