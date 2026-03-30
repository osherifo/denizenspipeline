/** Batch DICOM-to-BIDS conversion progress — summary bar + per-job status table + log. */
import { useEffect, useRef, useState } from 'react'
import { useConvertStore } from '../../stores/convert-store'
import type { BatchEvent, BatchJobStatus } from '../../api/types'

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

const pulseKeyframes = `
@keyframes batch-pulse {
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

const countsBar: React.CSSProperties = {
  display: 'flex',
  gap: 16,
  marginBottom: 12,
  fontSize: 12,
  fontWeight: 600,
}

const thStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  padding: '6px 8px',
  textAlign: 'left',
  borderBottom: '1px solid var(--border)',
}

const tdStyle: React.CSSProperties = {
  padding: '6px 8px',
  fontSize: 12,
  borderBottom: '1px solid var(--border)',
}

const logStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
  maxHeight: 200,
  overflowY: 'auto',
  fontSize: 11,
  lineHeight: 1.8,
  fontFamily: 'monospace',
  marginTop: 12,
}

function statusBadge(status: string): React.CSSProperties {
  const colors: Record<string, string> = {
    queued: 'var(--text-secondary)',
    running: 'var(--accent-cyan)',
    done: 'var(--accent-green)',
    failed: 'var(--accent-red)',
  }
  return {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 600,
    color: colors[status] || 'var(--text-secondary)',
    backgroundColor: `${colors[status] || 'var(--text-secondary)'}15`,
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  }
}

function formatElapsed(seconds: number): string {
  const min = Math.floor(seconds / 60)
  const sec = Math.round(seconds % 60)
  if (min > 0) return `${min}m ${sec}s`
  return `${sec}s`
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

export function BatchProgress() {
  const {
    batchRunning, batchEvents, batchJobStatuses, batchCounts,
    batchError, batchStartTime, clearBatch,
  } = useConvertStore()

  const [expandedJob, setExpandedJob] = useState<string | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  const hasFailed = batchCounts.failed > 0
  const isDone = !batchRunning && batchEvents.some((e) => e.event === 'batch_done')
  const status = isDone ? (hasFailed ? 'failed' : 'done') : 'running'

  const jobList = Object.values(batchJobStatuses).sort((a, b) => {
    const order = { running: 0, done: 1, failed: 2, queued: 3 }
    return (order[a.status] ?? 4) - (order[b.status] ?? 4)
  })

  // Log events: all events with a message/error, or per-job if one is selected
  const isLogEvent = (e: BatchEvent) =>
    e.event === 'log' || e.event === 'started' || e.event === 'done' || e.event === 'failed'

  const logEvents = expandedJob
    ? batchEvents.filter((e) => e.job_id === expandedJob && isLogEvent(e))
    : batchEvents.filter((e) => e.job_id && isLogEvent(e))

  // Auto-scroll log to bottom on new events
  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [logEvents.length])

  // Resolve job_id to a label for the global log
  const jobLabel = (jobId: string) => {
    const js = batchJobStatuses[jobId]
    if (!js) return jobId
    return `sub-${js.subject}${js.session ? ` ses-${js.session}` : ''}`
  }

  return (
    <div style={panelStyle(status)}>
      <style>{pulseKeyframes}</style>

      {/* Header */}
      <div style={headerStyle}>
        <div style={{
          ...titleStyle,
          color: isDone && !hasFailed ? 'var(--accent-green)' : hasFailed && !batchRunning ? 'var(--accent-red)' : 'var(--accent-cyan)',
        }}>
          {batchRunning && <span style={{ animation: 'batch-pulse 1.5s infinite' }}>{'\u25CF'}</span>}
          {isDone && !hasFailed && <span>{'\u2713'}</span>}
          {isDone && hasFailed && <span>{'\u2717'}</span>}
          <span>
            {isDone && !hasFailed ? 'Batch Complete' :
             isDone && hasFailed ? `Batch Complete (${batchCounts.failed} failed)` :
             'Batch Converting...'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {batchRunning && <ElapsedTimer startTime={batchStartTime} />}
          {!batchRunning && (
            <button style={dismissBtn} onClick={clearBatch}>Dismiss</button>
          )}
        </div>
      </div>

      {/* Counts bar */}
      <div style={countsBar}>
        <span style={{ color: 'var(--text-secondary)' }}>
          {batchCounts.queued > 0 && <>{batchCounts.queued} queued{' '}</>}
        </span>
        <span style={{ color: 'var(--accent-cyan)' }}>
          {batchCounts.running > 0 && <>{batchCounts.running} running{' '}</>}
        </span>
        <span style={{ color: 'var(--accent-green)' }}>
          {batchCounts.done > 0 && <>{batchCounts.done} done{' '}</>}
        </span>
        <span style={{ color: 'var(--accent-red)' }}>
          {batchCounts.failed > 0 && <>{batchCounts.failed} failed</>}
        </span>
      </div>

      {/* Error */}
      {batchError && (
        <div style={{ fontSize: 12, color: 'var(--accent-red)', marginBottom: 12 }}>
          {batchError}
        </div>
      )}

      {/* Jobs table */}
      {jobList.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>Subject</th>
                <th style={thStyle}>Session</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Elapsed</th>
                <th style={thStyle}>Error</th>
              </tr>
            </thead>
            <tbody>
              {jobList.map((job) => {
                const elapsed = job.finished_at && job.started_at
                  ? formatElapsed((job.finished_at - job.started_at))
                  : job.started_at ? '...' : '-'
                return (
                  <tr
                    key={job.job_id}
                    style={{ cursor: 'pointer', backgroundColor: expandedJob === job.job_id ? 'rgba(0,229,255,0.04)' : 'transparent' }}
                    onClick={() => setExpandedJob(expandedJob === job.job_id ? null : job.job_id)}
                  >
                    <td style={tdStyle}>{job.subject}</td>
                    <td style={tdStyle}>{job.session || '-'}</td>
                    <td style={tdStyle}><span style={statusBadge(job.status)}>{job.status}</span></td>
                    <td style={tdStyle}>{elapsed}</td>
                    <td style={{ ...tdStyle, color: 'var(--accent-red)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {job.error || ''}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Log stream */}
      <div style={logStyle} ref={logRef}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>
            {expandedJob ? `Log: ${jobLabel(expandedJob)}` : 'Log (all jobs)'}
          </span>
          {expandedJob && (
            <button
              style={{ ...dismissBtn, fontSize: 11, padding: 0 }}
              onClick={(e) => { e.stopPropagation(); setExpandedJob(null) }}
            >
              show all
            </button>
          )}
        </div>
        {logEvents.length === 0 && (
          <div style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>
            {batchRunning ? 'Waiting for events...' : 'No log events.'}
          </div>
        )}
        {logEvents.map((ev, i) => (
          <div key={i} style={{
            color:
              ev.event === 'done' ? 'var(--accent-green)' :
              ev.event === 'failed' ? 'var(--accent-red)' :
              ev.event === 'started' ? 'var(--accent-cyan)' :
              'var(--text-secondary)',
          }}>
            {!expandedJob && ev.job_id && (
              <span style={{ color: 'var(--accent-cyan)', opacity: 0.6, marginRight: 6 }}>
                [{jobLabel(ev.job_id)}]
              </span>
            )}
            {ev.message || ev.error || ev.event}
          </div>
        ))}
      </div>
    </div>
  )
}
