/** Shared styles for result viewers. */
import type { CSSProperties } from 'react'

export const viewerCard: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  overflow: 'hidden',
}

export const viewerHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '8px 12px',
  borderBottom: '1px solid var(--border)',
  backgroundColor: 'var(--bg-card)',
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

export const viewerHeaderActions: CSSProperties = {
  display: 'flex',
  gap: 12,
  alignItems: 'center',
}

export const actionLink: CSSProperties = {
  fontSize: 10,
  color: 'var(--accent-cyan)',
  textDecoration: 'none',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

export const viewerBody: CSSProperties = {
  padding: '12px 14px',
}

export const subtleText: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  fontFamily: 'monospace',
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}
