import { afterEach, describe, expect, it } from 'vitest'
import { usePreprocRunsStore } from '../preproc-runs-store'
import { mockWsServer, uninstallMockWebSocket } from '../../test/ws'

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
