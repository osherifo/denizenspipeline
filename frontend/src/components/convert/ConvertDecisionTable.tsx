/**
 * What the heuristic did with every DICOM series it saw.
 *
 * A conversion is a lossy decision and the discarded set is often the
 * interesting one — a heuristic that keeps only the MP2RAGE uniform image
 * throws away the inversions needed to correct that image later, and nothing
 * used to surface that.
 *
 * Reconstructed server-side from the provenance heudiconv leaves behind, so
 * this works on any already-converted dataset without re-running anything.
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'

import { fetchConvertDecisionTable } from '../../api/client'
import type { ConvertDecisionTable as TableData } from '../../api/types'

interface Props {
  bidsDir: string
  subject: string
  /** Start collapsed when embedded somewhere already dense. */
  defaultOpen?: boolean
}

export function ConvertDecisionTable({ bidsDir, subject, defaultOpen = true }: Props) {
  const [data, setData] = useState<TableData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(defaultOpen)
  const [showDropped, setShowDropped] = useState(true)

  useEffect(() => {
    if (!bidsDir || !subject) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchConvertDecisionTable(bidsDir, subject)
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [bidsDir, subject])

  if (loading) return <div style={hintStyle}>Reading conversion provenance…</div>

  if (error) {
    // Absent provenance is ordinary, not a failure: the dataset may not have
    // come from heudiconv at all.
    const missing = error.includes('404')
    return (
      <div style={hintStyle}>
        {missing
          ? 'No conversion provenance for this dataset — it was not produced by heudiconv, or .heudiconv was removed.'
          : `Could not read the decision table: ${error}`}
      </div>
    )
  }
  if (!data) return null

  const rows = showDropped ? data.series : data.series.filter(s => !s.dropped)

  return (
    <div style={boxStyle}>
      <div style={headerStyle} onClick={() => setOpen(o => !o)}>
        <span>{open ? '▾' : '▸'} DICOM → BIDS decisions</span>
        <span style={summaryStyle}>
          {data.n_series} series in ·{' '}
          <strong style={{ color: 'var(--accent-green, #10b981)' }}>{data.n_mapped} mapped</strong> ·{' '}
          <strong style={{ color: data.n_dropped ? 'var(--accent-yellow, #e2a832)' : 'inherit' }}>
            {data.n_dropped} dropped
          </strong>
        </span>
      </div>

      {open && (
        <>
          {data.warnings.length > 0 && (
            <div style={warnBoxStyle}>
              {data.warnings.map((w, i) => (
                <div key={i} style={warnRowStyle}>⚠ {w}</div>
              ))}
            </div>
          )}

          <div style={controlRowStyle}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <input
                type="checkbox"
                checked={showDropped}
                onChange={e => setShowDropped(e.target.checked)}
              />
              show dropped series
            </label>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  {['series', 'description', 'files', 'dims', 'TR', '→ output'].map(h => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(s => (
                  <tr key={s.series_id} style={s.dropped ? droppedRowStyle : undefined}>
                    <td style={{ ...tdStyle, fontFamily: 'monospace' }}>{s.series_id}</td>
                    <td style={tdStyle}>
                      {s.description}
                      {s.is_derived && <span style={chipStyle}>derived</span>}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>{s.n_files}</td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                      {s.dims.filter(d => d > 0).join('×')}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>
                      {s.tr != null ? s.tr : '—'}
                    </td>
                    <td style={tdStyle}>
                      {s.dropped
                        ? <span style={droppedTagStyle}>— dropped —</span>
                        : <span style={{ fontFamily: 'monospace', fontSize: 10 }}>
                            {outputName(s.output_template!)}
                          </span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={footnoteStyle}>
            heudiconv records what the heuristic claimed, not why it passed over
            the rest — so “dropped” means unclaimed, without a stated reason.
          </div>
        </>
      )}
    </div>
  )
}

/** Templates are full BIDS paths; the filename carries the information. */
function outputName(template: string): string {
  return template.split('/').pop()!.replace('sub-{subject}_', '')
}

// ── styles ──────────────────────────────────────────────────────────

const boxStyle: CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 6,
  marginTop: 12, overflow: 'hidden',
}
const headerStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer',
  padding: '8px 12px', borderBottom: '1px solid var(--border)',
  fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
  letterSpacing: 0.5, color: 'var(--accent-cyan)',
}
const summaryStyle: CSSProperties = {
  marginLeft: 'auto', fontSize: 11, fontWeight: 400,
  textTransform: 'none', letterSpacing: 0, color: 'var(--text-secondary)',
}
const warnBoxStyle: CSSProperties = {
  padding: '8px 12px', borderBottom: '1px solid var(--border)',
  background: 'var(--bg-elevated, rgba(226,168,50,0.08))',
}
const warnRowStyle: CSSProperties = {
  fontSize: 11, color: 'var(--accent-yellow, #e2a832)', marginBottom: 4,
}
const controlRowStyle: CSSProperties = {
  padding: '6px 12px', fontSize: 11, color: 'var(--text-secondary)',
  borderBottom: '1px solid var(--border)',
}
const tableStyle: CSSProperties = {
  width: '100%', borderCollapse: 'collapse', fontSize: 11,
}
const thStyle: CSSProperties = {
  textAlign: 'left', padding: '6px 12px', color: 'var(--text-secondary)',
  fontWeight: 600, textTransform: 'uppercase', fontSize: 10,
  letterSpacing: 0.5, borderBottom: '1px solid var(--border)',
  whiteSpace: 'nowrap',
}
const tdStyle: CSSProperties = {
  padding: '5px 12px', color: 'var(--text-primary)',
  borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap',
}
const droppedRowStyle: CSSProperties = { opacity: 0.55 }
const droppedTagStyle: CSSProperties = {
  color: 'var(--text-secondary)', fontStyle: 'italic', fontSize: 10,
}
const chipStyle: CSSProperties = {
  marginLeft: 6, padding: '1px 5px', borderRadius: 3, fontSize: 9,
  border: '1px solid var(--border)', color: 'var(--text-secondary)',
}
const footnoteStyle: CSSProperties = {
  padding: '6px 12px', fontSize: 10, color: 'var(--text-secondary)', opacity: 0.8,
}
const hintStyle: CSSProperties = {
  fontSize: 11, color: 'var(--text-secondary)', padding: '8px 0',
}
