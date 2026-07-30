/**
 * What the heuristic did with each DICOM series — three views, three questions.
 *
 * 1. Audit table (per subject). One row per series with the parameters a rule
 *    discriminates on — TR/TE/dims/image_type — beside the BIDS path it
 *    produced. This is the debugging view: you need the parameters and the
 *    outcome in the same row to see *why* a rule fired.
 * 2. Coverage matrix (per study). Subjects x BIDS keys. A whole empty column
 *    is a rule that never matched anywhere — a code bug. A single empty cell
 *    is one subject missing what the others have — a data incident. Same
 *    visual, different diagnosis.
 * 3. Flow (per study). Aggregated protocol -> datatype -> suffix. Aggregate
 *    only; at series granularity it is spaghetti. Its job is making the
 *    dropped ribbon impossible to scroll past.
 *
 * All three derive from provenance heudiconv already leaves behind, so they
 * work on any converted dataset without re-running anything.
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'

import {
  fetchConvertCoverage,
  fetchConvertDecisionTable,
  fetchConvertFlow,
} from '../../api/client'
import type {
  ConvertCoverage,
  ConvertDecisionTable as TableData,
  ConvertFlow,
} from '../../api/types'

type View = 'audit' | 'coverage' | 'flow'

interface Props {
  bidsDir: string
  subject: string
  defaultView?: View
}

export function ConvertDecisionTable({ bidsDir, subject, defaultView = 'coverage' }: Props) {
  const [view, setView] = useState<View>(defaultView)

  return (
    <div style={boxStyle}>
      <div style={headerStyle}>
        <span>DICOM → BIDS</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          {(['coverage', 'audit', 'flow'] as View[]).map(v => (
            <button key={v} style={tabStyle(v === view)} onClick={() => setView(v)}>
              {v === 'coverage' ? 'Coverage' : v === 'audit' ? 'Audit' : 'Flow'}
            </button>
          ))}
        </div>
      </div>
      {view === 'audit' && <AuditTable bidsDir={bidsDir} subject={subject} />}
      {view === 'coverage' && <CoverageMatrix bidsDir={bidsDir} />}
      {view === 'flow' && <FlowView bidsDir={bidsDir} />}
    </div>
  )
}

// ── 1. audit table ──────────────────────────────────────────────────

function AuditTable({ bidsDir, subject }: { bidsDir: string; subject: string }) {
  const { data, error, loading } = useAsync<TableData>(
    () => fetchConvertDecisionTable(bidsDir, subject), [bidsDir, subject])
  const [showDropped, setShowDropped] = useState(true)

  if (loading) return <div style={hintStyle}>Reading conversion provenance…</div>
  if (error) return <Missing error={error} />
  if (!data) return null

  const rows = showDropped ? data.series : data.series.filter(s => !s.dropped)

  return (
    <>
      <div style={subHeaderStyle}>
        sub-{data.subject} · {data.n_series} series in ·{' '}
        <strong style={{ color: 'var(--accent-green, #10b981)' }}>{data.n_mapped} mapped</strong> ·{' '}
        <strong style={{ color: data.n_dropped ? 'var(--accent-yellow, #e2a832)' : 'inherit' }}>
          {data.n_dropped} dropped
        </strong>
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5 }}>
          <input type="checkbox" checked={showDropped}
                 onChange={e => setShowDropped(e.target.checked)} />
          show dropped
        </label>
      </div>

      {data.warnings.length > 0 && (
        <div style={warnBoxStyle}>
          {data.warnings.map((w, i) => <div key={i} style={warnRowStyle}>⚠ {w}</div>)}
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              {['series', 'description', 'dims', 'TR', 'TE', '→ BIDS', 'rule', 'status']
                .map(h => <th key={h} style={thStyle}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(s => (
              <tr key={s.series_id} style={s.dropped ? droppedRowStyle : undefined}>
                <td style={{ ...tdStyle, fontFamily: 'monospace' }}>{s.series_number}</td>
                <td style={tdStyle}>
                  {s.description}
                  {s.is_derived && (
                    <span style={chipStyle} title={s.image_type.join(', ')}>derived</span>
                  )}
                </td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                  {s.dims.filter(d => d > 0).join('×') || '—'}
                </td>
                <td style={numCell}>{fmt(s.tr)}</td>
                <td style={numCell}>{fmt(s.te)}</td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                  {s.outputs.length
                    ? s.outputs.map(o => <div key={o}>{o.split('/').slice(-2).join('/')}</div>)
                    : <span style={mutedStyle}>—</span>}
                </td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                  {s.rules.length
                    ? s.rules.map(r => <div key={r}>{ruleName(r)}</div>)
                    : <span style={mutedStyle}>—</span>}
                </td>
                <td style={tdStyle}><StatusTag status={s.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={footnoteStyle}>
        heudiconv records what the heuristic claimed, not why it passed over the
        rest — so “dropped” means unclaimed, without a stated reason.
      </div>
    </>
  )
}

function StatusTag({ status }: { status: string }) {
  const color = status === 'ok'
    ? 'var(--accent-green, #10b981)'
    : status === 'dropped'
      ? 'var(--text-secondary)'
      : 'var(--accent-cyan, #0891b2)'
  return (
    <span style={{ color, fontSize: 10, fontWeight: 700, whiteSpace: 'nowrap' }}>
      {status}
    </span>
  )
}

// ── 2. coverage matrix ──────────────────────────────────────────────

function CoverageMatrix({ bidsDir }: { bidsDir: string }) {
  const { data, error, loading } = useAsync<ConvertCoverage>(
    () => fetchConvertCoverage(bidsDir), [bidsDir])

  if (loading) return <div style={hintStyle}>Scanning subjects…</div>
  if (error) return <Missing error={error} />
  if (!data || data.subjects.length === 0) {
    return <div style={hintStyle}>No converted subjects with provenance in this dataset.</div>
  }

  const dead = new Set(data.never_matched)

  return (
    <>
      <div style={subHeaderStyle}>
        {data.subjects.length} subject{data.subjects.length === 1 ? '' : 's'} ·{' '}
        {data.keys.length} BIDS key{data.keys.length === 1 ? '' : 's'}
        {data.subjects.length === 1 && (
          <span style={{ marginLeft: 10 }}>
            (one subject — this view earns its keep once a study has several)
          </span>
        )}
      </div>

      {dead.size > 0 && (
        <div style={warnBoxStyle}>
          <div style={warnRowStyle}>
            ⚠ {dead.size} rule{dead.size === 1 ? '' : 's'} declared but never matched for
            any subject — a heuristic bug rather than missing data:{' '}
            {[...dead].join(', ')}
          </div>
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>subject</th>
              {data.keys.map(k => (
                <th key={k} style={{
                  ...thStyle,
                  color: dead.has(k) ? 'var(--accent-red, #ef4444)' : undefined,
                }}>
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.matrix.map(row => (
              <tr key={row.subject}>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600 }}>
                  sub-{row.subject}
                </td>
                {row.cells.map((n, i) => (
                  <td key={data.keys[i]} style={cellStyle(n, dead.has(data.keys[i]))}>
                    {n || '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={footnoteStyle}>
        Cell = number of outputs. Run indices fold together (four runs of one
        acquisition is one column); <code>inv-1</code> and <code>inv-2</code> stay
        separate, because a subject missing one is a real finding. A whole red
        column is a rule that never fired; a single red cell is one subject
        missing what the others have.
      </div>
    </>
  )
}

/** Empty cells are the point of this view, so they get the colour. */
function cellStyle(n: number, columnDead: boolean): CSSProperties {
  const base: CSSProperties = {
    ...tdStyle, textAlign: 'center', fontFamily: 'monospace', fontWeight: 600,
  }
  if (n > 0) return { ...base, color: 'var(--text-primary)' }
  return {
    ...base,
    // A dead column is already called out above; a lone empty cell is the
    // surprising one, so it gets to be the loudest thing on screen.
    color: columnDead ? 'var(--text-secondary)' : 'var(--on-accent, #fff)',
    background: columnDead ? 'transparent' : 'var(--accent-red, #ef4444)',
  }
}

