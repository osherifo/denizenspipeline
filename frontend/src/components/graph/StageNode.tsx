/** Custom React Flow node for pipeline stages. */
import { memo } from 'react'
import type { CSSProperties } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { StageNodeData, StageType } from '../../stores/graph-store'

// ── Stage metadata ──────────────────────────────────────────────────────

interface StageMeta {
  color: string
  icon: string
  inputs: { id: string; label: string }[]
  outputs: { id: string; label: string }[]
}

const STAGE_META: Record<StageType, StageMeta> = {
  source: {
    color: '#6b7280',
    icon: '\u{1F4C1}',
    inputs: [],
    outputs: [{ id: 'output-dicom', label: 'DICOM' }],
  },
  convert: {
    color: '#3b82f6',
    icon: '\u{1F504}',
    inputs: [{ id: 'input-dicom', label: 'DICOM' }],
    outputs: [{ id: 'output-bids', label: 'BIDS' }],
  },
  preproc: {
    color: '#10b981',
    icon: '\u{2699}',
    inputs: [{ id: 'input-bids', label: 'BIDS' }],
    outputs: [
      { id: 'output-manifest', label: 'Manifest' },
      { id: 'output-freesurfer', label: 'FreeSurfer' },
    ],
  },
  autoflatten: {
    color: '#14b8a6',
    icon: '\u{1F9E0}',
    inputs: [{ id: 'input-freesurfer', label: 'FreeSurfer' }],
    outputs: [{ id: 'output-surface', label: 'Surface' }],
  },
  response_loader: {
    color: '#8b5cf6',
    icon: '\u{1F4E5}',
    inputs: [{ id: 'input-manifest', label: 'Manifest' }],
    outputs: [{ id: 'output-responses', label: 'Responses' }],
  },
  features: {
    color: '#eab308',
    icon: '\u{2728}',
    inputs: [],
    outputs: [{ id: 'output-features', label: 'Features' }],
  },
  preprocess: {
    color: '#f97316',
    icon: '\u{1F527}',
    inputs: [
      { id: 'input-responses', label: 'Responses' },
      { id: 'input-features', label: 'Features' },
    ],
    outputs: [{ id: 'output-prepared', label: 'Prepared' }],
  },
  model: {
    color: '#ef4444',
    icon: '\u{1F4CA}',
    inputs: [
      { id: 'input-prepared', label: 'Prepared' },
      { id: 'input-surface', label: 'Surface' },
    ],
    outputs: [{ id: 'output-results', label: 'Results' }],
  },
  report: {
    color: '#ec4899',
    icon: '\u{1F4DD}',
    inputs: [{ id: 'input-results', label: 'Results' }],
    outputs: [],
  },
}

// ── Status dot ──────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  pending: '#6b7280',
  running: '#3b82f6',
  done: '#10b981',
  error: '#ef4444',
  skipped: '#4b5563',
}

// ── Styles ──────────────────────────────────────────────────────────────

const nodeBase: CSSProperties = {
  borderRadius: 8,
  padding: '10px 14px',
  minWidth: 190,
  maxWidth: 240,
  fontSize: 11,
  fontFamily: 'inherit',
  cursor: 'pointer',
  transition: 'box-shadow 0.15s ease',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  marginBottom: 6,
}

const labelStyle: CSSProperties = {
  fontWeight: 700,
  fontSize: 12,
  flex: 1,
}

const dotStyle = (color: string): CSSProperties => ({
  width: 8,
  height: 8,
  borderRadius: '50%',
  backgroundColor: color,
  flexShrink: 0,
})

const summaryLine: CSSProperties = {
  opacity: 0.7,
  lineHeight: 1.5,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}

const handleStyle = (color: string): CSSProperties => ({
  width: 10,
  height: 10,
  backgroundColor: color,
  border: '2px solid #1a1a2e',
  borderRadius: '50%',
})

// ── Component ───────────────────────────────────────────────────────────

function StageNodeInner({ data, selected }: NodeProps & { data: StageNodeData }) {
  const meta = STAGE_META[data.stageType]
  const statusColor = STATUS_COLORS[data.status] || STATUS_COLORS.pending

  const style: CSSProperties = {
    ...nodeBase,
    backgroundColor: '#1a1a2e',
    border: selected
      ? `2px solid ${meta.color}`
      : '1px solid #2a2a4a',
    boxShadow: selected
      ? `0 0 12px ${meta.color}40`
      : 'none',
  }

  return (
    <div style={style}>
      {/* Input handles */}
      {meta.inputs.map((h, i) => (
        <Handle
          key={h.id}
          type="target"
          position={Position.Top}
          id={h.id}
          style={{
            ...handleStyle(meta.color),
            left: meta.inputs.length === 1
              ? '50%'
              : `${((i + 1) / (meta.inputs.length + 1)) * 100}%`,
          }}
        />
      ))}

      {/* Header */}
      <div style={headerStyle}>
        <span>{meta.icon}</span>
        <span style={{ ...labelStyle, color: meta.color }}>{data.label}</span>
        <span style={dotStyle(statusColor)} title={data.status} />
      </div>

      {/* Summary lines */}
      {data.summary.slice(0, 3).map((line, i) => (
        <div key={i} style={summaryLine}>{line}</div>
      ))}

      {/* Output handles */}
      {meta.outputs.map((h, i) => (
        <Handle
          key={h.id}
          type="source"
          position={Position.Bottom}
          id={h.id}
          style={{
            ...handleStyle(meta.color),
            left: meta.outputs.length === 1
              ? '50%'
              : `${((i + 1) / (meta.outputs.length + 1)) * 100}%`,
          }}
        />
      ))}
    </div>
  )
}

export const StageNode = memo(StageNodeInner)

export const nodeTypes = { stage: StageNode }
