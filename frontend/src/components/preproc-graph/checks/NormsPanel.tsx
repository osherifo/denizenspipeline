/** The checkpoint norms table: every (step, metric) bound the built-ins define, editable;
 *  edits are saved as an overlay file in $FMRIFLOW_HOME/configs/norms.yaml, so the package
 *  stays untouched and the built-in value is always one click away. */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type { BoundJson, NormsRow } from '../../../api/types'
import { fetchNorms, saveNorms } from '../../../api/preproc'
import { formatBound, parseBounds } from './bounds'

const table: CSSProperties = { borderCollapse: 'collapse', fontSize: 11, width: '100%' }
const th: CSSProperties = { textAlign: 'left', padding: '4px 8px', color: 'var(--text-secondary)', fontWeight: 600, borderBottom: '1px solid var(--border)', fontSize: 10, textTransform: 'uppercase' }
const td: CSSProperties = { padding: '3px 8px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle', fontFamily: 'monospace' }
const input: CSSProperties = { padding: '3px 6px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'monospace', width: 220 }
const btn: CSSProperties = { ...input, width: 'auto', cursor: 'pointer', fontFamily: 'inherit' }

type Draft = Record<string, string>   // key step|kind|metric -> "op value" text

const key = (r: NormsRow) => `${r.step}|${r.kind}|${r.metric}`

export function NormsPanel() {
  const [rows, setRows] = useState<NormsRow[]>([])
  const [path, setPath] = useState('')
  const [draft, setDraft] = useState<Draft>({})
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('')

  const load = () => fetchNorms().then((r) => { setRows(r.rows); setPath(r.path); setDraft({}) }).catch((e) => setError(String(e)))
  useEffect(() => { void load() }, [])

  const dirty = Object.keys(draft).length > 0
  const visible = useMemo(() => rows.filter((r) => !filter || r.step.includes(filter) || r.metric.includes(filter)), [rows, filter])

  /** The overlay to save: every user-sourced row plus every edited row, minus rows reset to built-in. */
  const buildOverlay = (): { norms: Record<string, Record<string, Record<string, BoundJson>>>; errors: string[] } => {
    const norms: Record<string, Record<string, Record<string, BoundJson>>> = {}
    const errors: string[] = []
    for (const r of rows) {
      const k = key(r)
      let bound: BoundJson | null = null
      if (k in draft) {
        const text = draft[k].trim()
        if (text === '') { bound = null }   // reset to built-in
        else {
          const parsed = parseBounds(`${r.metric} ${text}`)
          if (parsed.errors.length) { errors.push(`${r.step} ${r.metric}: ${parsed.errors[0]}`); continue }
          bound = parsed.bounds[r.metric]
        }
      } else if (r.source === 'user') {
        bound = [r.op, r.value]
      }
      if (bound) ((norms[r.step] ??= {})[r.kind] ??= {})[r.metric] = bound
    }
    return { norms, errors }
  }

  const save = async () => {
    const { norms, errors } = buildOverlay()
    if (errors.length) { setError(errors.join('; ')); return }
    setSaving(true); setError(null); setSaved(false)
    try { const r = await saveNorms(norms); setRows(r.rows); setDraft({}); setSaved(true) } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, fontSize: 12 }}>
        <b>Checkpoint norms</b>
        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>a result outside its bound is <b>bad</b> · edit the value, blank it to reset · saved to <code>{path}</code></span>
        <span style={{ flex: 1 }} />
        <input style={{ ...input, fontFamily: 'inherit', width: 160 }} placeholder="filter step / metric" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button style={btn} disabled={!dirty} onClick={() => setDraft({})}>Revert</button>
        <button style={{ ...btn, borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }} disabled={!dirty || saving} onClick={save}>{saving ? 'Saving…' : 'Save'}</button>
      </div>
      {error && <div style={{ color: '#ef4444', fontSize: 11, marginBottom: 6 }}>{error}</div>}
      {saved && !dirty && <div style={{ color: '#10b981', fontSize: 11, marginBottom: 6 }}>Saved. New runs use these bounds.</div>}
      <div style={{ overflowX: 'auto' }}>
        <table style={table}>
          <thead><tr><th style={th}>step</th><th style={th}>metric</th><th style={th}>bound (op value)</th><th style={th}>built-in</th></tr></thead>
          <tbody>
            {visible.map((r) => {
              const k = key(r)
              const text = k in draft ? draft[k] : `${r.op} ${Array.isArray(r.value) ? (r.value as unknown[]).join(' ') : String(r.value)}`
              const isUser = k in draft ? draft[k].trim() !== '' : r.source === 'user'
              return (
                <tr key={k}>
                  <td style={td}>{r.step}</td>
                  <td style={td}>{r.metric}</td>
                  <td style={td}>
                    <input style={{ ...input, borderColor: isUser ? 'var(--accent-cyan)' : 'var(--border)' }} value={text} aria-label={`${r.step} ${r.kind} ${r.metric}`}
                      onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
                    {isUser && <span style={{ fontSize: 9, color: 'var(--accent-cyan)', marginLeft: 6 }}>override</span>}
                  </td>
                  <td style={{ ...td, color: 'var(--text-secondary)' }}>{r.builtin ? formatBound(r.builtin[0], r.builtin[1]) : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
