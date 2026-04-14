/** Live autoflatten progress — log stream + timer + completion summary. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { AutoflattenEvent } from '../../stores/autoflatten-store'

interface Props {
  events: AutoflattenEvent[]
  startTime: number | null
  running: boolean
  error: string | null
  onDismiss?: () => void
}

const panelStyle = (status: 'running' | 'done' | 'failed'): CSSProperties => ({
  backgroundColor: 'var(--bg-card)',
  border: `1px solid ${
    status === 'done' ? 'var(--accent-green)' :
    status === 'failed' ? 'var(--accent-red)' :
    'var(--accent-cyan)'
  }`,
  borderRadius: 8,
  padding: '16px 20px',
  marginTop: 16,
})

const headerStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 12,
}

const titleStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const logStyle: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
  maxHeight: 320,
  overflowY: 'auto',
  fontSize: 11,
  lineHeight: 1.6,
  fontFamily: 'monospace',
}

const pulseKeyframes = `
@keyframes autoflatten-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
`

const dismissBtn: CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontSize: 12,
  fontFamily: 'inherit',
}

function ElapsedTimer({ startTime, running }: { startTime: number | null; running: boolean }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!startTime || !running) return
    const iv = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000)
    return () => clearInterval(iv)
  }, [startTime, running])

  if (!startTime) return null

  const min = Math.floor(elapsed / 60)
  const sec = elapsed % 60
  return (
    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
      {min > 0 ? `${min}m ${sec}s` : `${sec}s`}
    </span>
  )
}

function levelColor(level?: string, event?: string): string {
  if (event === 'done') return 'var(--accent-green)'
  if (event === 'failed' || level === 'ERROR') return 'var(--accent-red)'
  if (level === 'WARNING') return 'var(--accent-yellow, #e2a832)'
  return 'var(--text-secondary)'
}

export function AutoflattenProgress({ events, startTime, running, error, onDismiss }: Props) {
  const lastEvent = events[events.length - 1]
  const isDone = lastEvent?.event === 'done'
  const isFailed = lastEvent?.event === 'failed' || !!error
  const status = isDone ? 'done' : isFailed ? 'failed' : 'running'

  // Auto-scroll the log to the bottom as new events arrive
  const [logRef, setLogRef] = useState<HTMLDivElement | null>(null)
  useEffect(() => {
    if (logRef) logRef.scrollTop = logRef.scrollHeight
  }, [events.length, logRef])

  return (
    <div style={panelStyle(status)}>
      <style>{pulseKeyframes}</style>
      <div style={headerStyle}>
        <div style={{
          ...titleStyle,
          color: isDone ? 'var(--accent-green)' : isFailed ? 'var(--accent-red)' : 'var(--accent-cyan)',
        }}>
          {running && <span style={{ animation: 'autoflatten-pulse 1.5s infinite' }}>{'\u25CF'}</span>}
          {isDone && <span>{'\u2713'}</span>}
          {isFailed && !running && <span>{'\u2717'}</span>}
          <span>
            {isDone ? 'Autoflatten Complete' : isFailed && !running ? 'Autoflatten Failed' : 'Running...'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ElapsedTimer startTime={startTime} running={running} />
          {!running && onDismiss && (
            <button style={dismissBtn} onClick={onDismiss}>Dismiss</button>
          )}
        </div>
      </div>

      {/* Completion info */}
      {isDone && lastEvent && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: 'var(--accent-green)', fontWeight: 600 }}>
            {lastEvent.message}
            {lastEvent.elapsed !== undefined && ` in ${lastEvent.elapsed.toFixed(1)}s`}
          </div>
          {lastEvent.pycortex_surface && (
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
              pycortex surface: {lastEvent.pycortex_surface}
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {isFailed && error && (
        <div style={{ fontSize: 12, color: 'var(--accent-red)', marginBottom: 12 }}>
          {error}
        </div>
      )}

      {/* Log */}
      {events.length > 0 && (
        <div style={logStyle} ref={setLogRef}>
          {events.map((ev, i) => (
            <div key={i} style={{
              color: levelColor(ev.level, ev.event),
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {ev.message ?? ev.error ?? ev.event}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
