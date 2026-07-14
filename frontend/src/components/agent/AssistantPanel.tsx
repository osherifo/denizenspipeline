/**
 * Experimental AI assistant — global floating panel.
 *
 * Mounted once (in main.tsx). Renders nothing unless the assistant is
 * enabled + keyed + installed. A launcher button floats bottom-right;
 * clicking it opens a chat drawer whose mode auto-follows the current
 * route. Advisory only — it never mutates app state.
 *
 * Self-contained: delete this folder + stores/agent-store.ts and remove
 * the <AssistantPanel/> mount to fully remove the feature.
 */

import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useAgentStore, modeForHash } from '../../stores/agent-store'
import { useConfigStore } from '../../stores/config-store'
import { useEditorStore } from '../../stores/editor-store'
import type { AgentModeId } from '../../api/types'

// Gather the opening context for the active mode from the relevant store.
// Read-only getState() calls — no subscription, no coupling on removal.
function contextFor(mode: AgentModeId): Record<string, unknown> | undefined {
  if (mode === 'pipeline') {
    const s = useConfigStore.getState()
    return { yaml: s.yamlString, validationErrors: s.validationErrors }
  }
  if (mode === 'coding') {
    const s = useEditorStore.getState()
    return { code: s.code, category: s.currentCategory, validation: s.validation }
  }
  return undefined
}

const ACCENT = 'var(--accent-cyan)'

export function AssistantPanel() {
  const {
    ready, open, mode, messages, streaming, model, modes,
    loadStatus, toggleOpen, setMode, send, clear,
  } = useAgentStore()
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => { loadStatus() }, [loadStatus])

  // Follow the route to pick the default mode (only while closed, so we
  // don't yank the mode out from under an in-progress conversation).
  useEffect(() => {
    const sync = () => { if (!useAgentStore.getState().open) setMode(modeForHash(window.location.hash)) }
    sync()
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [setMode])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  if (!ready) return null

  const submit = () => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    void send(text, contextFor(mode))
  }

  if (!open) {
    return (
      <button onClick={toggleOpen} style={launcherStyle} title="AI assistant (experimental)">
        ✦ Ask AI
      </button>
    )
  }

  const currentLabel = modes.find((m) => m.id === mode)?.label ?? mode

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <span style={{ fontWeight: 600, color: ACCENT }}>✦ Assistant</span>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as AgentModeId)}
          style={selectStyle}
          title="Assistant mode"
        >
          {modes.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
        <span style={{ flex: 1 }} />
        <button onClick={clear} style={iconBtnStyle} title="New conversation">⟲</button>
        <button onClick={toggleOpen} style={iconBtnStyle} title="Close">✕</button>
      </div>

      <div ref={scrollRef} style={scrollStyle}>
        {messages.length === 0 && (
          <div style={hintStyle}>
            <b>{currentLabel}</b> — experimental. Advisory only; I read your configs, modules,
            runs, and error KB but never change anything. Model: <code>{model}</code>.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={m.role === 'user' ? userRowStyle : asstRowStyle}>
            {m.tools && m.tools.length > 0 && (
              <div style={toolsStyle}>🔧 {m.tools.join(', ')}</div>
            )}
            <div style={m.role === 'user' ? userBubbleStyle : asstBubbleStyle}>
              {m.content || (m.streaming ? '…' : '')}
              {m.streaming && <span style={caretStyle}>▊</span>}
            </div>
          </div>
        ))}
      </div>

      <div style={composerStyle}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
          }}
          placeholder={`Ask about ${currentLabel.toLowerCase()}…  (Enter to send)`}
          rows={2}
          style={textareaStyle}
        />
        <button onClick={submit} disabled={streaming || !input.trim()} style={sendBtnStyle}>
          {streaming ? '…' : 'Send'}
        </button>
      </div>
    </div>
  )
}

// ── styles (inline CSSProperties + theme vars, per project convention) ──

const launcherStyle: CSSProperties = {
  position: 'fixed', right: 20, bottom: 20, zIndex: 9000,
  background: 'var(--bg-card)', color: ACCENT, border: `1px solid ${ACCENT}`,
  borderRadius: 20, padding: '8px 16px', cursor: 'pointer', fontSize: 13,
  boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
}

const panelStyle: CSSProperties = {
  position: 'fixed', right: 20, bottom: 20, zIndex: 9000,
  width: 400, maxWidth: 'calc(100vw - 40px)', height: 560, maxHeight: 'calc(100vh - 40px)',
  display: 'flex', flexDirection: 'column',
  background: 'var(--bg-secondary)', border: '1px solid var(--border)',
  borderRadius: 10, boxShadow: '0 8px 32px rgba(0,0,0,0.5)', overflow: 'hidden',
}

const headerStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px',
  borderBottom: '1px solid var(--border)', background: 'var(--bg-card)',
}

const selectStyle: CSSProperties = {
  background: 'var(--bg-input)', color: 'var(--text-primary)',
  border: '1px solid var(--border)', borderRadius: 6, padding: '3px 6px', fontSize: 12,
}

const iconBtnStyle: CSSProperties = {
  background: 'transparent', color: 'var(--text-secondary)', border: 'none',
  cursor: 'pointer', fontSize: 15, padding: '2px 6px',
}

const scrollStyle: CSSProperties = {
  flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 10,
}

const hintStyle: CSSProperties = {
  color: 'var(--text-secondary)', fontSize: 12, lineHeight: 1.5,
  padding: 10, border: '1px dashed var(--border)', borderRadius: 8,
}

const userRowStyle: CSSProperties = { display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }
const asstRowStyle: CSSProperties = { display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }

const bubbleBase: CSSProperties = {
  maxWidth: '92%', padding: '8px 10px', borderRadius: 10, fontSize: 13,
  lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
}
const userBubbleStyle: CSSProperties = {
  ...bubbleBase, background: 'var(--bg-input)', color: 'var(--text-primary)',
}
const asstBubbleStyle: CSSProperties = {
  ...bubbleBase, background: 'var(--bg-card)', color: 'var(--text-primary)',
  border: '1px solid var(--border)',
}

const toolsStyle: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }
const caretStyle: CSSProperties = { color: ACCENT, marginLeft: 1 }

const composerStyle: CSSProperties = {
  display: 'flex', gap: 8, padding: 10, borderTop: '1px solid var(--border)', background: 'var(--bg-card)',
}
const textareaStyle: CSSProperties = {
  flex: 1, resize: 'none', background: 'var(--bg-input)', color: 'var(--text-primary)',
  border: '1px solid var(--border)', borderRadius: 8, padding: '6px 8px', fontSize: 13,
  fontFamily: 'inherit',
}
const sendBtnStyle: CSSProperties = {
  background: ACCENT, color: '#001018', border: 'none', borderRadius: 8,
  padding: '0 14px', cursor: 'pointer', fontWeight: 600, fontSize: 13,
}
