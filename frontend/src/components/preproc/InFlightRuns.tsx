/** In-flight panel — lists preproc runs, lets user reattach, cancel, or view logs. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'
import { fetchPreprocRun } from '../../api/client'
import type { PreprocRunSummary } from '../../api/types'

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
  gridTemplateColumns: '1fr 80px 80px 110px auto',
  alignItems: 'center',
  gap: 8,
  padding: '6px 0',
  borderTop: '1px solid var(--border)',
  fontSize: 11,
}

const actionsStyle: CSSProperties = {
  display: 'flex',
  gap: 6,
  justifyContent: 'flex-end',
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

const btn = (variant: 'link' | 'danger' | 'muted'): CSSProperties => ({
  padding: '3px 8px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: `1px solid ${
    variant === 'danger' ? 'var(--accent-red)' :
    variant === 'muted' ? 'var(--border)' :
    'var(--accent-cyan)'
  }`,
  borderRadius: 4,
  cursor: 'pointer',
  backgroundColor: 'transparent',
  color:
    variant === 'danger' ? 'var(--accent-red)' :
    variant === 'muted' ? 'var(--text-secondary)' :
    'var(--accent-cyan)',
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
  const [logDetail, setLogDetail] = useState<PreprocRunSummary | null>(null)
  const [logLoading, setLogLoading] = useState(false)
  const [logError, setLogError] = useState<string | null>(null)

  async function openLog(runId: string) {
    setLogDetail(null)
    setLogError(null)
    setLogLoading(true)
    try {
      const detail = await fetchPreprocRun(runId)
      setLogDetail(detail)
    } catch (e) {
      setLogError(String(e))
    } finally {
      setLogLoading(false)
    }
  }

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
            <div style={actionsStyle}>
              {isRunning && (
                <button
                  style={btn('link')}
                  onClick={() => attachToRun(r.run_id, r.started_at)}
                >
                  Watch
                </button>
              )}
              <button style={btn('muted')} onClick={() => openLog(r.run_id)}>
                Log
              </button>
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
      {(logDetail || logLoading || logError) && (
        <LogModal
          detail={logDetail}
          loading={logLoading}
          error={logError}
          onClose={() => { setLogDetail(null); setLogError(null) }}
        />
      )}
    </div>
  )
}


// ── Log modal ────────────────────────────────────────────────────────────

const overlayStyle: CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.6)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 100,
}

const modalStyle: CSSProperties = {
  width: 'min(1000px, 92vw)',
  height: '85vh',
  display: 'flex',
  flexDirection: 'column',
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '16px 20px',
  gap: 12,
}

const modalHeader: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
}

const modalTitle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
  fontFamily: 'monospace',
}

const modalMetaGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '110px 1fr',
  gap: '4px 14px',
  fontSize: 11,
  padding: '8px 10px',
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
}

const metaLabel: CSSProperties = {
  color: 'var(--text-secondary)',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  fontSize: 10,
}

const metaValue: CSSProperties = {
  color: 'var(--text-primary)',
  fontFamily: 'monospace',
  wordBreak: 'break-all',
}

const logPre: CSSProperties = {
  flex: 1,
  overflow: 'auto',
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
  fontSize: 10,
  lineHeight: 1.5,
  fontFamily: 'monospace',
  color: 'var(--text-primary)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  margin: 0,
  border: '1px solid var(--border)',
}

const errorBox: CSSProperties = {
  fontSize: 11,
  color: 'var(--accent-red)',
  backgroundColor: 'rgba(255, 23, 68, 0.08)',
  border: '1px solid rgba(255, 23, 68, 0.25)',
  borderRadius: 6,
  padding: '8px 12px',
  fontFamily: 'monospace',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}

function LogModal({
  detail,
  loading,
  error,
  onClose,
}: {
  detail: PreprocRunSummary | null
  loading: boolean
  error: string | null
  onClose: () => void
}) {
  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={modalHeader}>
          <div style={modalTitle}>
            {detail
              ? `${detail.subject} — ${detail.run_id}`
              : loading ? 'Loading log…' : 'Log'}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {detail?.log_tail && (
              <button
                style={btn('muted')}
                onClick={() => {
                  navigator.clipboard?.writeText(detail.log_tail || '')
                }}
              >
                Copy
              </button>
            )}
            <button style={btn('muted')} onClick={onClose}>Close</button>
          </div>
        </div>

        {error && <div style={errorBox}>{error}</div>}

        {detail && (
          <>
            <div style={modalMetaGrid}>
              <div style={metaLabel}>Status</div>
              <div style={{ ...metaValue, color: statusColor(detail.status), textTransform: 'uppercase' }}>
                {detail.status}
              </div>
              <div style={metaLabel}>Backend</div>
              <div style={metaValue}>{detail.backend}</div>
              <div style={metaLabel}>PID</div>
              <div style={metaValue}>{detail.pid ?? '-'}</div>
              <div style={metaLabel}>Started</div>
              <div style={metaValue}>{formatWhen(detail.started_at)}</div>
              {detail.finished_at > 0 && (
                <>
                  <div style={metaLabel}>Finished</div>
                  <div style={metaValue}>{formatWhen(detail.finished_at)}</div>
                </>
              )}
              <div style={metaLabel}>Elapsed</div>
              <div style={metaValue}>
                {formatElapsed(detail.started_at, detail.finished_at, detail.status === 'running')}
              </div>
              {detail.log_path && (
                <>
                  <div style={metaLabel}>Log file</div>
                  <div style={metaValue}>{detail.log_path}</div>
                </>
              )}
              {detail.error && (
                <>
                  <div style={metaLabel}>Error</div>
                  <div style={{ ...metaValue, color: 'var(--accent-red)' }}>{detail.error}</div>
                </>
              )}
            </div>

            <pre style={logPre}>
              {detail.log_tail && detail.log_tail.length > 0
                ? detail.log_tail
                : '(log empty — the subprocess may not have written anything yet)'}
            </pre>
          </>
        )}
      </div>
    </div>
  )
}
