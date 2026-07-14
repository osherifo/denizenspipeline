/**
 * Experimental AI assistant store.
 *
 * Holds the chat state and drives the `/ws/agent/{session}` WebSocket:
 * sends `{mode, message, context}` frames and appends the streamed
 * `{type: delta|tool|done|error}` events onto the last assistant message
 * (mirroring the append-to-array pattern in preproc-store's attachToRun).
 *
 * Fully self-contained — delete this file + components/agent/ to remove.
 */

import { create } from 'zustand'
import {
  connectAgentWs,
  fetchAgentStatus,
} from '../api/client'
import type { AgentMessage, AgentMode, AgentModeId } from '../api/types'

// Route → default mode. Keeps the assistant context-aware without the
// panel importing every view.
export function modeForHash(hash: string): AgentModeId {
  const h = hash.replace(/^#/, '')
  if (h === 'analysis' || h === 'composer' || h === 'graph') return 'pipeline'
  if (h === 'editor') return 'coding'
  if (h === 'errors') return 'errors'
  return 'generic'
}

interface AgentState {
  ready: boolean
  available: boolean
  enabled: boolean
  hasKey: boolean
  model: string
  modes: AgentMode[]

  open: boolean
  mode: AgentModeId
  messages: AgentMessage[]
  streaming: boolean

  ws: WebSocket | null
  sessionId: string

  loadStatus: () => Promise<void>
  toggleOpen: () => void
  setOpen: (open: boolean) => void
  setMode: (mode: AgentModeId) => void
  clear: () => void
  send: (message: string, context?: Record<string, unknown>) => Promise<void>
}

function newSessionId(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `sess-${Date.now()}-${Math.floor(Math.random() * 1e6)}`
  }
}

export const useAgentStore = create<AgentState>((set, get) => ({
  ready: false,
  available: false,
  enabled: false,
  hasKey: false,
  model: '',
  modes: [],

  open: false,
  mode: 'generic',
  messages: [],
  streaming: false,

  ws: null,
  sessionId: newSessionId(),

  loadStatus: async () => {
    try {
      const s = await fetchAgentStatus()
      set({
        ready: s.ready,
        available: s.available,
        enabled: s.enabled,
        hasKey: s.has_key,
        model: s.model,
        modes: s.modes,
      })
    } catch {
      set({ ready: false })
    }
  },

  toggleOpen: () => set((s) => ({ open: !s.open })),
  setOpen: (open) => set({ open }),
  setMode: (mode) => set({ mode }),

  clear: () => {
    const { ws } = get()
    if (ws) try { ws.close() } catch { /* ignore */ }
    set({ messages: [], streaming: false, ws: null, sessionId: newSessionId() })
  },

  send: async (message, context) => {
    if (get().streaming || !message.trim()) return
    const { mode } = get()

    // Ensure a live socket, wiring the streaming handler once.
    let ws = get().ws
    if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      ws = connectAgentWs(get().sessionId)
      ws.onmessage = (evt: MessageEvent) => {
        let data: { type?: string; text?: string; name?: string; message?: string }
        try { data = JSON.parse(evt.data) } catch { return }
        if (data.type === 'delta') {
          appendToLast(set, (m) => ({ ...m, content: m.content + (data.text ?? '') }))
        } else if (data.type === 'tool') {
          appendToLast(set, (m) => ({ ...m, tools: [...(m.tools ?? []), data.name!] }))
        } else if (data.type === 'error') {
          appendToLast(set, (m) => ({
            ...m,
            content: m.content + `\n\n⚠️ ${data.message ?? 'error'}`,
            streaming: false,
          }))
          set({ streaming: false })
        } else if (data.type === 'done') {
          appendToLast(set, (m) => ({ ...m, streaming: false }))
          set({ streaming: false })
        }
      }
      ws.onclose = () => set({ streaming: false })
      ws.onerror = () => {
        appendToLast(set, (m) => ({ ...m, content: m.content + '\n\n⚠️ connection error', streaming: false }))
        set({ streaming: false })
      }
      set({ ws })
      await waitOpen(ws)
    }

    // Append the user turn + a placeholder assistant turn to stream into.
    set((s) => ({
      streaming: true,
      messages: [
        ...s.messages,
        { role: 'user', content: message },
        { role: 'assistant', content: '', streaming: true },
      ],
    }))

    ws.send(JSON.stringify({ mode, message, context: context ?? null }))
  },
}))

function appendToLast(
  set: (fn: (s: AgentState) => Partial<AgentState>) => void,
  update: (m: AgentMessage) => AgentMessage,
) {
  set((s) => {
    if (!s.messages.length) return {}
    const messages = s.messages.slice()
    const last = messages[messages.length - 1]
    if (last.role !== 'assistant') return {}
    messages[messages.length - 1] = update(last)
    return { messages }
  })
}

function waitOpen(ws: WebSocket): Promise<void> {
  if (ws.readyState === WebSocket.OPEN) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const onOpen = () => { cleanup(); resolve() }
    const onErr = () => { cleanup(); reject(new Error('ws error')) }
    const cleanup = () => {
      ws.removeEventListener('open', onOpen)
      ws.removeEventListener('error', onErr)
    }
    ws.addEventListener('open', onOpen)
    ws.addEventListener('error', onErr)
  })
}
