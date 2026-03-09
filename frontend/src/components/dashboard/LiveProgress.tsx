/** Live progress panel with stage tracker and event log. */
import { useEffect, useState } from 'react'
import type { RunEvent, StageStatus, RunSummary, ArtifactInfo } from '../../api/types'
import { StageTracker } from './StageTracker'
import { StageTimeline } from '../runs/StageTimeline'
import { artifactUrl } from '../../api/client'

interface LiveProgressProps {
  runId: string
  events: RunEvent[]
  stageStatuses: Record<string, StageStatus>
  startTime: number | null
  completedRun?: RunSummary | null
  onDismiss?: () => void
}

const panelStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--accent-cyan)',
  borderRadius: 8,
  padding: '20px',
  marginBottom: 16,
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 16,
}

const titleStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const elapsedStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 16,
  marginBottom: 8,
}

const eventLogStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
  maxHeight: 200,
  overflowY: 'auto',
  fontSize: 11,
  lineHeight: 1.8,
  fontFamily: 'monospace',
}

const eventLine: React.CSSProperties = {
  color: 'var(--text-secondary)',
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}

function formatTimestamp(ts: number | undefined, startTime: number | null): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatEventLine(event: RunEvent): string {
  switch (event.event) {
    case 'stage_start':
      return `\u25B6 ${event.stage}`
    case 'stage_done':
      return `\u2713 ${event.stage}: ${event.detail || 'done'} (${event.elapsed?.toFixed(1)}s)`
    case 'stage_fail':
      return `\u2717 ${event.stage}: ${event.error || 'failed'}`
    case 'stage_warn':
      return `! ${event.stage}: ${event.detail || 'warning'}`
    case 'feature_info':
      return `  feature: ${(event as any).name || ''} (${(event as any).source || ''})`
    case 'data_warning':
      return `  warning: ${(event as any).message || ''}`
    case 'run_done':
      return `\u2713 Run completed (${(event as any).total_elapsed?.toFixed(1)}s)`
    case 'run_failed':
      return `\u2717 Run failed: ${event.error || ''}`
    default:
      return `${event.event}`
  }
}

function ElapsedTimer({ startTime }: { startTime: number | null }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!startTime) return
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [startTime])

  if (!startTime) return null

  const min = Math.floor(elapsed / 60)
  const sec = elapsed % 60
  return (
    <span style={elapsedStyle}>
      {min > 0 ? `${min}m ${sec}s` : `${sec}s`}
    </span>
  )
}

const resultsGrid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
  gap: 10,
  marginBottom: 16,
}

const resultCard: React.CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
}

const resultLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 3,
}

const resultValue: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 700,
  color: 'var(--text-primary)',
}

const artifactRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '6px 10px',
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 4,
  marginBottom: 4,
  fontSize: 11,
}

const artifactLink: React.CSSProperties = {
  color: 'var(--accent-cyan)',
  textDecoration: 'none',
  fontWeight: 600,
  fontSize: 11,
}

