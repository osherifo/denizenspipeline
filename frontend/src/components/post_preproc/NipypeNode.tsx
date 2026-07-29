/** Custom XYFlow node for the post-preproc builder.
 *
 * Renders one labelled handle per declared INPUT (left) and OUTPUT
 * (right), so wires land unambiguously on the right port.
 */

import { memo } from 'react'
import type { CSSProperties } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { useThemeStore } from '../../stores/theme-store'
import { identityColor } from '../../utils/status-colors'

// Matches the preproc stage colour in WorkflowGraph. Light mode darkens it
// (see identityColor) — the neon original is ~2.5:1 on a white card.
const BASE_COLOR = '#10b981'

export interface NipypeNodeData {
  label: string
  nodeType: string
  inputs: string[]
  outputs: string[]
  iterating?: boolean
}

const handleStyle = (color: string): CSSProperties => ({
  width: 10,
  height: 10,
  backgroundColor: color,
  border: '2px solid var(--bg-card)',
})

const handleLabel = (side: 'left' | 'right'): CSSProperties => ({
  position: 'absolute',
  fontSize: 9,
  color: 'var(--text-secondary)',
  pointerEvents: 'none',
  whiteSpace: 'nowrap',
  [side === 'left' ? 'left' : 'right']: 14,
  top: -1,
  transform: 'translateY(-50%)',
})

function NipypeNodeInner({ data, selected }: NodeProps & { data: NipypeNodeData }) {
  const mode = useThemeStore((s) => s.mode)
  const light = mode === 'light'
  const COLOR = identityColor(BASE_COLOR, mode)
  const inputs = data.inputs ?? []
  const outputs = data.outputs ?? []
  const rows = Math.max(inputs.length, outputs.length, 1)
  const rowHeight = 22
  const headerHeight = 30
  const height = headerHeight + rows * rowHeight + 6

  const containerStyle: CSSProperties = {
    background: light ? `${COLOR}1f` : `${COLOR}22`,
    // A 67%-alpha border vanishes on white; use the solid colour in light mode.
    border: selected ? `2px solid ${COLOR}` : `1px solid ${light ? COLOR : `${COLOR}aa`}`,
    borderRadius: 6,
    minWidth: 170,
    color: 'var(--text-primary)',
    fontSize: 12,
    fontWeight: 600,
    position: 'relative',
    height,
    boxShadow: selected ? `0 0 10px ${COLOR}55` : undefined,
  }

  return (
    <div style={containerStyle}>
      <div
        style={{
          padding: '6px 10px',
          borderBottom: `1px solid ${COLOR}55`,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span style={{ color: COLOR }}>{data.nodeType}</span>
        <span style={{ flex: 1 }} />
        {data.iterating && (
          <span
            style={{
              fontSize: 9,
              padding: '1px 5px',
              borderRadius: 8,
              background: light ? 'rgba(143, 90, 0, 0.14)' : '#ffd60022',
              color: 'var(--accent-yellow)',
              border: '1px solid #ffd60055',
            }}
            title="Iterates over a list"
          >
            map
          </span>
        )}
      </div>

      {/* input handles, stacked */}
      {inputs.map((name, i) => {
        const top = headerHeight + i * rowHeight + rowHeight / 2
        return (
          <div key={`in-${name}`}>
            <Handle
              type="target"
              position={Position.Left}
              id={name}
              style={{ ...handleStyle(COLOR), top }}
            />
            <span style={{ ...handleLabel('left'), top }}>{name}</span>
          </div>
        )
      })}

      {/* output handles, stacked */}
      {outputs.map((name, i) => {
        const top = headerHeight + i * rowHeight + rowHeight / 2
        return (
          <div key={`out-${name}`}>
            <Handle
              type="source"
              position={Position.Right}
              id={name}
              style={{ ...handleStyle(COLOR), top }}
            />
            <span style={{ ...handleLabel('right'), top }}>{name}</span>
          </div>
        )
      })}
    </div>
  )
}

export const NipypeNode = memo(NipypeNodeInner)
