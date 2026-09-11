/** Custom ReactFlow node shared by every graph editor: a tag, one handle per port
 *  (coloured by port type when the caller gives a colour), run status and badges. */
import { memo } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { useThemeStore } from '../../stores/theme-store'
import { identityColor, nodeColors, runningNodeStyle } from '../../utils/status-colors'
import { HEADER_H, NODE_WIDTH, ROW_H } from './layout'

export type GraphNodeStatus = 'pending' | 'running' | 'ok' | 'failed' | 'cached' | 'skipped' | 'warning' | null

export interface NodeRunStatus {
  status: GraphNodeStatus
  durationS?: number | null
  error?: string
}

export interface GraphPort {
  name: string
  /** Handle colour, e.g. the port type's colour; defaults to the node's colour. */
  color?: string
  title?: string
}

export interface GraphBadge {
  key: string
  content: ReactNode
  title?: string
  color?: string
}

export interface GraphNodeCardData {
  label: string
  /** Tooltip for the whole card, e.g. the node type. */
  title?: string
  tag: string
  tagColor: string
  inputs: GraphPort[]
  outputs: GraphPort[]
  status?: GraphNodeStatus
  durationS?: number | null
  badges?: GraphBadge[]
  [key: string]: unknown
}

const STATUS_KEY: Record<string, string> = {
  running: 'running', ok: 'done', cached: 'done', failed: 'failed', skipped: 'pending', warning: 'warning',
}

function GraphNodeCardInner({ data, selected }: NodeProps & { data: GraphNodeCardData }) {
  const mode = useThemeStore((s) => s.mode)
  const light = mode === 'light'
  const base = identityColor(data.tagColor, mode)
  const status = data.status && data.status !== 'pending' ? nodeColors(mode, STATUS_KEY[data.status] ?? 'pending') : null
  // The plain status hex: nodeColors().border already carries an alpha suffix in dark mode.
  const color = status?.color ?? base
  const inputs = data.inputs ?? []
  const outputs = data.outputs ?? []
  const rows = Math.max(inputs.length, outputs.length, 1)
  const height = HEADER_H + rows * ROW_H + 10

  const container: CSSProperties = {
    background: light ? `${base}14` : `${base}1c`,
    border: selected ? `2px solid ${color}` : `1px solid ${light ? color : `${color}aa`}`,
    borderRadius: 8,
    width: NODE_WIDTH,
    height,
    position: 'relative',
    color: 'var(--text-primary)',
    fontSize: 12,
    boxShadow: selected ? `0 0 10px ${color}55` : undefined,
    ...(status ? runningNodeStyle(status) : {}),
  }
  const handleStyle = (c: string): CSSProperties => ({
    width: 10, height: 10, backgroundColor: c, border: '2px solid var(--bg-card)',
  })
  const label: CSSProperties = {
    position: 'absolute', top: 0, transform: 'translateY(-50%)', fontSize: 9, color: 'var(--text-secondary)',
    whiteSpace: 'nowrap', pointerEvents: 'none',
  }

  return (
    <div style={container} title={data.title}>
      <div style={{ padding: '6px 10px', borderBottom: `1px solid ${color}55`, display: 'flex', alignItems: 'center', gap: 6, height: HEADER_H, boxSizing: 'border-box' }}>
        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color: base, opacity: 0.9 }}>
          {data.tag}
        </span>
        <span style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{data.label}</span>
        {(data.badges ?? []).map((b) => (
          <span key={b.key} title={b.title} style={{ fontSize: 10, color: b.color ?? 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center' }}>
            {b.content}
          </span>
        ))}
      </div>
      {inputs.map((p, i) => (
        <div key={`in-${p.name}`} style={{ position: 'absolute', left: 0, top: HEADER_H + 4 + i * ROW_H + ROW_H / 2 }}>
          <Handle type="target" position={Position.Left} id={p.name} title={p.title} style={{ ...handleStyle(p.color ?? color), top: 0 }} />
          <span style={{ ...label, left: 14 }}>{p.name}</span>
        </div>
      ))}
      {outputs.map((p, i) => (
        <div key={`out-${p.name}`} style={{ position: 'absolute', right: 0, top: HEADER_H + 4 + i * ROW_H + ROW_H / 2 }}>
          <Handle type="source" position={Position.Right} id={p.name} title={p.title} style={{ ...handleStyle(p.color ?? color), top: 0 }} />
          <span style={{ ...label, right: 14 }}>{p.name}</span>
        </div>
      ))}
      {typeof data.durationS === 'number' && data.durationS > 0 && (
        <span style={{ position: 'absolute', right: 8, bottom: 2, fontSize: 9, color: 'var(--text-secondary)' }}>
          {data.durationS < 60 ? `${data.durationS.toFixed(1)}s` : `${Math.round(data.durationS / 60)}m`}
        </span>
      )}
    </div>
  )
}

export const GraphNodeCard = memo(GraphNodeCardInner)
