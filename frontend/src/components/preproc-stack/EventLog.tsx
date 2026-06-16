/**
 * EventLog — scrolling view of live WebSocket events from a stack run.
 *
 * Each event is rendered as a one-line summary with the most useful
 * fields. The raw JSON isn't shown for v1; we can add an expand
 * affordance later if it's useful for debugging.
 */

import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'
import type { StackEvent } from '../../api/types'


const panelStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: 12,
  marginTop: 16,
  maxHeight: 320,
  overflowY: 'auto',
  fontSize: 12,
  fontFamily:
    "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
}

const headerStyle: CSSProperties = {
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 1,
  color: 'var(--text-secondary)',
  marginBottom: 8,
}


const EVENT_COLOR: Record<string, string> = {
  started: 'var(--accent-cyan)',
  stage_start: 'var(--accent-yellow)',
  stage_done: 'var(--accent-green)',
  stage_failed: 'var(--accent-red)',
  completed: 'var(--accent-green)',
  failed: 'var(--accent-red)',
  _close: 'var(--text-secondary)',
}


function summarise(ev: StackEvent): string {
  switch (ev.event) {
    case 'started':
      return `▶ run started · subject=${ev.subject} · ${ev.n_stages} stages`
    case 'stage_start':
      return `· stage ${ev.stage_index} (${ev.kind}): ${ev.stage_name} starting`
    case 'stage_done': {
      const cache = ev.cache_hit ? ' (cache hit)' : ''
      const dur = ev.duration_s !== undefined ? ` ${ev.duration_s.toFixed(2)}s` : ''
      return `✓ stage ${ev.stage_index} (${ev.kind}): ${ev.stage_name} done${cache}${dur}`
    }
    case 'stage_failed':
      return `✗ stage ${ev.stage_index} (${ev.kind}): ${ev.stage_name} failed — ${ev.error}`
    case 'completed':
      return `✓ completed · ${ev.n_stages} stages · ${ev.duration_s?.toFixed(2) ?? '?'}s`
    case 'failed': {
      const msg = (ev.errors && ev.errors.join('; ')) || ev.error || 'unknown error'
      return `✗ failed — ${msg}`
    }
    case '_close':
      return `— terminal · status=${ev.status}`
    default:
      return JSON.stringify(ev)
  }
}


export function EventLog() {
  const events = usePreprocStackStore((s) => s.activeEvents)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Auto-scroll to the latest event when new ones arrive.
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events.length])

  if (events.length === 0) return null

  return (
    <div ref={scrollRef} style={panelStyle}>
      <div style={headerStyle}>Live events ({events.length})</div>
      {events.map((ev, i) => (
        <div
          key={i}
          style={{
            color: EVENT_COLOR[ev.event] ?? 'var(--text-primary)',
            marginBottom: 2,
            whiteSpace: 'pre-wrap',
          }}
        >
          {summarise(ev)}
        </div>
      ))}
    </div>
  )
}
