/** Draggable node palette — add new nodes to the graph. */
import type { CSSProperties } from 'react'
import { useGraphStore, type StageType } from '../../stores/graph-store'

const PALETTE_ITEMS: { type: StageType; label: string; icon: string }[] = [
  { type: 'source', label: 'Source', icon: '\u{1F4C1}' },
  { type: 'convert', label: 'Convert', icon: '\u{1F504}' },
  { type: 'preproc', label: 'Preproc', icon: '\u{2699}' },
  { type: 'autoflatten', label: 'Autoflatten', icon: '\u{1F9E0}' },
  { type: 'response_loader', label: 'Responses', icon: '\u{1F4E5}' },
  { type: 'features', label: 'Features', icon: '\u{2728}' },
  { type: 'preprocess', label: 'Preprocess', icon: '\u{1F527}' },
  { type: 'model', label: 'Model', icon: '\u{1F4CA}' },
  { type: 'report', label: 'Report', icon: '\u{1F4DD}' },
]

const container: CSSProperties = {
  display: 'flex',
  gap: 6,
  flexWrap: 'wrap',
}

const chip: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '5px 10px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 5,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  transition: 'border-color 0.12s',
}

export function NodePalette() {
  const addNode = useGraphStore((s) => s.addNode)

  return (
    <div style={container}>
      {PALETTE_ITEMS.map((item) => (
        <button
          key={item.type}
          style={chip}
          onClick={() => addNode(item.type, item.label)}
          title={`Add ${item.label} node`}
        >
          <span>{item.icon}</span>
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  )
}
