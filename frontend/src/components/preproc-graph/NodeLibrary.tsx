/** Library tab: browse the node library with kind / source / preflight badges; open detail. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { fetchNodeDetail, nodePreflight } from '../../api/preproc'
import { usePreprocPipelineStore } from '../../stores/preproc-pipeline-store'
import type { PreprocNodeDetail, PreprocNodeInfo, PreprocNodeKind } from '../../api/types'
import { KIND_COLORS, KIND_LABELS } from './PipelineNodeCard'

const list: CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8 }
const card = (selected: boolean, color: string): CSSProperties => ({
  border: selected ? `2px solid ${color}` : '1px solid var(--border)', borderLeft: `4px solid ${color}`, borderRadius: 8,
  background: 'var(--bg-card)', padding: '8px 10px', fontSize: 12, cursor: 'pointer',
})
const badge = (color: string): CSSProperties => ({
  fontSize: 9, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color, border: `1px solid ${color}55`, borderRadius: 3, padding: '1px 5px',
})
const SOURCE_COLOR: Record<string, string> = { 'built-in': '#9ca3af', user: '#22c55e', unknown: '#9ca3af' }

interface Props {
  onUseInPipeline?: (type: string) => void
}

export function NodeLibrary({ onUseInPipeline }: Props) {
  const library = usePreprocPipelineStore((s) => s.library)
  const [filter, setFilter] = useState('')
  const [kind, setKind] = useState<PreprocNodeKind | ''>('')
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<PreprocNodeDetail | null>(null)
  const [preflight, setPreflight] = useState<Record<string, { ok: boolean; errors: string[]; warnings: string[] }>>({})

  useEffect(() => {
    if (!selected) { setDetail(null); return }
    let cancelled = false
    fetchNodeDetail(selected).then((d) => { if (!cancelled) setDetail(d) }).catch(() => {})
    nodePreflight(selected).then((p) => { if (!cancelled) setPreflight((prev) => ({ ...prev, [selected]: p })) }).catch(() => {})
    return () => { cancelled = true }
  }, [selected])

  const shown = library.filter((n) => (!kind || n.kind === kind) && (!filter || `${n.name} ${n.description}`.toLowerCase().includes(filter.toLowerCase())))

  return (
    <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 420px' : '1fr', gap: 12 }}>
      <div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <input placeholder="filter…" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ flex: 1, padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit' }} />
          <select value={kind} onChange={(e) => setKind(e.target.value as PreprocNodeKind | '')} style={{ padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit' }}>
            <option value="">all kinds</option>
            {(Object.keys(KIND_LABELS) as PreprocNodeKind[]).map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
          </select>
        </div>
        <div style={list}>
          {shown.map((n: PreprocNodeInfo) => (
            <div key={n.name} style={card(selected === n.name, KIND_COLORS[n.kind])} onClick={() => setSelected(n.name)}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 4 }}>
                <span style={{ fontWeight: 700 }}>{n.name}</span>
                <span style={badge(KIND_COLORS[n.kind])}>{KIND_LABELS[n.kind]}</span>
                <span style={badge(SOURCE_COLOR[n.source] ?? '#60a5fa')}>{n.source}</span>
                {n.checks.length > 0 && <span style={badge('#10b981')} title={n.checks.join(', ')}>{n.checks.length} checks</span>}
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{n.description}</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: 10, marginTop: 4, fontFamily: 'monospace' }}>
                {Object.keys(n.inputs).join(', ') || '—'} → {Object.keys(n.outputs).join(', ') || '—'}
              </div>
            </div>
          ))}
        </div>
      </div>
      {selected && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 12, fontSize: 12, overflow: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <b style={{ fontSize: 13 }}>{selected}</b>
            <span style={{ flex: 1 }} />
            {onUseInPipeline && <button onClick={() => onUseInPipeline(selected)} style={{ padding: '4px 10px', borderRadius: 4, border: '1px solid var(--accent-cyan)', background: 'transparent', color: 'var(--accent-cyan)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>Use in Build</button>}
            <button onClick={() => setSelected(null)} style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>✕</button>
          </div>
          {preflight[selected] && (
            <div style={{ marginBottom: 8, color: preflight[selected].ok ? '#10b981' : '#ef4444' }}>
              {preflight[selected].ok ? '✓ ready on this host' : preflight[selected].errors.map((e, i) => <div key={i}>✗ {e}</div>)}
              {preflight[selected].warnings.map((w, i) => <div key={i} style={{ color: '#f59e0b' }}>! {w}</div>)}
            </div>
          )}
          {detail && (
            <>
              <div style={{ color: 'var(--text-secondary)', marginBottom: 6 }}>{detail.module} · v{detail.version || '?'}</div>
              {Object.keys(detail.params_schema).length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>Parameters</div>
                  {Object.entries(detail.params_schema).map(([k, f]) => (
                    <div key={k} style={{ fontSize: 11, marginBottom: 2 }}><code>{k}</code> <span style={{ color: 'var(--text-secondary)' }}>{f.type}{f.group ? ` · ${f.group}` : ''}{f.description ? ` — ${f.description}` : ''}</span></div>
                  ))}
                </div>
              )}
              {detail.source_code && (
                <pre style={{ fontSize: 10, background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: 8, overflow: 'auto', maxHeight: 400, margin: 0 }}>{detail.source_code}</pre>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
