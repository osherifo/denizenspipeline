import type { StageRecord } from '../../api/types'

interface StageTimelineProps {
  stages: StageRecord[]
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  padding: '8px 0',
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
}

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  width: 100,
  textAlign: 'right',
  flexShrink: 0,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const barContainerStyle: React.CSSProperties = {
  flex: 1,
  height: 22,
  backgroundColor: 'var(--bg-input)',
  borderRadius: 4,
  overflow: 'hidden',
  position: 'relative',
}

function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'ok':
    case 'success':
    case 'done':
    case 'completed':
      return 'var(--accent-green)'
    case 'warning':
    case 'warn':
      return 'var(--accent-yellow)'
    case 'error':
    case 'failed':
    case 'fail':
      return 'var(--accent-red)'
    case 'skipped':
    case 'skip':
      return 'var(--text-secondary)'
    case 'running':
      return 'var(--accent-cyan)'
    default:
      return 'var(--text-secondary)'
  }
}

const timeStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  width: 60,
  textAlign: 'right',
  flexShrink: 0,
}

function formatElapsed(s: number): string {
  if (s < 1) return `${(s * 1000).toFixed(0)}ms`
  if (s < 60) return `${s.toFixed(1)}s`
  const min = Math.floor(s / 60)
  const sec = s % 60
  return `${min}m ${sec.toFixed(0)}s`
}

export function StageTimeline({ stages }: StageTimelineProps) {
  const maxElapsed = Math.max(...stages.map((s) => s.elapsed_s), 0.001)

  return (
    <div style={containerStyle}>
      {stages.map((stage) => {
        const pct = Math.max((stage.elapsed_s / maxElapsed) * 100, 2)
        const color = statusColor(stage.status)
        return (
          <div key={stage.name} style={rowStyle}>
            <div style={labelStyle}>{stage.name}</div>
            <div style={barContainerStyle}>
              <div
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  backgroundColor: color,
                  borderRadius: 4,
                  opacity: 0.7,
                  transition: 'width 0.3s ease',
                }}
                title={`${stage.name}: ${stage.status} (${formatElapsed(stage.elapsed_s)})\n${stage.detail || ''}`}
              />
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 8,
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  fontSize: 10,
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  pointerEvents: 'none',
                }}
              >
                {stage.status}
              </div>
            </div>
            <div style={timeStyle}>{formatElapsed(stage.elapsed_s)}</div>
          </div>
        )
      })}
    </div>
  )
}
