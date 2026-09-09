/** A text field with a Browse button that opens a server-side directory picker.
 *
 *  The picker lists directories as the *server* sees them (inside Docker that is
 *  the container's view), restricted to the data roots, so whatever you pick is a
 *  path the server can actually open. Typed paths stay free-form; a small hint
 *  says when the server cannot see one.
 */
import React, { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { createFsDir, fetchFsExists, fetchFsListing, fetchFsRoots, type FsEntry, type FsRoot } from '../../api/fs'

const backdrop: CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center' }
const card: CSSProperties = { width: 'min(760px, 94vw)', height: 'min(560px, 88vh)', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, display: 'flex', flexDirection: 'column', overflow: 'hidden', fontSize: 12 }
const btn: CSSProperties = { padding: '5px 10px', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-primary)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11, whiteSpace: 'nowrap' }
const chip = (active: boolean): CSSProperties => ({ ...btn, borderColor: active ? 'var(--accent-cyan)' : 'var(--border)', color: active ? 'var(--accent-cyan)' : 'var(--text-primary)' })
const row = (selected: boolean): CSSProperties => ({ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 8px', cursor: 'pointer', borderRadius: 4, background: selected ? 'rgba(0,229,255,0.10)' : 'transparent' })

function fmtSize(n?: number): string {
  if (n === undefined) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

interface PickerProps {
  initialPath?: string
  mode?: 'dir' | 'file'
  onPick: (path: string) => void
  onClose: () => void
}

export function PathPickerModal({ initialPath, mode = 'dir', onPick, onClose }: PickerProps) {
  const [roots, setRoots] = useState<FsRoot[]>([])
  const [path, setPath] = useState<string | null>(null)
  const [parent, setParent] = useState<string | null>(null)
  const [entries, setEntries] = useState<FsEntry[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [extraEnv, setExtraEnv] = useState('FMRIFLOW_BROWSE_ROOTS')

  const open = async (p: string) => {
    setError(null)
    try {
      const l = await fetchFsListing(p, mode === 'file')
      setPath(l.path); setParent(l.parent); setEntries(l.entries); setSelected(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    let cancelled = false
    fetchFsRoots().then(async (r) => {
      if (cancelled) return
      setRoots(r.roots); setExtraEnv(r.extra_roots_env)
      const start = initialPath && r.roots.some((x) => initialPath.startsWith(x.path)) ? initialPath : r.roots[0]?.path
      if (start) await open(start)
    }).catch((e) => setError((e as Error).message))
    return () => { cancelled = true }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const pickValue = selected ?? (mode === 'dir' ? path : null)

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: 10, borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
          <b>Choose a {mode === 'dir' ? 'directory' : 'file'}</b>
          <span style={{ flex: 1 }} />
          {roots.map((r) => (
            <button key={r.path} style={chip(path === r.path)} title={r.path} onClick={() => open(r.path)}>{r.label}</button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '6px 10px', borderBottom: '1px solid var(--border)' }}>
          <button style={btn} disabled={!parent} onClick={() => parent && open(parent)}>↑ up</button>
          <code style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{path ?? ''}</code>
          {mode === 'dir' && path && (
            <button
              style={btn}
              title="create a new folder here"
              onClick={async () => {
                const name = prompt('New folder name', '')
                if (!name || !path) return
                try {
                  const r = await createFsDir(path, name.trim())
                  await open(path)
                  setSelected(r.path)
                } catch (e) {
                  setError((e as Error).message)
                }
              }}
            >+ New folder</button>
          )}
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 6 }}>
          {error && <div style={{ color: '#ef4444', padding: 8 }}>{error}</div>}
          {!error && entries.length === 0 && path && <div style={{ color: 'var(--text-secondary)', padding: 8 }}>empty directory</div>}
          {entries.map((e) => (
            <div
              key={e.path}
              style={{ ...row(selected === e.path), opacity: e.dangling ? 0.7 : 1 }}
              onClick={() => { if (!e.dangling) setSelected(e.path) }}
              onDoubleClick={() => { if (e.dangling) return; e.is_dir ? open(e.path) : onPick(e.path) }}
              title={e.dangling ? `broken link → ${e.link_target ?? '?'} (not visible to the server; inside Docker the target must be mounted)` : e.is_dir ? 'double-click to open' : e.path}
            >
              <span style={{ width: 16, textAlign: 'center' }}>{e.dangling ? '⚠' : e.is_dir ? '📁' : '·'}</span>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {e.name}{e.is_symlink && !e.dangling ? <span style={{ color: 'var(--text-secondary)', fontSize: 10 }}> ↪</span> : null}
              </span>
              {e.dangling && <span style={{ color: '#f59e0b', fontSize: 10 }}>link target not visible to the server: {e.link_target}</span>}
              {!e.is_dir && !e.dangling && <span style={{ color: 'var(--text-secondary)', fontSize: 10 }}>{fmtSize(e.size)}</span>}
              {e.is_dir && <button style={btn} onClick={(ev) => { ev.stopPropagation(); open(e.path) }}>open</button>}
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: 10, borderTop: '1px solid var(--border)' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: 10 }}>
            Browsing covers the data roots. Add more with <code>{extraEnv}</code> (inside Docker: a read-only bind mount).
          </span>
          <span style={{ flex: 1 }} />
          <button style={btn} onClick={onClose}>Cancel</button>
          <button
            style={{ ...btn, borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }}
            disabled={!pickValue || (mode === 'file' && !!selected && entries.find((x) => x.path === selected)?.is_dir)}
            onClick={() => pickValue && onPick(pickValue)}
          >
            Use {selected ? 'selected' : 'this directory'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface FieldProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  mode?: 'dir' | 'file'
  style?: CSSProperties
  /** Check whether the server can see a typed path and show a hint. */
  checkExists?: boolean
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void
}

export function PathField({ value, onChange, placeholder, mode = 'dir', style, checkExists = true, onKeyDown }: FieldProps) {
  const [open, setOpen] = useState(false)
  const [seen, setSeen] = useState<boolean | null>(null)

  useEffect(() => {
    if (!checkExists || !value || value.length < 2) { setSeen(null); return }
    let cancelled = false
    const t = setTimeout(() => {
      fetchFsExists(value).then((r) => { if (!cancelled) setSeen(r.exists) }).catch(() => { if (!cancelled) setSeen(null) })
    }, 400)
    return () => { cancelled = true; clearTimeout(t) }
  }, [value, checkExists])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <input style={{ ...style, flex: 1, minWidth: 0 }} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown} />
        <button type="button" style={btn} onClick={() => setOpen(true)} title="browse the server's data roots">Browse…</button>
      </div>
      {seen === false && (
        <span style={{ fontSize: 10, color: '#f59e0b' }}>
          The server cannot see this path. Inside Docker, use the container's view (e.g. /workspace/data/…) or Browse.
        </span>
      )}
      {open && (
        <PathPickerModal initialPath={value} mode={mode} onPick={(p) => { onChange(p); setOpen(false) }} onClose={() => setOpen(false)} />
      )}
    </div>
  )
}
