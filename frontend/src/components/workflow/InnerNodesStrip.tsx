/** Render a strip of nipype-node status pills under a stage block.
 *
 * Variable-N siblings, grouped by workflow path so a 200-node fmriprep
 * graph stays scannable. Default-collapsed; expand on click to see all.
 */

import { memo, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type {
  NipypeNodeStatus,
  NipypeStatusCounts,
  NipypeStatusBlock,
} from '../../api/types'

const STATUS_COLOR: Record<string, string> = {
  running: '#00e5ff',
  ok: '#00e676',
  failed: '#ff1744',
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
  cursor: 'pointer',
  userSelect: 'none',
}

const countPill = (color: string): CSSProperties => ({
  padding: '1px 6px',
  borderRadius: 8,
  background: `${color}22`,
  color,
  border: `1px solid ${color}55`,
  fontSize: 9,
  fontWeight: 700,
})

const groupHeader: CSSProperties = {
  marginTop: 6,
  marginBottom: 2,
  fontSize: 9,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  color: 'var(--text-secondary)',
  fontWeight: 700,
}

const pillRow: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 4,
}

const nodePill = (color: string): CSSProperties => ({
  padding: '2px 6px',
  borderRadius: 8,
  background: `${color}1f`,
  color,
  border: `1px solid ${color}55`,
  fontSize: 9,
  fontWeight: 600,
  cursor: 'default',
  whiteSpace: 'nowrap',
})


function _summarize(counts: NipypeStatusCounts): React.ReactNode {
  const items: { color: string; label: string }[] = []
  if (counts.running) items.push({ color: STATUS_COLOR.running, label: `${counts.running} running` })
  if (counts.ok) items.push({ color: STATUS_COLOR.ok, label: `${counts.ok} done` })
  if (counts.failed) items.push({ color: STATUS_COLOR.failed, label: `${counts.failed} failed` })
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


function _topGroup(workflow: string): string {
  // First two dotted segments — keeps fmriprep_wf groups (anatomical /
  // functional / fieldmap) visible without dragging in 8-deep paths.
  const parts = workflow.split('.')
  if (parts.length === 0) return '(root)'
  if (parts.length === 1) return parts[0]
  return parts.slice(0, 2).join('.')
}


interface Props {
  block: NipypeStatusBlock
  onNodeClick?: (node: NipypeNodeStatus) => void
}

function InnerNodesStripInner({ block, onNodeClick }: Props) {
  const [expanded, setExpanded] = useState(false)
  const grouped = useMemo(() => {
    const groups = new Map<string, NipypeNodeStatus[]>()
    for (const n of block.recent_nodes) {
      const key = _topGroup(n.workflow || '')
      const arr = groups.get(key)
      if (arr) arr.push(n)
      else groups.set(key, [n])
    }
    return groups
  }, [block.recent_nodes])

  const total = block.counts.total_seen
  return (
    <div style={containerStyle}>
      <div style={headerStyle} onClick={() => setExpanded((v) => !v)}>
        <span style={{ color: 'var(--text-secondary)' }}>
          {expanded ? '▼' : '▶'}
        </span>
        <span style={{ fontWeight: 700 }}>nipype nodes</span>
        {_summarize(block.counts)}
        {total > 0 && (
          <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)' }}>
            {total} seen
          </span>
        )}
      </div>
      {expanded && grouped.size > 0 && (
        <div style={{ marginTop: 4 }}>
          {Array.from(grouped.entries()).map(([group, nodes]) => (
            <div key={group}>
              <div style={groupHeader}>{group}</div>
              <div style={pillRow}>
                {nodes.map((n) => {
                  const color = STATUS_COLOR[n.status] ?? 'var(--text-secondary)'
                  const elapsed = n.elapsed > 0
                    ? ` · ${n.elapsed.toFixed(1)}s`
                    : ''
                  return (
                    <span
                      key={n.node}
                      style={{
                        ...nodePill(color),
                        cursor: onNodeClick ? 'pointer' : 'default',
                      }}
                      title={`${n.node} — ${n.status}${elapsed}`}
                      onClick={onNodeClick ? () => onNodeClick(n) : undefined}
                    >
                      {n.leaf}{elapsed}
                    </span>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


export const InnerNodesStrip = memo(InnerNodesStripInner)
