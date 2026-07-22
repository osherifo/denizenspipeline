/** Collapsible stage card — the top-level unit of the Analysis Composer.
 *
 * A stage maps 1:1 to a section of the analysis pipeline schema
 * (stimuli, responses, features, prepare, model, analyze, report).
 * The card has three states for the badge:
 *  - "filled": user picked at least one module
 *  - "empty":  no module yet (calls the user to action)
 *  - "error":  validate() returned an error keyed to this stage
 */

import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'

export type StageStatus = 'filled' | 'empty' | 'error'

interface StageCardProps {
  num: number
  name: string
  /** Tier-1 colour used in the badge + accent border. */
  color: string
  /** Display state — determines badge colour + glow. */
  status: StageStatus
  /** One-line summary shown when the card is collapsed. */
  summary?: string
  /** When provided, rendered next to the title (e.g. count "(3)"). */
  badge?: string
  /** Validation message shown below the header when status==='error'. */
  errorMessage?: string
  /** Stable id so the ghost graph can scroll to this card. */
  anchorId?: string
  /** Initially collapsed? Defaults to false. */
  initiallyCollapsed?: boolean
  children: ReactNode
}

const cardStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  marginBottom: 14,
  overflow: 'hidden',
  scrollMarginTop: 80,
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '14px 18px',
  cursor: 'pointer',
  userSelect: 'none',
}

const numStyle = (color: string, status: StageStatus): CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 28,
  height: 28,
  borderRadius: '50%',
  backgroundColor:
    status === 'error' ? 'var(--accent-red, #ef5350)' :
    status === 'filled' ? color :
    'var(--bg-input)',
  color: status === 'empty' ? 'var(--text-secondary)' : 'var(--on-accent)',
  fontSize: 13,
  fontWeight: 800,
  flexShrink: 0,
  boxShadow: status === 'filled' ? `0 0 8px ${color}40` : 'none',
})

const nameStyle = (color: string, status: StageStatus): CSSProperties => ({
  fontSize: 14,
  fontWeight: 700,
  color: status === 'filled' ? color : 'var(--text-primary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  flexShrink: 0,
})

const summaryStyle: CSSProperties = {
  flex: 1,
  fontSize: 12,
  color: 'var(--text-secondary)',
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}

const badgeStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  padding: '2px 8px',
  borderRadius: 10,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}

const chevronStyle = (open: boolean): CSSProperties => ({
  transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
  transition: 'transform 0.15s ease',
  color: 'var(--text-secondary)',
  fontSize: 14,
  width: 14,
  flexShrink: 0,
})

const bodyStyle: CSSProperties = {
  padding: '4px 18px 18px 18px',
  borderTop: '1px solid var(--border)',
}

const errorBanner: CSSProperties = {
  margin: '0 18px 12px',
  padding: '8px 12px',
  fontSize: 12,
  color: 'var(--accent-red, #ef5350)',
  backgroundColor: 'rgba(239, 83, 80, 0.08)',
  border: '1px solid var(--accent-red, #ef5350)',
  borderRadius: 6,
}

export function StageCard({
  num,
  name,
  color,
  status,
  summary,
  badge,
  errorMessage,
  anchorId,
  initiallyCollapsed = false,
  children,
}: StageCardProps) {
  const [open, setOpen] = useState(!initiallyCollapsed)

  return (
    <div id={anchorId} style={cardStyle}>
      <div style={headerStyle} onClick={() => setOpen((v) => !v)}>
        <span style={chevronStyle(open)}>▶</span>
        <span style={numStyle(color, status)}>{num}</span>
        <span style={nameStyle(color, status)}>{name}</span>
        {badge && <span style={badgeStyle}>{badge}</span>}
        {summary && <span style={summaryStyle}>{summary}</span>}
      </div>
      {status === 'error' && errorMessage && (
        <div style={errorBanner}>{errorMessage}</div>
      )}
      {open && <div style={bodyStyle}>{children}</div>}
    </div>
  )
}
