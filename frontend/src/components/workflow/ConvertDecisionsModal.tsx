/** Drill-in from a finished convert stage: what the heuristic did with each series. */
import type { CSSProperties } from 'react'

import { ConvertDecisionTable } from '../convert/ConvertDecisionTable'

interface Props {
  bidsDir: string
  subject: string
  onClose: () => void
}

export function ConvertDecisionsModal({ bidsDir, subject, onClose }: Props) {
  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div>
            <div style={titleStyle}>DICOM → BIDS decisions</div>
            <div style={subtitleStyle}>
              sub-{subject} · <span style={{ fontFamily: 'monospace' }}>{bidsDir}</span>
            </div>
          </div>
          <button style={closeStyle} onClick={onClose}>Close</button>
        </div>
        <div style={bodyStyle}>
          <ConvertDecisionTable bidsDir={bidsDir} subject={subject} />
        </div>
      </div>
    </div>
  )
}

const overlayStyle: CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
}
const modalStyle: CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 8, width: 'min(1100px, 94vw)', maxHeight: '88vh',
  display: 'flex', flexDirection: 'column', overflow: 'hidden',
}
const headerStyle: CSSProperties = {
  display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
  gap: 12, padding: '14px 18px', borderBottom: '1px solid var(--border)',
}
const titleStyle: CSSProperties = {
  fontSize: 14, fontWeight: 700, color: 'var(--text-primary)',
}
const subtitleStyle: CSSProperties = {
  fontSize: 11, color: 'var(--text-secondary)', marginTop: 3,
}
const closeStyle: CSSProperties = {
  background: 'var(--bg-card)', color: 'var(--text-secondary)',
  border: '1px solid var(--border)', borderRadius: 4,
  padding: '4px 12px', cursor: 'pointer', fontSize: 11,
}
const bodyStyle: CSSProperties = {
  padding: '4px 18px 18px', overflow: 'auto',
}
