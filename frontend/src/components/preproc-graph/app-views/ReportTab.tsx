/** The app's subject HTML report (fmriprep's sub-XX.html), run-scoped. */
import type { NodePopupContext } from './index'
import { runNodeReportUrl } from '../../../api/preproc'
import { fill, muted } from './shared'

export function ReportTab({ ctx }: { ctx: NodePopupContext }) {
  const port = ctx.record.ui.report
  if (!port || !ctx.record.outputs[port]) return <div style={muted}>No report yet{ctx.isRunning ? ' — it appears when the app finishes' : ''}.</div>
  return (
    <div style={{ ...fill, overflow: 'hidden' }}>
      <iframe title="report" src={runNodeReportUrl(ctx.runId, ctx.nodeId)} style={{ flex: 1, width: '100%', border: 'none', background: '#fff' }} />
    </div>
  )
}
