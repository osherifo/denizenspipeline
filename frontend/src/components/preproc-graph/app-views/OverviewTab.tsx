/** Status, timing, parameters and the outputs this node produced. */
import type { NodePopupContext } from './index'
import { formatDuration } from '../../../utils/format'
import { h, pad, table, td, th } from './shared'

const fmt = (v: unknown): string => {
  if (v == null || v === '') return '—'
  if (Array.isArray(v)) return v.length ? v.map(String).join('\n') : '[]'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export function OverviewTab({ ctx }: { ctx: NodePopupContext }) {
  const r = ctx.record
  const groups = new Map<string, [string, unknown][]>()
  for (const [k, v] of Object.entries(r.params)) {
    const g = r.params_schema[k]?.group ?? 'Parameters'
    groups.set(g, [...(groups.get(g) ?? []), [k, v]])
  }
  const ports = Object.keys(r.output_ports)
  const extra = Object.keys(r.outputs).filter((k) => !ports.includes(k))
  return (
    <div style={pad}>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        <span><b>status</b> {r.status}</span>
        <span><b>duration</b> {r.duration_s != null ? formatDuration(r.duration_s) : '—'}</span>
        <span><b>type</b> {r.node_type}{r.kind ? ` (${r.kind})` : ''}</span>
        {r.work_dir && <span><b>work dir</b> <code style={{ fontSize: 11 }}>{r.work_dir}</code></span>}
      </div>
      {r.error && <div style={{ color: '#ef4444', marginTop: 8, whiteSpace: 'pre-wrap' }}>{r.error}</div>}

      {groups.size > 0 && [...groups.entries()].map(([g, rows]) => (
        <div key={g}>
          <div style={h}>{g}</div>
          <table style={table}><tbody>
            {rows.map(([k, v]) => <tr key={k}><td style={{ ...td, width: 220 }}>{k}</td><td style={td}>{fmt(v)}</td></tr>)}
          </tbody></table>
        </div>
      ))}
      {groups.size === 0 && <div style={{ ...h }}>Parameters <span style={{ fontWeight: 400, textTransform: 'none' }}>· none set (defaults)</span></div>}

      <div style={h}>Outputs</div>
      {ports.length + extra.length === 0 ? (
        <div style={{ color: 'var(--text-secondary)' }}>nothing yet</div>
      ) : (
        <table style={table}>
          <thead><tr><th style={th}>port</th><th style={th}>kind</th><th style={th}>value</th></tr></thead>
          <tbody>
            {[...ports, ...extra].map((k) => (
              <tr key={k}>
                <td style={{ ...td, width: 160 }}>{k}</td>
                <td style={{ ...td, width: 80 }}>{r.output_ports[k]?.kind ?? ''}</td>
                <td style={{ ...td, whiteSpace: 'pre-wrap' }}>{fmt(r.outputs[k])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
