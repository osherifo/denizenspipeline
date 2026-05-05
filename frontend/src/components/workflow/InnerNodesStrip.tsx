/** Render a strip of nipype-node status pills under a stage block.
 *
 * Variable-N siblings, grouped by workflow path so a 200-node fmriprep
 * graph stays scannable. Default-collapsed; expand on click to see all.
 */

import { memo } from 'react'
import type { CSSProperties } from 'react'
import type {
  NipypeStatusCounts,
  NipypeStatusBlock,
} from '../../api/types'

const STATUS_COLOR: Record<string, string> = {
  running: '#00e5ff',
  ok: '#00e676',
  failed: '#ff1744',
  // Softer green for inferred-as-finished (no Finished log line seen).
  completed_assumed: '#52c98f',
  // Anything else falls back to neutral
}

const containerStyle: CSSProperties = {
  marginTop: 6,
  padding: '6px 8px',
  borderRadius: 6,
  background: 'rgba(16, 185, 129, 0.08)',
  border: '1px solid rgba(16, 185, 129, 0.25)',
  fontSize: 10,
  color: 'var(--text-primary)',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  userSelect: 'none',
}

const viewBtn = (color: string): CSSProperties => ({
  marginLeft: 'auto',
  padding: '2px 8px',
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: 0.5,
  borderRadius: 4,
  background: `${color}33`,
  color,
  border: `1px solid ${color}88`,
  cursor: 'pointer',
  textTransform: 'uppercase',
})

const countPill = (color: string): CSSProperties => ({
  padding: '1px 6px',
  borderRadius: 8,
  background: `${color}22`,
  color,
  border: `1px solid ${color}55`,
  fontSize: 9,
  fontWeight: 700,
})

function _summarize(counts: NipypeStatusCounts): React.ReactNode {
  const items: { color: string; label: string }[] = []
  if (counts.running) items.push({ color: STATUS_COLOR.running, label: `${counts.running} running` })
  if (counts.ok) items.push({ color: STATUS_COLOR.ok, label: `${counts.ok} done` })
  if (counts.failed) items.push({ color: STATUS_COLOR.failed, label: `${counts.failed} failed` })
  if (counts.completed_assumed)
    items.push({
      color: STATUS_COLOR.completed_assumed,
      label: `${counts.completed_assumed} assumed`,
    })
  if (items.length === 0) {
    return <span style={{ color: 'var(--text-secondary)' }}>no nodes seen yet</span>
  }
  return (
    <>
      {items.map((it, i) => (
        <span key={i} style={countPill(it.color)}>{it.label}</span>
      ))}
    </>
  )
}


interface Props {
  block: NipypeStatusBlock
  onOpenDag?: () => void
}

function InnerNodesStripInner({ block, onOpenDag }: Props) {
  const total = block.counts.total_seen
  // Pick the dominant status color for the View DAG button.
  const btnColor =
    block.counts.failed > 0 ? STATUS_COLOR.failed
    : block.counts.running > 0 ? STATUS_COLOR.running
    : STATUS_COLOR.ok
  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <span style={{ fontWeight: 700 }}>nipype nodes</span>
        {_summarize(block.counts)}
        {total > 0 && (
          <span style={{ color: 'var(--text-secondary)', marginLeft: 4 }}>
            ({total} seen)
          </span>
        )}
        {onOpenDag && total > 0 && (
          <button
            style={viewBtn(btnColor)}
            onClick={(e) => {
              e.stopPropagation()
              onOpenDag()
            }}
          >
            View DAG →
          </button>
        )}
      </div>
    </div>
  )
}


export const InnerNodesStrip = memo(InnerNodesStripInner)
