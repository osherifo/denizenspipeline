/** FreeSurfer surfaces, the report, and the review/sign-off form — for this run's node. */
import type { NodePopupContext } from './index'
import { StructuralQCPanel } from '../../preproc/StructuralQCPanel'
import { muted, pad } from './shared'

export function StructuralQCTab({ ctx }: { ctx: NodePopupContext }) {
  const port = ctx.record.ui.structural_qc
  if (!port || !ctx.record.outputs[port]) return <div style={muted}>No FreeSurfer outputs yet{ctx.isRunning ? ' — they appear as recon-all finishes' : ''}.</div>
  return (
    <div style={pad}>
      <StructuralQCPanel source={{ kind: 'run', runId: ctx.runId, nodeId: ctx.nodeId, subject: ctx.record.subject, dataset: ctx.record.dataset }} reportHeight={700} />
    </div>
  )
}
