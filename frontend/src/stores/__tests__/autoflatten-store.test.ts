import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useAutoflattenStore } from '../autoflatten-store'
import {
  installMockWebSocket,
  uninstallMockWebSocket,
  mockWsServer,
} from '../../test/ws'

describe('useAutoflattenStore', () => {
  beforeEach(() => installMockWebSocket())
  afterEach(() => uninstallMockWebSocket())

  it('initial state', () => {
    const s = useAutoflattenStore.getState()
    expect(s.tab).toBe('status')
    expect(s.tools).toEqual([])
    expect(s.runId).toBeNull()
  })

  it('setTab changes tab', () => {
    useAutoflattenStore.getState().setTab('run')
    expect(useAutoflattenStore.getState().tab).toBe('run')
  })

  it('loadTools populates tool list', async () => {
    await useAutoflattenStore.getState().loadTools()
    expect(useAutoflattenStore.getState().tools.length).toBeGreaterThan(0)
  })

  it('checkStatus populates subjectStatus', async () => {
    await useAutoflattenStore.getState().checkStatus('/tmp/subjects', 'sub-01')
    expect(useAutoflattenStore.getState().subjectStatus?.subject).toBe('sub-01')
  })

  it('startRun sets runId', async () => {
    mockWsServer('ws://localhost:5173/ws/autoflatten/af-1')
    await useAutoflattenStore.getState().startRun({
      subjects_dir: '/tmp',
      subject: 'sub-01',
    })
    await new Promise((r) => setTimeout(r, 10))
    expect(useAutoflattenStore.getState().runId).toBe('af-1')
  })

  it('clearRun resets state', () => {
    useAutoflattenStore.setState({ runId: 'x', running: true, runError: 'e' })
    useAutoflattenStore.getState().clearRun()
    const s = useAutoflattenStore.getState()
    expect(s.runId).toBeNull()
    expect(s.running).toBe(false)
    expect(s.runError).toBeNull()
  })

  it('clearStatus resets status', () => {
    useAutoflattenStore.setState({
      subjectStatus: { subject: 'x' } as any,
      statusError: 'e',
    })
    useAutoflattenStore.getState().clearStatus()
    expect(useAutoflattenStore.getState().subjectStatus).toBeNull()
    expect(useAutoflattenStore.getState().statusError).toBeNull()
  })
})
