/** The node's nipype work dir: files render inline by type. */
import type { NodePopupContext } from './index'
import { NodeOutputsPanel } from '../../workflow/NodeOutputsPanel'
import { fill } from './shared'

export function OutputsTab({ ctx }: { ctx: NodePopupContext }) {
  const path = ctx.record.workflow ? `${ctx.record.workflow}.${ctx.nodeId}` : ctx.nodeId
  return (
    <div style={{ ...fill, overflow: 'hidden' }}>
      <NodeOutputsPanel runId={ctx.runId} node={path} variant="inline" />
    </div>
  )
}