// ── 3. flow ─────────────────────────────────────────────────────────

function FlowView({ bidsDir }: { bidsDir: string }) {
  const { data, error, loading } = useAsync<ConvertFlow>(
    () => fetchConvertFlow(bidsDir), [bidsDir])

  if (loading) return <div style={hintStyle}>Aggregating…</div>
  if (error) return <Missing error={error} />
  if (!data || !data.links.length) return <div style={hintStyle}>Nothing to show.</div>

  const max = Math.max(...data.links.map(l => l.value))
  const droppedFrac = data.n_series ? data.n_dropped / data.n_series : 0

  return (
    <>
      <div style={subHeaderStyle}>
        {data.n_series} series across the study ·{' '}
        <strong style={{
          color: droppedFrac > 0.25 ? 'var(--accent-yellow, #e2a832)' : 'inherit',
        }}>
          {data.n_dropped} dropped ({(droppedFrac * 100).toFixed(0)}%)
        </strong>
      </div>

      <div style={{ padding: '10px 12px' }}>
        {data.links.map(l => {
          const isDropped = l.target === '— dropped —'
          return (
            <div key={`${l.source}->${l.target}`} style={flowRowStyle}>
              <div style={flowLabelStyle} title={l.source}>{l.source}</div>
              <div style={flowBarTrack}>
                <div style={{
                  ...flowBarStyle,
                  width: `${(l.value / max) * 100}%`,
                  background: isDropped
                    ? 'var(--accent-yellow, #e2a832)'
                    : 'var(--accent-cyan, #0891b2)',
                }} />
              </div>
              <div style={{
                ...flowLabelStyle,
                color: isDropped ? 'var(--accent-yellow, #e2a832)' : undefined,
              }}>
                {l.target}
              </div>
              <div style={{ width: 34, textAlign: 'right', fontFamily: 'monospace' }}>
                {l.value}
              </div>
            </div>
          )
        })}
      </div>

      <div style={footnoteStyle}>
        Aggregated across the study — protocol → datatype → suffix. Deliberately
        not per-series: at that granularity it is unreadable. Its one job is
        making the dropped ribbon large enough to notice.
      </div>
    </>
  )
}

