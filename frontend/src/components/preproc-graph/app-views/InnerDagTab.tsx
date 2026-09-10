/** The app's own nipype workflow (fmriprep's recon-all, BOLD fit, …), live while it runs. */
import { useEffect, useState } from 'react'
import type { NodePopupContext } from './index'
import { NipypeDagPanel } from '../../workflow/NipypeDagPanel'
import { fetchRunNodeManifest } from '../../../api/preproc'
import { fill } from './shared'

export function InnerDagTab({ ctx }: { ctx: NodePopupContext }) {
  const family = ctx.record.ui.label_map ?? null
  const [version, setVersion] = useState<string | undefined>(undefined)
  // Friendly-label map version follows the app version the node recorded, when it has a manifest.
  useEffect(() => {
    if (family !== 'fmriprep' || !ctx.record.ui.summary) return
    let cancelled = false
    fetchRunNodeManifest(ctx.runId, ctx.nodeId)
      .then((m) => { const major = String(m.backend_version ?? '').split('.')[0]; if (!cancelled && /^\d+$/.test(major)) setVersion(major) })
      .catch(() => { /* embedded fallback */ })
    return () => { cancelled = true }
  }, [ctx.runId, ctx.nodeId, family, ctx.record.ui.summary])
  return (
    <div style={{ ...fill, overflow: 'hidden' }}>
      <NipypeDagPanel
        runId={ctx.runId}
        isRunning={ctx.isRunning}
        nodePath={{ workflow: ctx.record.workflow, nodeId: ctx.nodeId }}
        labelFamily={family}
        labelVersion={version}
      />
    </div>
  )
}
