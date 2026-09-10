/** The app's own stdout (`<node dir>/stdout.log`), tailed while the run is live. */
import { useEffect, useState } from 'react'
import type { NodePopupContext } from './index'
import { fetchRunNodeLog } from '../../../api/preproc'
import { fill, pre } from './shared'

export function LogTab({ ctx }: { ctx: NodePopupContext }) {
  const [lines, setLines] = useState<string[]>([])
  const [total, setTotal] = useState(0)
  useEffect(() => {
    let cancelled = false
    const load = () => fetchRunNodeLog(ctx.runId, ctx.nodeId, 500)
      .then((r) => { if (!cancelled) { setLines(r.lines); setTotal(r.total) } })
      .catch(() => {})
    void load()
    if (!ctx.isRunning) return () => { cancelled = true }
    const id = setInterval(load, 2000)
    return () => { cancelled = true; clearInterval(id) }
  }, [ctx.runId, ctx.nodeId, ctx.isRunning])
  return (
    <div style={{ ...fill, padding: 12 }}>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>stdout.log · last {lines.length} of {total} lines</div>
      <pre style={pre}>{lines.length ? lines.join('\n') : '(no output yet)'}</pre>
    </div>
  )
}
