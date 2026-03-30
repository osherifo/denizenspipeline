/** Live DICOM-to-BIDS conversion progress — log stream + timer + completion summary. */
import { useEffect, useState } from 'react'
import type { ConvertEvent } from '../../api/types'

interface Props {
  events: ConvertEvent[]
  startTime: number | null
  running: boolean
  error: string | null
  onDismiss?: () => void
}

const panelStyle = (status: 'running' | 'done' | 'failed'): React.CSSProperties => ({
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

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 12,
}

const titleStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const logStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
  maxHeight: 250,
  overflowY: 'auto',
  fontSize: 11,
  lineHeight: 1.8,
  fontFamily: 'monospace',
}

const pulseKeyframes = `
@keyframes convert-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
`

const dismissBtn: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontSize: 12,
  fontFamily: 'inherit',
}

function ElapsedTimer({ startTime }: { startTime: number | null }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!startTime) return
    const iv = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000)
    return () => clearInterval(iv)
  }, [startTime])

  if (!startTime) return null

  const min = Math.floor(elapsed / 60)
  const sec = elapsed % 60
  return (
    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
      {min > 0 ? `${min}m ${sec}s` : `${sec}s`}
    </span>
  )
}

function formatElapsed(seconds: number): string {
  const min = Math.floor(seconds / 60)
  const sec = Math.round(seconds % 60)
  if (min > 0) return `${min}m ${sec}s`
  return `${sec}s`
}

export function ConvertProgress({ events, startTime, running, error, onDismiss }: Props) {
  const lastEvent = events[events.length - 1]
  const isDone = lastEvent?.event === 'done'
  const isFailed = lastEvent?.event === 'failed' || !!error
  const status = isDone ? 'done' : isFailed ? 'failed' : 'running'

  return (
    <div style={panelStyle(status)}>
      <style>{pulseKeyframes}</style>
      <div style={headerStyle}>
        <div style={{
          ...titleStyle,
          color: isDone ? 'var(--accent-green)' : isFailed ? 'var(--accent-red)' : 'var(--accent-cyan)',
        }}>
          {running && <span style={{ animation: 'convert-pulse 1.5s infinite' }}>{'\u25CF'}</span>}
          {isDone && <span>{'\u2713'}</span>}
          {isFailed && !running && <span>{'\u2717'}</span>}
          <span>
            {isDone ? 'Conversion Complete' : isFailed && !running ? 'Conversion Failed' : 'Converting...'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {running && <ElapsedTimer startTime={startTime} />}
          {!running && lastEvent?.elapsed != null && (
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {formatElapsed(lastEvent.elapsed as number)}
            </span>
          )}
          {!running && onDismiss && (
            <button style={dismissBtn} onClick={onDismiss}>Dismiss</button>
          )}
        </div>
      </div>

      {/* Completion info */}
      {isDone && lastEvent && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: 'var(--accent-green)', fontWeight: 600 }}>
            {lastEvent.message || 'Conversion completed successfully'}
          </div>
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
        <div style={logStyle}>
          {events.map((ev, i) => (
            <div key={i} style={{
              color:
                ev.event === 'done' ? 'var(--accent-green)' :
                ev.event === 'failed' ? 'var(--accent-red)' :
                'var(--text-secondary)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}>
              {ev.message || ev.error || ev.event}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
