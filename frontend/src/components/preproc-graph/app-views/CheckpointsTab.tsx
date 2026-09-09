import type { NodePopupContext } from './index'
import { CheckpointFilmstrip } from '../CheckpointFilmstrip'
import { muted, pad } from './shared'

export function CheckpointsTab({ ctx }: { ctx: NodePopupContext }) {
  const mine = ctx.checkpoints.filter((cp) => cp.node === ctx.nodeId || cp.node.endsWith(`.${ctx.nodeId}`))
  if (mine.length === 0) return <div style={muted}>No checkpoints recorded for this node{ctx.isRunning ? ' yet' : ''}.</div>
  return (
    <div style={pad}>
      <CheckpointFilmstrip runId={ctx.runId} checkpoints={ctx.checkpoints} nodeFilter={ctx.nodeId} />
    </div>
  )
}
