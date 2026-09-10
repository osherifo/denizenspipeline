/** Checkpoint frames for a run: verdict colour, key metrics, thumbnail, reasons on hover/click. */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { checkpointThumbnailUrl } from '../../api/preproc'
import type { CheckpointRecord } from '../../api/types'

export const VERDICT_COLORS: Record<string, string> = {
  ok: '#10b981', suspicious: '#f59e0b', bad: '#ef4444', unknown: '#9ca3af',
}

// The strip scrolls inside its host instead of widening it: the host gets
// minWidth 0 (a grid/flex child otherwise sizes to the cards' total width)
// and the cards refuse to shrink so they stay readable.
const host: CSSProperties = { minWidth: 0, maxWidth: '100%' }
const strip: CSSProperties = { display: 'flex', gap: 8, overflowX: 'auto', padding: '6px 2px' }
const frame = (verdict: string, open: boolean): CSSProperties => ({
  minWidth: 150, flexShrink: 0, border: `1px solid ${VERDICT_COLORS[verdict] ?? '#9ca3af'}`, borderTop: `4px solid ${VERDICT_COLORS[verdict] ?? '#9ca3af'}`,
  borderRadius: 6, background: 'var(--bg-card)', padding: 8, fontSize: 11, cursor: 'pointer',
  boxShadow: open ? `0 0 8px ${VERDICT_COLORS[verdict]}66` : undefined,
})

function keyMetrics(cp: CheckpointRecord): [string, string][] {
  const prefer = ['modal_fraction', 'n_unique', 'n_defects', 'mean_mm', 'zero_fraction', 'wm_volume_cm3', 'brain_volume_cm3', 'etiv_cm3', 'n_trs', 'is_4d', 'nonzero_fraction', 'exists']
  const out: [string, string][] = []
  for (const k of prefer) {
    if (k in cp.metrics) {
      const v = cp.metrics[k]
      out.push([k, typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(3)) : String(v)])
    }
    if (out.length >= 3) break
  }
  return out
}

interface Props {
  runId: string
  checkpoints: CheckpointRecord[]
  nodeFilter?: string | null
}

export function CheckpointFilmstrip({ runId, checkpoints, nodeFilter }: Props) {
  const [open, setOpen] = useState<number | null>(null)
  const rows = checkpoints.map((cp, i) => ({ cp, i })).filter(({ cp }) => !nodeFilter || cp.node.endsWith(`.${nodeFilter}`) || cp.node === nodeFilter)
  if (rows.length === 0) {
    return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: '6px 2px' }}>No checkpoints yet.</div>
  }
  const openRow = open !== null ? rows.find((r) => r.i === open) : null
  return (
    <div style={host}>
      <div style={strip}>
        {rows.map(({ cp, i }) => (
          <div key={i} style={frame(cp.verdict, open === i)} onClick={() => setOpen(open === i ? null : i)} title={cp.reasons.join('\n')}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6 }}>
              <span style={{ fontWeight: 700 }}>{cp.step}</span>
              <span style={{ color: VERDICT_COLORS[cp.verdict], fontWeight: 700, textTransform: 'uppercase', fontSize: 9, letterSpacing: 0.5 }}>{cp.verdict}</span>
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 10, marginBottom: 4 }}>{cp.node.split('.').slice(-1)[0]}</div>
            {cp.artifact && /\.(nii|nii\.gz|mgz|mgh)$/i.test(cp.artifact) && (
              <img
                src={checkpointThumbnailUrl(runId, i)}
                alt=""
                style={{ width: '100%', height: 70, objectFit: 'contain', background: '#000', borderRadius: 4, marginBottom: 4 }}
                onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
              />
            )}
            {keyMetrics(cp).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'monospace', fontSize: 10 }}>
                <span style={{ color: 'var(--text-secondary)' }}>{k}</span><span>{v}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
      {openRow && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 10, fontSize: 11, background: 'var(--bg-card)' }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{openRow.cp.step} · <span style={{ color: VERDICT_COLORS[openRow.cp.verdict] }}>{openRow.cp.verdict}</span></div>
          {openRow.cp.reasons.length > 0 && <ul style={{ margin: '0 0 6px 16px', padding: 0 }}>{openRow.cp.reasons.map((r, j) => <li key={j}>{r}</li>)}</ul>}
          <div style={{ color: 'var(--text-secondary)', wordBreak: 'break-all', marginBottom: 6 }}>{openRow.cp.artifact}</div>
          <table style={{ borderCollapse: 'collapse', fontFamily: 'monospace', fontSize: 10 }}>
            <tbody>
              {Object.entries(openRow.cp.metrics).filter(([k]) => k !== 'shape').map(([k, v]) => {
                const hard = openRow.cp.expectations[k]
                const soft = openRow.cp.soft_expectations[k]
                return (
                  <tr key={k}>
                    <td style={{ paddingRight: 12, color: 'var(--text-secondary)' }}>{k}</td>
                    <td style={{ paddingRight: 12 }}>{typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(4)) : String(v)}</td>
                    <td style={{ color: 'var(--text-secondary)' }}>{hard ? `bad unless ${hard[0]} ${JSON.stringify(hard[1])}` : ''}{soft ? ` · suspicious unless ${soft[0]} ${JSON.stringify(soft[1])}` : ''}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
