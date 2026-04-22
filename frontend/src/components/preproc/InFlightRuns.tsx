/** In-flight panel — lists preproc runs, lets user reattach or cancel. */
import { useEffect } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'

const panelStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '14px 18px',
  marginBottom: 12,
}

const headerStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 10,
}

const titleStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const refreshBtn: CSSProperties = {
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 4,
  cursor: 'pointer',
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
}

const rowStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 80px 80px 110px 90px 80px',
  alignItems: 'center',
  gap: 8,
  padding: '6px 0',
  borderTop: '1px solid var(--border)',
  fontSize: 11,
}

const emptyStyle: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  fontStyle: 'italic',
  padding: '6px 0',
}

function statusColor(status: string): string {
  switch (status) {
    case 'running': return 'var(--accent-cyan)'
    case 'done': return 'var(--accent-green)'
    case 'failed':
    case 'cancelled':
    case 'lost': return 'var(--accent-red)'
    default: return 'var(--text-secondary)'
  }
}

function formatElapsed(startedAt: number, finishedAt: number, isRunning: boolean): string {
  const end = isRunning ? Date.now() / 1000 : finishedAt
  const s = Math.max(0, end - startedAt)
  if (s < 60) return `${Math.round(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`
}

function formatWhen(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

const btn = (variant: 'link' | 'danger'): CSSProperties => ({
  padding: '3px 8px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: `1px solid ${variant === 'danger' ? 'var(--accent-red)' : 'var(--accent-cyan)'}`,
  borderRadius: 4,
  cursor: 'pointer',
  backgroundColor: 'transparent',
  color: variant === 'danger' ? 'var(--accent-red)' : 'var(--accent-cyan)',
})

interface InFlightRunsProps {
  // Show only `running` when true; show everything otherwise.
  runningOnly?: boolean
}

export function InFlightRuns({ runningOnly = false }: InFlightRunsProps) {
  const {
    preprocRuns,
    preprocRunsLoading,
    loadPreprocRuns,
    attachToRun,
    cancelRun,
    running: liveRunning,
  } = usePreprocStore()

  useEffect(() => {
    loadPreprocRuns()
  }, [loadPreprocRuns])

  // Auto-refresh every 5s while any run is marked running
  useEffect(() => {
    const hasLive = preprocRuns.some((r) => r.status === 'running')
    if (!hasLive && !liveRunning) return
    const id = setInterval(() => loadPreprocRuns(), 5000)
    return () => clearInterval(id)
  }, [preprocRuns, liveRunning, loadPreprocRuns])

  const visible = runningOnly
    ? preprocRuns.filter((r) => r.status === 'running')
    : preprocRuns

  const title = runningOnly ? 'In Flight' : 'Recent Runs'
  const count = visible.length

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <span style={titleStyle}>{title} ({count})</span>
        <button style={refreshBtn} onClick={() => loadPreprocRuns()}>
          {preprocRunsLoading ? '...' : 'Refresh'}
        </button>
      </div>
      {visible.length === 0 && (
        <div style={emptyStyle}>
          {runningOnly ? 'No running preprocessing jobs.' : 'No recent runs.'}
        </div>
      )}
      {visible.map((r) => {
        const isRunning = r.status === 'running'
        return (
          <div key={r.run_id} style={rowStyle}>
            <div>
              <div style={{ fontFamily: 'monospace', color: 'var(--text-primary)', fontWeight: 600 }}>
                {r.subject}
                {r.is_reattached && (
                  <span style={{ marginLeft: 8, fontSize: 9, color: 'var(--accent-yellow, #e2a832)', fontWeight: 600 }}>
                    REATTACHED
                  </span>
                )}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                {r.run_id} · {r.backend}{r.pid ? ` · pid ${r.pid}` : ''}
              </div>
            </div>
            <div style={{ color: statusColor(r.status), fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {r.status}
            </div>
            <div style={{ color: 'var(--text-secondary)' }}>
              {formatElapsed(r.started_at, r.finished_at, isRunning)}
            </div>
            <div style={{ color: 'var(--text-secondary)' }}>
              {formatWhen(r.started_at)}
            </div>
            <div>
              {isRunning && (
                <button
                  style={btn('link')}
                  onClick={() => attachToRun(r.run_id, r.started_at)}
                >
                  Watch
                </button>
              )}
            </div>
            <div>
              {isRunning && (
                <button
                  style={btn('danger')}
                  onClick={() => {
                    if (confirm(`Cancel run for ${r.subject}?`)) {
                      cancelRun(r.run_id).catch((e) => alert(String(e)))
                    }
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
