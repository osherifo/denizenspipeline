/** Full-screen modal wrapping the StructuralQCPanel for a given subject.
 *
 * Used from the Workflows view: when a workflow's preproc stage is
 * `done`, the user clicks "Structural QC" on the Preproc block and
 * this modal opens with the same panel that lives under the
 * Preproc-manager manifest detail view.
 */

import type { CSSProperties } from 'react'
import { StructuralQCPanel } from '../preproc/StructuralQCPanel'

const backdrop: CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.7)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 999,
}

const card: CSSProperties = {
  width: '92vw',
  maxHeight: '92vh',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  display: 'flex',
  flexDirection: 'column',
  padding: 12,
  overflowY: 'auto',
}

const header: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  marginBottom: 8,
}

const closeBtn: CSSProperties = {
  padding: '4px 12px',
  fontSize: 12,
  border: '1px solid var(--border)',
  borderRadius: 4,
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
  marginLeft: 'auto',
}


interface Props {
  subject: string
  onClose: () => void
}


export function StructuralQCModal({ subject, onClose }: Props) {
  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Structural QC</div>
          <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            sub-{subject}
          </code>
          <button style={closeBtn} onClick={onClose}>Close</button>
        </div>
        <StructuralQCPanel subject={subject} />
      </div>
    </div>
  )
}
