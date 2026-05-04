import { Server, WebSocket as MockWebSocket } from 'mock-socket'
import { vi } from 'vitest'
import type { RunEvent } from '../api/types'

interface Connection {
  url: string
  server: Server
  client?: MockWebSocket
  send: (data: unknown) => void
  close: () => void
}

const servers: Server[] = []

let originalWebSocket: typeof WebSocket | undefined

export function installMockWebSocket() {
  if (originalWebSocket === undefined) {
    originalWebSocket = (globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket
  }
  Object.defineProperty(globalThis, 'WebSocket', {
    configurable: true,
    writable: true,
    value: MockWebSocket,
  })
}

export function uninstallMockWebSocket() {
  servers.forEach((s) => s.stop())
  servers.length = 0
  if (originalWebSocket !== undefined) {
    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: true,
      writable: true,
      value: originalWebSocket,
    })
  }
}

export function mockWsServer(url: string): Connection {
  installMockWebSocket()
  const server = new Server(url)
  servers.push(server)

  let activeSocket: MockWebSocket | null = null
  server.on('connection', (socket) => {
    activeSocket = socket as unknown as MockWebSocket
  })

  return {
    url,
    server,
    get client() {
      return activeSocket ?? undefined
    },
    send: (data: unknown) => {
      const payload = typeof data === 'string' ? data : JSON.stringify(data)
      server.emit('message', payload)
    },
    close: () => {
      server.stop()
    },
  }
}

export function runEventStream(): RunEvent[] {
  return [
    { event: 'run_start', timestamp: 1 },
    { event: 'stage_start', stage: 'stimuli' },
    { event: 'stage_done', stage: 'stimuli', elapsed: 1, detail: 'ok' },
    { event: 'stage_start', stage: 'responses' },
    { event: 'stage_done', stage: 'responses', elapsed: 1, detail: 'ok' },
    { event: 'stage_start', stage: 'features' },
    { event: 'stage_done', stage: 'features', elapsed: 2, detail: 'ok' },
    { event: 'stage_start', stage: 'prepare' },
    { event: 'stage_done', stage: 'prepare', elapsed: 1, detail: 'ok' },
    { event: 'stage_start', stage: 'model' },
    { event: 'stage_done', stage: 'model', elapsed: 5, detail: 'ok' },
    { event: 'stage_start', stage: 'analyze' },
    { event: 'stage_done', stage: 'analyze', elapsed: 3, detail: 'ok' },
    { event: 'stage_start', stage: 'report' },
    { event: 'stage_done', stage: 'report', elapsed: 1, detail: 'ok' },
    { event: 'run_done' },
  ]
}

export function runFailureStream(): RunEvent[] {
  return [
    { event: 'run_start' },
    { event: 'stage_start', stage: 'stimuli' },
    { event: 'stage_done', stage: 'stimuli', elapsed: 1, detail: 'ok' },
    { event: 'stage_start', stage: 'features' },
    { event: 'stage_fail', stage: 'features', elapsed: 1, error: 'boom' },
    { event: 'run_failed', error: 'boom' },
  ]
}

export function playEventStream(conn: Connection, events: RunEvent[], stepMs = 0) {
  if (stepMs <= 0) {
    for (const e of events) conn.send(e)
    return
  }
  let i = 0
  const id = setInterval(() => {
    if (i >= events.length) {
      clearInterval(id)
      return
    }
    conn.send(events[i++])
  }, stepMs)
}

vi.stubGlobal('flushMicrotasks', async () => {
  await new Promise((r) => setTimeout(r, 0))
})
