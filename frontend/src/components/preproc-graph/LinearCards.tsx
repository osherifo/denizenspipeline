/** Simple view: a pipeline that is a single chain, shown as ordered cards. */
import type { CSSProperties } from 'react'
import { usePreprocPipelineStore, topoOrder } from '../../stores/preproc-pipeline-store'
import { KIND_COLORS, KIND_LABELS } from './PipelineNodeCard'
import type { PreprocNodeInfo } from '../../api/types'

const card = (selected: boolean, color: string): CSSProperties => ({
  border: selected ? `2px solid ${color}` : '1px solid var(--border)',
  borderLeft: `4px solid ${color}`,
  borderRadius: 8, background: 'var(--bg-card)', padding: '10px 12px', cursor: 'pointer',
  display: 'flex', alignItems: 'center', gap: 10, fontSize: 12,
})
const arrow: CSSProperties = { textAlign: 'center', color: 'var(--text-secondary)', fontSize: 14, margin: '2px 0' }
const select: CSSProperties = {
  padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)',
  color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit',
}

interface Props {
  library: PreprocNodeInfo[]
}

export function LinearCards({ library }: Props) {
  const pipeline = usePreprocPipelineStore((s) => s.pipeline)
  const selectedNodeId = usePreprocPipelineStore((s) => s.selectedNodeId)
  const selectNode = usePreprocPipelineStore((s) => s.selectNode)
  const appendAfter = usePreprocPipelineStore((s) => s.appendAfter)
  const ordered = topoOrder(pipeline)
  const byName = new Map(library.map((n) => [n.name, n]))
  const addable = library.filter((n) => n.kind !== 'source' || ordered.length === 0)

  const picker = (afterId: string | null) => (
    <select
      style={select}
      value=""
      onChange={(e) => { if (e.target.value) appendAfter(afterId, e.target.value) }}
    >
      <option value="">+ add step…</option>
      {addable.map((n) => <option key={n.name} value={n.name}>{n.name} — {n.description.slice(0, 60)}</option>)}
    </select>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {ordered.length === 0 && (
        <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginBottom: 6 }}>
          Start from a template, or add a first step (usually a source or an app such as fmriprep).
        </div>
      )}
      {ordered.map((n, i) => {
        const info = byName.get(n.type)
        const kind = n.kind ?? info?.kind ?? 'interface'
        const color = KIND_COLORS[kind]
        const paramSummary = Object.entries(n.data.params ?? {}).filter(([, v]) => v !== '' && v !== null && v !== undefined)
          .slice(0, 4).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(',') : String(v)}`).join('  ')
        return (
          <div key={n.id}>
            {i > 0 && <div style={arrow}>↓</div>}
            <div style={card(selectedNodeId === n.id, color)} onClick={() => selectNode(n.id)}>
              <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color, width: 60 }}>{KIND_LABELS[kind]}</span>
              <span style={{ fontWeight: 700 }}>{n.id}</span>
              <span style={{ color: 'var(--text-secondary)' }}>{n.type}</span>
              {n.data.iter && <span style={{ color: 'var(--text-secondary)' }}>×N</span>}
              {pipeline.manifest?.backend_node === n.id && <span title="backend node" style={{ color }}>★</span>}
              <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)', fontFamily: 'monospace', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 320 }}>{paramSummary}</span>
            </div>
          </div>
        )
      })}
      <div style={{ marginTop: 8 }}>{picker(null)}</div>
    </div>
  )
}
