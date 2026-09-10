/** Checkpoint metrics: the functions that turn an artifact into numbers. Built-ins are
 *  read-only (view, duplicate); user metrics live as one Python file each under
 *  $FMRIFLOW_HOME/addons/checks/ and can be created, edited, tried on a file, and deleted. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { MetricInfo, MetricRunResult } from '../../../api/types'
import { deleteMetric, fetchCheckMetrics, fetchMetric, fetchMetricScaffold, runMetric, saveMetric } from '../../../api/preproc'
import { CodeEditor } from '../../editor/CodeEditor'
import { PathField } from '../../common/PathPicker'
import { useDialog } from '../../common/Dialog'

const table: CSSProperties = { borderCollapse: 'collapse', fontSize: 11, width: '100%' }
const th: CSSProperties = { textAlign: 'left', padding: '4px 8px', color: 'var(--text-secondary)', fontWeight: 600, borderBottom: '1px solid var(--border)', fontSize: 10, textTransform: 'uppercase' }
const td: CSSProperties = { padding: '3px 8px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle' }
const input: CSSProperties = { padding: '3px 6px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'inherit' }
const btn: CSSProperties = { ...input, cursor: 'pointer' }
const tierBadge = (tier: string): CSSProperties => ({
  padding: '0 5px', borderRadius: 3, fontSize: 9, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5,
  border: `1px solid ${tier === 'user' ? 'var(--accent-cyan)' : 'var(--border)'}`, color: tier === 'user' ? 'var(--accent-cyan)' : 'var(--text-secondary)',
})

type EditorState = { name: string; code: string; readOnly: boolean; isNew: boolean } | null

export function MetricsPanel() {
  const [metrics, setMetrics] = useState<MetricInfo[]>([])
  const [addonsDir, setAddonsDir] = useState('')
  const [hidden, setHidden] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [editor, setEditor] = useState<EditorState>(null)
  const dlg = useDialog()

  const load = () => fetchCheckMetrics().then((r) => { setMetrics(r.metrics); setAddonsDir(r.addons_dir ?? ''); setHidden(r.hidden ?? 0) }).catch((e) => setError(String(e)))
  useEffect(() => { void load() }, [])

  const open = async (m: MetricInfo) => {
    try {
      const d = await fetchMetric(m.name)
      setEditor({ name: m.name, code: d.source, readOnly: d.builtin, isNew: false })
    } catch (e) { setError(String(e)) }
  }
  const duplicate = async (m: MetricInfo) => {
    try {
      const d = await fetchMetric(m.name)
      const name = `${m.name}_copy`
      // re-point the decorator at the new name; the function may keep its name
      const code = d.source.replace(new RegExp(`checkpoint_metric\\(["']${m.name}["']\\)`, 'g'), `checkpoint_metric("${name}")`)
      setEditor({ name, code, readOnly: false, isNew: true })
    } catch (e) { setError(String(e)) }
  }
  const create = async () => {
    try {
      const { code } = await fetchMetricScaffold()
      setEditor({ name: 'my_metric', code, readOnly: false, isNew: true })
    } catch (e) { setError(String(e)) }
  }
  const remove = async (m: MetricInfo) => {
    if (!(await dlg.confirm(`Delete metric "${m.name}"? Its file ${m.path ?? ''} is removed; checks that name it will fail to resolve.`))) return
    try {
      const r = await deleteMetric(m.name)
      setMetrics(r.metrics)
    } catch (e) { setError(String(e)) }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Checkpoint metrics</span>
        <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
          a metric turns an artifact into numbers; norms below put bounds on them · user metrics live in {addonsDir || '$FMRIFLOW_HOME/addons/checks/'}{hidden > 0 && ` · ${hidden} built-in metric${hidden === 1 ? '' : 's'} of parked checks hidden`}
        </span>
        <span style={{ flex: 1 }} />
        <button style={btn} onClick={() => void create()}>+ New metric</button>
      </div>
      {error && <div style={{ color: '#ef4444', fontSize: 11, marginBottom: 6 }}>{error}</div>}
      <table style={table}>
        <thead>
          <tr><th style={th}>metric</th><th style={th}>tier</th><th style={th}>description</th><th style={th} /></tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.name}>
              <td style={{ ...td, fontFamily: 'monospace' }}>{m.name}</td>
              <td style={td}><span style={tierBadge(m.tier)}>{m.tier}</span></td>
              <td style={{ ...td, color: m.error ? '#ef4444' : 'var(--text-primary)' }}>{m.error ? `failed to load: ${m.error}` : m.description}</td>
              <td style={{ ...td, whiteSpace: 'nowrap', textAlign: 'right' }}>
                <button style={btn} onClick={() => void open(m)}>{m.tier === 'user' ? 'Edit' : 'View'}</button>{' '}
                {!m.error && <button style={btn} onClick={() => void duplicate(m)}>Duplicate</button>}{' '}
                {m.tier === 'user' && <button style={{ ...btn, color: '#ef4444' }} aria-label={`delete metric ${m.name}`} onClick={() => void remove(m)}>Delete</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {editor && (
        <MetricEditorModal
          {...editor}
          onSaved={(rows) => { setMetrics(rows); setEditor((e) => (e ? { ...e, isNew: false } : e)) }}
          onClose={() => setEditor(null)}
        />
      )}
    </div>
  )
}

// ── editor modal ────────────────────────────────────────────────────

const backdrop: CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }
const card: CSSProperties = { width: 'min(1000px, 94vw)', height: 'min(760px, 90vh)', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, display: 'flex', flexDirection: 'column', overflow: 'hidden' }

interface EditorProps {
  name: string
  code: string
  readOnly: boolean
  isNew: boolean
  onSaved: (metrics: MetricInfo[]) => void
  onClose: () => void
}

function MetricEditorModal({ name: initialName, code: initialCode, readOnly, isNew, onSaved, onClose }: EditorProps) {
  const [name, setName] = useState(initialName)
  const [code, setCode] = useState(initialCode)
  const [status, setStatus] = useState<string | null>(null)
  const [tryPath, setTryPath] = useState('')
  const [result, setResult] = useState<MetricRunResult | null>(null)
  const [savedName, setSavedName] = useState<string | null>(readOnly || !isNew ? initialName : null)

  const save = async () => {
    setStatus('saving…')
    try {
      const r = await saveMetric(name, code)
      setStatus(`saved ${r.path}`)
      setSavedName(name)
      onSaved(r.metrics)
    } catch (e) { setStatus((e as Error).message) }
  }
  const tryIt = async () => {
    if (!savedName) { setStatus('save first, then try it'); return }
    setResult(null)
    try { setResult(await runMetric(savedName, tryPath)) } catch (e) { setStatus((e as Error).message) }
  }

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: 10, borderBottom: '1px solid var(--border)', fontSize: 12 }}>
          <b>{readOnly ? 'Built-in metric' : isNew ? 'New metric' : 'Edit metric'}</b>
          {readOnly ? <span style={{ fontFamily: 'monospace' }}>{name}</span>
            : <input style={{ ...input, width: 200, fontFamily: 'monospace' }} value={name} onChange={(e) => setName(e.target.value)} placeholder="metric name" disabled={!isNew} title={isNew ? 'file and decorator name' : 'rename by duplicating'} />}
          {!readOnly && <span style={{ color: 'var(--text-secondary)' }}>→ addons/checks/{name}.py · must register @checkpoint_metric("{name}")</span>}
          {readOnly && <span style={{ color: 'var(--text-secondary)' }}>read-only · Duplicate to make your own</span>}
          <span style={{ flex: 1 }} />
          {status && <span style={{ color: 'var(--text-secondary)', maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={status}>{status}</span>}
          {!readOnly && <button style={btn} onClick={() => void save()}>Save + reload</button>}
          <button style={btn} onClick={onClose}>Close</button>
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <CodeEditor code={code} onChange={readOnly ? () => {} : setCode} />
        </div>
        <div style={{ borderTop: '1px solid var(--border)', padding: 8, fontSize: 11, display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 220 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Try it on a file:</span>
            <PathField style={{ ...input, flex: 1 }} compact mode="file" placeholder="/path/to/an/artifact" value={tryPath} onChange={setTryPath} />
            <button style={btn} onClick={() => void tryIt()} disabled={!tryPath}>Run</button>
          </div>
          {result && (
            <pre style={{ margin: 0, overflow: 'auto', fontSize: 10, background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 4, padding: 6, color: result.ok ? 'var(--text-primary)' : '#ef4444' }}>
              {result.ok ? JSON.stringify({ metrics: result.metrics, detail: result.detail }, null, 2) : result.error}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}