// ── shared ──────────────────────────────────────────────────────────

function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fn()
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { data, error, loading }
}

/** Absent provenance is ordinary, not a failure. */
function Missing({ error }: { error: string }) {
  const missing = error.includes('404')
  return (
    <div style={hintStyle}>
      {missing
        ? 'No conversion provenance for this dataset — it was not produced by heudiconv, or .heudiconv was removed.'
        : `Could not read it: ${error}`}
    </div>
  )
}

const fmt = (v: number | null) => (v == null ? '—' : v < 10 ? v.toFixed(2) : v.toFixed(0))
const ruleName = (r: string) => r.split('/').pop()!.replace('sub-{subject}_', '')

// ── styles ──────────────────────────────────────────────────────────

const boxStyle: CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 6, marginTop: 12, overflow: 'hidden',
}
const headerStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
  borderBottom: '1px solid var(--border)', fontSize: 11, fontWeight: 700,
  textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--accent-cyan)',
}
const tabStyle = (on: boolean): CSSProperties => ({
  padding: '3px 10px', fontSize: 10, fontWeight: 700, borderRadius: 4,
  textTransform: 'uppercase', letterSpacing: 0.5, cursor: 'pointer',
  background: on ? 'var(--accent-cyan, #0891b2)' : 'var(--bg-card)',
  color: on ? 'var(--on-accent, #fff)' : 'var(--text-secondary)',
  border: `1px solid ${on ? 'var(--accent-cyan, #0891b2)' : 'var(--border)'}`,
})
const subHeaderStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6, padding: '7px 12px',
  borderBottom: '1px solid var(--border)', fontSize: 11, color: 'var(--text-secondary)',
}
const warnBoxStyle: CSSProperties = {
  padding: '8px 12px', borderBottom: '1px solid var(--border)',
  background: 'var(--bg-elevated, rgba(226,168,50,0.08))',
}
const warnRowStyle: CSSProperties = {
  fontSize: 11, color: 'var(--accent-yellow, #e2a832)', marginBottom: 4,
}
const tableStyle: CSSProperties = { width: '100%', borderCollapse: 'collapse', fontSize: 11 }
const thStyle: CSSProperties = {
  textAlign: 'left', padding: '6px 12px', color: 'var(--text-secondary)',
  fontWeight: 600, textTransform: 'uppercase', fontSize: 10, letterSpacing: 0.5,
  borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap',
}
const tdStyle: CSSProperties = {
  padding: '5px 12px', color: 'var(--text-primary)',
  borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap', verticalAlign: 'top',
}
const numCell: CSSProperties = { ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }
const droppedRowStyle: CSSProperties = { opacity: 0.55 }
const mutedStyle: CSSProperties = { color: 'var(--text-secondary)' }
const chipStyle: CSSProperties = {
  marginLeft: 6, padding: '1px 5px', borderRadius: 3, fontSize: 9,
  border: '1px solid var(--border)', color: 'var(--text-secondary)',
}
const flowRowStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, marginBottom: 3,
}
const flowLabelStyle: CSSProperties = {
  width: 190, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  fontFamily: 'monospace', fontSize: 10, color: 'var(--text-primary)',
}
const flowBarTrack: CSSProperties = { flex: 1, height: 12, background: 'var(--bg-card)' }
const flowBarStyle: CSSProperties = { height: '100%', borderRadius: 2 }
const footnoteStyle: CSSProperties = {
  padding: '6px 12px', fontSize: 10, color: 'var(--text-secondary)', opacity: 0.85,
  borderTop: '1px solid var(--border)',
}
const hintStyle: CSSProperties = {
  fontSize: 11, color: 'var(--text-secondary)', padding: '10px 12px',
}
