/** The physio nodes' own view: for physio_regressors, how each run was paired with a
 *  block of the recording (and the regressors it got, as a heat-strip); for physio_clean,
 *  how much variance the model removed per run, with a montage of where. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { NodePopupContext } from './index'
import type { PhysioNodeView, PhysioViewItem } from '../../../api/types'
import { fetchRunNodePhysio } from '../../../api/preproc'
import { h, muted, pad, table, td, th } from './shared'

const img: CSSProperties = { maxWidth: '100%', border: '1px solid var(--border)', borderRadius: 4, background: '#000', display: 'block' }
const num = (v: unknown, digits = 0) => (typeof v === 'number' ? v.toFixed(digits) : v == null ? '—' : String(v))
const pct = (v: unknown) => (typeof v === 'number' ? `${(v * 100).toFixed(1)} %` : '—')
const hhmm = (s: unknown) => (typeof s === 'number' ? `${String(Math.floor(s / 3600)).padStart(2, '0')}:${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '—')

export function PhysioTab({ ctx }: { ctx: NodePopupContext }) {
  const [view, setView] = useState<PhysioNodeView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  useEffect(() => {
    let cancelled = false
    const load = () => fetchRunNodePhysio(ctx.runId, ctx.nodeId)
      .then((v) => { if (!cancelled) { setView(v); setError(null) } })
      .catch((e) => { if (!cancelled) setError(String(e)) })
    void load()
    if (!ctx.isRunning) return () => { cancelled = true }
    const id = setInterval(load, 5000)
    return () => { cancelled = true; clearInterval(id) }
  }, [ctx.runId, ctx.nodeId, ctx.isRunning])

  if (error) return <div style={muted}>Not available yet{ctx.isRunning ? ' — the node is still running' : ''}. ({error})</div>
  if (!view) return <div style={muted}>Loading…</div>
  if (!view.kind || view.items.length === 0) return <div style={muted}>Nothing written yet{ctx.isRunning ? ' — the node is still running' : ''}.</div>

  const items = view.items
  const selected = open != null ? items.find((it) => it.index === open) : null
  return (
    <div style={pad}>
      {view.kind === 'regressors' ? <PairingTable items={items} open={open} onOpen={setOpen} /> : <CleaningTable items={items} open={open} onOpen={setOpen} />}
      {items[0]?.skipped_runs && items[0].skipped_runs.length > 0 && (
        <div style={{ ...muted, padding: '6px 0' }}>Not covered by any recording (left out): {items[0].skipped_runs.join(', ')}</div>
      )}
      {selected && selected.image_url && (
        <div style={{ marginTop: 10 }}>
          <div style={h}>{selected.run}{view.kind === 'regressors' ? ' · regressors, one row each, time left → right (z-scored, blue − / red +)' : ' · fraction of variance removed per voxel (black 0 → yellow ≥ 50 %)'}</div>
          <img style={img} src={selected.image_url} alt={`${view.kind} for ${selected.run}`} />
        </div>
      )}
    </div>
  )
}

function PairingTable({ items, open, onOpen }: { items: PhysioViewItem[]; open: number | null; onOpen: (i: number | null) => void }) {
  return (
    <table style={table}>
      <thead>
        <tr>{['run', 'session', 'scanned at', 'block', 'triggers', 'BOLD TRs', 'Δ', 'order', 'regressors', ''].map((c) => <th key={c} style={th}>{c}</th>)}</tr>
      </thead>
      <tbody>
        {items.map((it) => {
          const delta = typeof it.triggers === 'number' && typeof it.bold_n_trs === 'number' ? it.triggers - it.bold_n_trs : null
          return (
            <tr key={it.index} style={{ background: open === it.index ? 'rgba(0,229,255,0.06)' : undefined }}>
              <td style={td}>{it.error ? <span style={{ color: '#ef4444' }}>{it.error}</span> : it.run}</td>
              <td style={td}>{it.session ?? '—'}</td>
              <td style={td}>{hhmm(it.acquisition_time_s)}</td>
              <td style={td}>#{num(it.block)} of {num(it.n_blocks)}</td>
              <td style={td}>{num(it.triggers)}</td>
              <td style={td}>{num(it.bold_n_trs)}</td>
              <td style={{ ...td, color: delta != null && Math.abs(delta) > 1 ? '#f59e0b' : undefined }}>{delta == null ? '—' : delta > 0 ? `+${delta}` : String(delta)}</td>
              <td style={{ ...td, color: it.order === 'acquisition_time' ? undefined : '#f59e0b' }} title={it.order === 'acquisition_time' ? 'ordered by the sidecar AcquisitionTime' : 'no sidecar: taken in the order given'}>{it.order ?? '—'}</td>
              <td style={td}>{num(it.n_regressors)}</td>
              <td style={td}>{it.has_image && <button style={btn} onClick={() => onOpen(open === it.index ? null : it.index)}>{open === it.index ? 'Hide' : 'Show'}</button>}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function CleaningTable({ items, open, onOpen }: { items: PhysioViewItem[]; open: number | null; onOpen: (i: number | null) => void }) {
  return (
    <table style={table}>
      <thead>
        <tr>{['run', 'TRs', 'regressors', 'variance removed', 'median voxel', '95th pct voxel', 'NaN/Inf', ''].map((c) => <th key={c} style={th}>{c}</th>)}</tr>
      </thead>
      <tbody>
        {items.map((it) => (
          <tr key={it.index} style={{ background: open === it.index ? 'rgba(0,229,255,0.06)' : undefined }}>
            <td style={td}>{it.error ? <span style={{ color: '#ef4444' }}>{it.error}</span> : it.run}</td>
            <td style={td}>{num(it.n_trs)}</td>
            <td style={td}>{num(it.n_regressors)}</td>
            <td style={td}>{pct(it.variance_removed_fraction)}</td>
            <td style={td}>{pct(it.variance_removed_p50)}</td>
            <td style={td}>{pct(it.variance_removed_p95)}</td>
            <td style={{ ...td, color: it.n_nan_inf ? '#ef4444' : undefined }}>{num(it.n_nan_inf)}</td>
            <td style={td}>{it.has_image && <button style={btn} onClick={() => onOpen(open === it.index ? null : it.index)}>{open === it.index ? 'Hide' : 'Show map'}</button>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const btn: CSSProperties = { padding: '2px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-primary)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11 }
