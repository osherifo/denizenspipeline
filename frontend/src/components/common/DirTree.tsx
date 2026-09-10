/** Read-only, lazily expanded directory tree served by /api/fs/list.
 *  Shows structure only — nothing opens. Used to inspect a generated BIDS dataset. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { fetchFsExists, fetchFsListing, type FsEntry } from '../../api/fs'

const row: CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, padding: '2px 0', fontFamily: 'monospace' }
const muted: CSSProperties = { color: 'var(--text-secondary)' }

function fmtSize(n?: number): string {
  if (n === undefined) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function Node({ entry, depth, initiallyOpen = false }: { entry: FsEntry; depth: number; initiallyOpen?: boolean }) {
  const [open, setOpen] = useState(initiallyOpen)
  const [children, setChildren] = useState<FsEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || children !== null || !entry.is_dir) return
    let cancelled = false
    fetchFsListing(entry.path, true)
      .then((l) => { if (!cancelled) setChildren(l.entries) })
      .catch((e) => { if (!cancelled) setError((e as Error).message) })
    return () => { cancelled = true }
  }, [open, children, entry])

  const pad = { paddingLeft: depth * 16 }
  if (!entry.is_dir) {
    return (
      <div style={{ ...row, ...pad }} title={entry.path}>
        <span style={{ width: 14, textAlign: 'center', ...muted }}>·</span>
        <span>{entry.name}</span>
        <span style={{ ...muted, fontSize: 10 }}>{fmtSize(entry.size)}</span>
      </div>
    )
  }
  return (
    <div>
      <div style={{ ...row, ...pad, cursor: 'pointer' }} onClick={() => setOpen(!open)} title={entry.path}>
        <span style={{ width: 14, textAlign: 'center', ...muted }}>{open ? '▾' : '▸'}</span>
        <span style={{ fontWeight: 600 }}>{entry.name}/</span>
        {children && <span style={{ ...muted, fontSize: 10 }}>{children.length} item{children.length === 1 ? '' : 's'}</span>}
      </div>
      {open && error && <div style={{ ...row, paddingLeft: (depth + 1) * 16, color: '#ef4444' }}>{error}</div>}
      {open && children && children.map((c) => <Node key={c.path} entry={c} depth={depth + 1} />)}
      {open && children && children.length === 0 && <div style={{ ...row, paddingLeft: (depth + 1) * 16, ...muted }}>empty</div>}
    </div>
  )
}

interface Props {
  path: string
  title?: string
  maxHeight?: number
}

export function DirTree({ path, title, maxHeight = 360 }: Props) {
  const [exists, setExists] = useState<boolean | null>(null)
  useEffect(() => {
    let cancelled = false
    setExists(null)
    fetchFsExists(path).then((r) => { if (!cancelled) setExists(r.exists && r.is_dir) }).catch(() => { if (!cancelled) setExists(false) })
    return () => { cancelled = true }
  }, [path])

  if (exists === null) return <div style={{ ...muted, fontSize: 12 }}>Checking {path}…</div>
  if (!exists) {
    return (
      <div style={{ ...muted, fontSize: 12 }}>
        {title ? `${title}: ` : ''}<code>{path}</code> no longer exists, or is not visible to the server.
      </div>
    )
  }
  const root: FsEntry = { name: path.replace(/\/+$/, '').split('/').pop() || path, path, is_dir: true }
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 6, background: 'var(--bg-card)', padding: '6px 8px', maxHeight, overflow: 'auto' }}>
      <div style={{ ...muted, fontSize: 10, marginBottom: 4 }}>{path}</div>
      <Node entry={root} depth={0} initiallyOpen />
    </div>
  )
}