function formatDuration(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function LiveProgress({ runId, events, stageStatuses, startTime, completedRun, onDismiss }: LiveProgressProps) {
  // Check if run is complete
  const lastEvent = events[events.length - 1]
  const isDone = lastEvent?.event === 'run_done'
  const isFailed = lastEvent?.event === 'run_failed'
  const isFinished = isDone || isFailed

  const artifacts = completedRun?.artifacts ? Object.values(completedRun.artifacts) : []

  return (
    <div style={{
      ...panelStyle,
      borderColor: isDone ? 'var(--accent-green)' : isFailed ? 'var(--accent-red)' : 'var(--accent-cyan)',
    }}>
      <div style={headerStyle}>
        <div style={titleStyle}>
          {!isDone && !isFailed && (
            <span style={{ animation: 'pulse 1.5s infinite' }}>{'\u25CF'}</span>
          )}
          {isDone && <span style={{ color: 'var(--accent-green)' }}>{'\u2713'}</span>}
          {isFailed && <span style={{ color: 'var(--accent-red)' }}>{'\u2717'}</span>}
          <span>
            {isDone ? 'Run Complete' : isFailed ? 'Run Failed' : `Running ${runId}`}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ElapsedTimer startTime={isDone || isFailed ? null : startTime} />
          {isFinished && onDismiss && (
            <button
              onClick={onDismiss}
              style={{
                background: 'none', border: 'none', color: 'var(--text-secondary)',
                cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
              }}
            >
              Dismiss
            </button>
          )}
        </div>
      </div>

      {/* Results summary — shown after completion */}
      {isFinished && completedRun && (
        <>
          <div style={resultsGrid}>
            <div style={resultCard}>
              <div style={resultLabel}>Mean Score</div>
              <div style={{
                ...resultValue,
                color: completedRun.mean_score != null ? 'var(--accent-green)' : 'var(--text-secondary)',
              }}>
                {completedRun.mean_score != null ? completedRun.mean_score.toFixed(4) : '-'}
              </div>
            </div>
            <div style={resultCard}>
              <div style={resultLabel}>Duration</div>
              <div style={resultValue}>{formatDuration(completedRun.total_elapsed_s)}</div>
            </div>
            <div style={resultCard}>
              <div style={resultLabel}>Status</div>
              <div style={{
                ...resultValue,
                color: completedRun.status === 'ok' ? 'var(--accent-green)' :
                       completedRun.status === 'failed' ? 'var(--accent-red)' : 'var(--text-primary)',
              }}>
                {completedRun.status}
              </div>
            </div>
            <div style={resultCard}>
              <div style={resultLabel}>Output</div>
              <div style={{ ...resultValue, fontSize: 10, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {completedRun.output_dir || '-'}
              </div>
            </div>
          </div>

          {/* Stage timeline bar chart */}
          {completedRun.stages?.length > 0 && (
            <>
              <div style={sectionLabel}>Stage Timeline</div>
              <StageTimeline stages={completedRun.stages} />
            </>
          )}

          {/* Artifacts */}
          {artifacts.length > 0 && (
            <>
              <div style={sectionLabel}>Artifacts ({artifacts.length})</div>
              {artifacts.map((art: ArtifactInfo) => (
                <div key={art.name} style={artifactRow}>
                  <span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{art.name}</span>
                    <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>
                      {art.type} / {formatSize(art.size)}
                    </span>
                  </span>
                  <div style={{ display: 'flex', gap: 12 }}>
                    <a
                      href={artifactUrl(completedRun.run_id, art.name)}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={artifactLink}
                    >
                      View
                    </a>
                    <a
                      href={artifactUrl(completedRun.run_id, art.name)}
                      download
                      style={artifactLink}
                    >
                      Download
                    </a>
                  </div>
                </div>
              ))}
            </>
          )}

          {/* Log tail */}
          {completedRun.log_tail && (
            <>
              <div style={sectionLabel}>Log (tail)</div>
              <pre style={{
                backgroundColor: 'var(--bg-secondary)', padding: '10px 12px', borderRadius: 6,
                fontSize: 10, lineHeight: 1.6, color: 'var(--text-secondary)',
                overflow: 'auto', maxHeight: 200, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              }}>
                {completedRun.log_tail}
              </pre>
            </>
          )}
        </>
      )}

      {/* Loading results indicator */}
      {isFinished && !completedRun && (
        <div style={{ padding: '12px 0', fontSize: 12, color: 'var(--text-secondary)' }}>
          Loading results...
        </div>
      )}

      {/* Stage tracker — shown while running */}
      {!isFinished && <StageTracker stageStatuses={stageStatuses} />}

      {/* Event log */}
      {events.length > 0 && (
        <>
          <div style={sectionLabel}>Event Log</div>
          <div style={eventLogStyle}>
            {events.map((event, i) => (
              <div key={i} style={eventLine}>
                <span style={{ color: 'var(--text-secondary)', marginRight: 8 }}>
                  {formatTimestamp(event.timestamp, startTime)}
                </span>
                <span style={{
                  color:
                    event.event === 'stage_fail' || event.event === 'run_failed' ? 'var(--accent-red)' :
                    event.event === 'stage_done' || event.event === 'run_done' ? 'var(--accent-green)' :
                    event.event === 'stage_start' ? 'var(--accent-cyan)' :
                    'var(--text-secondary)',
                }}>
                  {formatEventLine(event)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
