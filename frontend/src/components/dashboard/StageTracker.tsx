import type { CSSProperties } from 'react'
/** Vertical stage status tracker for live runs. */
import type { StageStatus } from '../../api/types'

interface StageTrackerProps {
  stageStatuses: Record<string, StageStatus>
}

const ALL_STAGES = ['stimuli', 'responses', 'features', 'preprocess', 'model', 'analyze', 'report']

const containerStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 2,
}

const stageRow: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '100px 24px 1fr 70px',
  alignItems: 'center',
  padding: '6px 0',
  gap: 8,
}

const stageLabel: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  textAlign: 'right',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

function statusIcon(status: StageStatus['status']): { symbol: string; color: string } {
  switch (status) {
    case 'done': return { symbol: '\u2713', color: 'var(--accent-green)' }
    case 'running': return { symbol: '\u25CF', color: 'var(--accent-cyan)' }
    case 'failed': return { symbol: '\u2717', color: 'var(--accent-red)' }
    case 'warning': return { symbol: '!', color: 'var(--accent-yellow)' }
    default: return { symbol: '\u25CB', color: 'var(--text-secondary)' }
  }
}

function formatElapsed(s: number): string {
  if (s <= 0) return ''
  if (s < 1) return `${(s * 1000).toFixed(0)}ms`
  if (s < 60) return `${s.toFixed(1)}s`
  const min = Math.floor(s / 60)
  const sec = s % 60
  return `${min}m ${sec.toFixed(0)}s`
}

export function StageTracker({ stageStatuses }: StageTrackerProps) {
  return (
    <div style={containerStyle}>
      {ALL_STAGES.map((name) => {
        const stage = stageStatuses[name] || { status: 'pending', detail: '', elapsed_s: 0 }
        const icon = statusIcon(stage.status)

        return (
          <div key={name} style={stageRow}>
            <div style={{
              ...stageLabel,
              color: stage.status === 'running' ? 'var(--accent-cyan)' :
                     stage.status === 'done' ? 'var(--text-primary)' :
                     'var(--text-secondary)',
            }}>
              {name}
            </div>
            <div style={{
              fontSize: 14,
              textAlign: 'center',
              color: icon.color,
              animation: stage.status === 'running' ? 'pulse 1.5s infinite' : undefined,
            }}>
              {icon.symbol}
            </div>
            <div style={{
              fontSize: 11,
              color: stage.status === 'failed' ? 'var(--accent-red)' : 'var(--text-secondary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {stage.status === 'running' ? 'running...' : stage.detail}
            </div>
            <div style={{
              fontSize: 11,
              color: 'var(--text-secondary)',
              textAlign: 'right',
            }}>
              {formatElapsed(stage.elapsed_s)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
