/** Generic manifest facts for any node that produces one. */
import type { NodePopupContext } from './index'
import { useNodeManifest } from './useNodeManifest'
import { muted, pad, table, td } from './shared'

export function SummaryTab({ ctx }: { ctx: NodePopupContext }) {
  const { manifest, error } = useNodeManifest(ctx.runId, ctx.nodeId, ctx.isRunning)
  if (error) return <div style={muted}>Not available yet{ctx.isRunning ? ' — the node has not written its manifest' : ''}. ({error})</div>
  if (!manifest) return <div style={muted}>Loading…</div>
  const rows: [string, unknown][] = [
    ['subject', manifest.subject], ['dataset', manifest.dataset], ['backend', `${manifest.backend} ${manifest.backend_version ?? ''}`],
    ['space', `${manifest.space ?? ''} ${manifest.resolution ? `(${manifest.resolution})` : ''}`], ['runs', manifest.runs?.length ?? 0],
    ['output dir', manifest.output_dir], ['created', manifest.created],
  ]
  return (
    <div style={pad}>
      <table style={table}><tbody>{rows.map(([k, v]) => <tr key={k}><td style={{ ...td, width: 140 }}>{k}</td><td style={td}>{String(v ?? '—')}</td></tr>)}</tbody></table>
    </div>
  )
}
