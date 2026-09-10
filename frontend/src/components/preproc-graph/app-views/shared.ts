import type { CSSProperties } from 'react'

export const fill: CSSProperties = { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }
export const pad: CSSProperties = { padding: 12, overflow: 'auto', fontSize: 12 }
export const muted: CSSProperties = { color: 'var(--text-secondary)', fontSize: 12, padding: 12 }
export const h: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', margin: '10px 0 6px' }
export const table: CSSProperties = { borderCollapse: 'collapse', fontSize: 12, width: '100%' }
export const th: CSSProperties = { textAlign: 'left', padding: '4px 8px', color: 'var(--text-secondary)', fontWeight: 600, borderBottom: '1px solid var(--border)', fontSize: 10, textTransform: 'uppercase' }
export const td: CSSProperties = { padding: '4px 8px', borderBottom: '1px solid var(--border)', verticalAlign: 'top', fontFamily: 'monospace', fontSize: 11, wordBreak: 'break-all' }
export const pre: CSSProperties = { flex: 1, minHeight: 0, overflow: 'auto', fontSize: 10, background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: 8, margin: 0, whiteSpace: 'pre-wrap' }
