/** Custom ReactFlow node for a pipeline node: kind tag, one handle per port,
 *  status colour when rendering a run, checkpoint badge. */
import { memo } from 'react'
import type { CSSProperties } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { useThemeStore } from '../../stores/theme-store'
import { identityColor, nodeColors } from '../../utils/status-colors'
import { HEADER_H, ROW_H } from './layout'
import type { PreprocNodeKind } from '../../api/types'

export const KIND_COLORS: Record<PreprocNodeKind, string> = {
  source: '#f59e0b',
  interface: '#10b981',
  container_app: '#3b82f6',
  composite: '#a855f7',
}

export const KIND_LABELS: Record<PreprocNodeKind, string> = {
  source: 'source',
  interface: 'node',
  container_app: 'app',
  composite: 'workflow',
}

export interface PipelineNodeCardData {
  label: string
  nodeType: string
  kind: PreprocNodeKind
  inputs: string[]
  outputs: string[]
  iterating?: boolean
  isBackend?: boolean
  /** Run overlay */
  status?: 'pending' | 'running' | 'ok' | 'failed' | 'cached' | 'skipped' | null
  durationS?: number | null
  checkpointVerdict?: 'ok' | 'suspicious' | 'bad' | 'unknown' | null
  checkpointCount?: number
  [key: string]: unknown
}

const VERDICT_COLORS: Record<string, string> = {
  ok: '#10b981', suspicious: '#f59e0b', bad: '#ef4444', unknown: '#9ca3af',
}

function statusColorOf(status: PipelineNodeCardData['status'], mode: 'light' | 'dark'): string | null {
  if (!status || status === 'pending') return null
  const map: Record<string, string> = { running: 'running', ok: 'done', cached: 'done', failed: 'failed', skipped: 'pending' }
  return nodeColors(mode, map[status] ?? 'pending').border
}

function PipelineNodeCardInner({ data, selected }: NodeProps & { data: PipelineNodeCardData }) {
  const mode = useThemeStore((s) => s.mode)
  const light = mode === 'light'
  const base = identityColor(KIND_COLORS[data.kind] ?? '#10b981', mode)
  const statusColor = statusColorOf(data.status, mode)
  const color = statusColor ?? base
  const inputs = data.inputs ?? []
  const outputs = data.outputs ?? []
  const rows = Math.max(inputs.length, outputs.length, 1)
  const height = HEADER_H + rows * ROW_H + 10
  const running = data.status === 'running'

  const container: CSSProperties = {
    background: light ? `${base}14` : `${base}1c`,
    border: selected ? `2px solid ${color}` : `1px solid ${light ? color : `${color}aa`}`,
    borderRadius: 8,
    width: 210,
    height,
    position: 'relative',
    color: 'var(--text-primary)',
    fontSize: 12,
    boxShadow: selected ? `0 0 10px ${color}55` : running ? `0 0 12px ${color}66` : undefined,
    animation: running ? 'pulse 1.6s ease-in-out infinite' : undefined,
  }
  const handleStyle = (c: string): CSSProperties => ({
    width: 10, height: 10, backgroundColor: c, border: '2px solid var(--bg-card)',
  })

  return (
    <div style={container} title={data.nodeType}>
      <div style={{ padding: '6px 10px', borderBottom: `1px solid ${color}55`, display: 'flex', alignItems: 'center', gap: 6, height: HEADER_H, boxSizing: 'border-box' }}>
        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color: base, opacity: 0.9 }}>
          {KIND_LABELS[data.kind] ?? data.kind}
        </span>
        <span style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{data.label}</span>
        {data.iterating && <span title="iterates over a list" style={{ fontSize: 10, color: 'var(--text-secondary)' }}>×N</span>}
        {data.isBackend && <span title="manifest backend node" style={{ fontSize: 10, color: base }}>★</span>}
        {data.status === 'cached' && <span title="cache hit" style={{ fontSize: 10, color: 'var(--text-secondary)' }}>⟲</span>}
        {data.checkpointVerdict && (
          <span
            title={`${data.checkpointCount ?? 0} checkpoint(s), worst: ${data.checkpointVerdict}`}
            style={{ width: 9, height: 9, borderRadius: 999, background: VERDICT_COLORS[data.checkpointVerdict], display: 'inline-block' }}
          />
        )}
      </div>
      {inputs.map((p, i) => (
        <div key={`in-${p}`} style={{ position: 'absolute', left: 0, top: HEADER_H + 4 + i * ROW_H + ROW_H / 2 }}>
          <Handle type="target" position={Position.Left} id={p} style={{ ...handleStyle(color), top: 0 }} />
          <span style={{ position: 'absolute', left: 14, top: 0, transform: 'translateY(-50%)', fontSize: 9, color: 'var(--text-secondary)', whiteSpace: 'nowrap', pointerEvents: 'none' }}>{p}</span>
        </div>
      ))}
      {outputs.map((p, i) => (
        <div key={`out-${p}`} style={{ position: 'absolute', right: 0, top: HEADER_H + 4 + i * ROW_H + ROW_H / 2 }}>
          <Handle type="source" position={Position.Right} id={p} style={{ ...handleStyle(color), top: 0 }} />
          <span style={{ position: 'absolute', right: 14, top: 0, transform: 'translateY(-50%)', fontSize: 9, color: 'var(--text-secondary)', whiteSpace: 'nowrap', pointerEvents: 'none' }}>{p}</span>
        </div>
      ))}
      {typeof data.durationS === 'number' && data.durationS > 0 && (
        <span style={{ position: 'absolute', right: 8, bottom: 2, fontSize: 9, color: 'var(--text-secondary)' }}>{data.durationS < 60 ? `${data.durationS.toFixed(1)}s` : `${Math.round(data.durationS / 60)}m`}</span>
      )}
    </div>
  )
}

export const PipelineNodeCard = memo(PipelineNodeCardInner)
