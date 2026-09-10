/** fmriprep's friendly summary: space, runs with QC badges, confounds. */
import type { NodePopupContext } from './index'
import { ManifestSummary } from '../../preproc/ManifestSummary'
import { useNodeManifest } from './useNodeManifest'
import { muted, pad } from './shared'

export function FmriprepSummaryTab({ ctx }: { ctx: NodePopupContext }) {
  const { manifest, error } = useNodeManifest(ctx.runId, ctx.nodeId, ctx.isRunning)
  if (error) return <div style={muted}>Not available yet{ctx.isRunning ? ' — fmriprep has not finished' : ''}. ({error})</div>
  if (!manifest) return <div style={muted}>Loading…</div>
  return <div style={pad}><ManifestSummary manifest={manifest} /></div>
}
