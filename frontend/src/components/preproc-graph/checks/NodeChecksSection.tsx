/** The Checks part of a node's panel: its built-in checks (toggle), plus checks written
 *  here on the pipeline node — an artifact template, a registered metric, optional bounds —
 *  with a Try button that evaluates the check against a finished run's node. */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type { BuiltinCheckInfo, CheckDef, CheckEvaluation, MetricInfo, PipelineNodeDoc, PipelineRunSummary } from '../../../api/types'
import { evaluateCheck, fetchCheckMetrics, fetchNodeChecks, fetchPipelineRuns } from '../../../api/preproc'
import { usePreprocPipelineStore } from '../../../stores/preproc-pipeline-store'
import { formatBounds, parseBounds } from './bounds'

const h: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', margin: '4px 0' }
const input: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '4px 6px', borderRadius: 4, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'inherit',
}
const mono: CSSProperties = { ...input, fontFamily: 'monospace' }
const btn: CSSProperties = { ...input, width: 'auto', cursor: 'pointer', padding: '3px 8px' }
const card: CSSProperties = { border: '1px solid var(--border)', borderRadius: 6, padding: 8, marginBottom: 6, display: 'flex', flexDirection: 'column', gap: 4 }
const small: CSSProperties = { fontSize: 10, color: 'var(--text-secondary)' }
const VERDICT: Record<string, string> = { ok: '#10b981', suspicious: '#f59e0b', bad: '#ef4444', unknown: '#9ca3af' }

interface Props { node: PipelineNodeDoc }

export function NodeChecksSection({ node }: Props) {
  const updateNodeData = usePreprocPipelineStore((s) => s.updateNodeData)
  const pipelineName = usePreprocPipelineStore((s) => s.pipeline.name)
  const [builtin, setBuiltin] = useState<BuiltinCheckInfo[]>([])
  const [metrics, setMetrics] = useState<MetricInfo[]>([])
  const [runs, setRuns] = useState<PipelineRunSummary[]>([])
  const entries: CheckDef[] = node.data.checks ?? []

  useEffect(() => {
    let cancelled = false
    fetchNodeChecks(node.type).then((r) => { if (!cancelled) setBuiltin(r.checks) }).catch(() => setBuiltin([]))
    fetchCheckMetrics().then((r) => { if (!cancelled) setMetrics(r.metrics) }).catch(() => {})
    return () => { cancelled = true }
  }, [node.type])

  const isUser = (e: CheckDef) => e.enabled !== false && Boolean(e.artifact || e.metric)
  // Edits read the live node from the store rather than the prop, so two quick edits
  // (artifact, then bounds) never clobber each other while the parent re-renders.
  const live = (): CheckDef[] => usePreprocPipelineStore.getState().pipeline.nodes.find((n) => n.id === node.id)?.data.checks ?? entries
  const setEntries = (next: CheckDef[]) => updateNodeData(node.id, { checks: next.length ? next : undefined })
  const disabled = new Set(entries.filter((e) => e.enabled === false).map((e) => e.step))
  const userEntries = entries.filter(isUser)

  const toggleBuiltin = (step: string, on: boolean) => {
    const rest = live().filter((e) => e.step !== step || e.enabled !== false)
    setEntries(on ? rest : [...rest, { step, enabled: false }])
  }
  const updateEntry = (i: number, patch: Partial<CheckDef>) => {
    const all = live()
    const target = all.filter(isUser)[i]
    setEntries(all.map((e) => (e === target ? { ...e, ...patch } : e)))
  }
  const removeEntry = (i: number) => { const all = live(); const target = all.filter(isUser)[i]; setEntries(all.filter((e) => e !== target)) }
  const addEntry = () => { const all = live(); setEntries([...all, { step: `check_${all.filter(isUser).length + 1}`, artifact: '{node_dir}/', metric: 'nifti_stats', live: true }]) }

  const loadRuns = () => fetchPipelineRuns().then((r) => setRuns(r.runs.filter((x) => x.status === 'done' || x.status === 'failed'))).catch(() => {})

  return (
    <div>
      <div style={h}>Checks</div>
      {builtin.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          {builtin.map((c) => (
            <label key={c.step} style={{ display: 'flex', gap: 6, alignItems: 'baseline', fontSize: 11, marginBottom: 2 }} title={c.artifact}>
              <input type="checkbox" checked={!disabled.has(c.step)} onChange={(e) => toggleBuiltin(c.step, e.target.checked)} />
              <span style={{ fontFamily: 'monospace' }}>{c.step}</span>
              <span style={small}>{c.metric ?? 'custom'}{c.live ? ' · live' : ''}</span>
            </label>
          ))}
          <div style={small}>Built into the node. Thresholds are in Library → Checkpoint norms; untick to skip one.</div>
        </div>
      )}
      {userEntries.map((e, i) => (
        <CheckEditor key={i} entry={e} metrics={metrics} runs={runs} nodeId={node.id} pipelineName={pipelineName}
          onLoadRuns={loadRuns} onChange={(patch) => updateEntry(i, patch)} onRemove={() => removeEntry(i)} />
      ))}
      <button style={btn} onClick={addEntry}>+ Add check</button>
      <div style={{ ...small, marginTop: 4 }}>
        Artifact placeholders: <code>{'{node_dir}'}</code>, <code>{'{subject}'}</code>, any output port (<code>{'{out_file}'}</code>) and, for apps, <code>{'{fs_subject_dir}'}</code>, <code>{'{derivatives_dir}'}</code>.
      </div>
    </div>
  )
}

function CheckEditor({ entry, metrics, runs, nodeId, pipelineName, onLoadRuns, onChange, onRemove }: {
  entry: CheckDef; metrics: MetricInfo[]; runs: PipelineRunSummary[]; nodeId: string; pipelineName: string
  onLoadRuns: () => void; onChange: (patch: Partial<CheckDef>) => void; onRemove: () => void
}) {
  const [hardText, setHardText] = useState(formatBounds(entry.norms?.hard))
  const [softText, setSoftText] = useState(formatBounds(entry.norms?.soft))
  const [runId, setRunId] = useState('')
  const [result, setResult] = useState<CheckEvaluation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const hard = useMemo(() => parseBounds(hardText), [hardText])
  const soft = useMemo(() => parseBounds(softText), [softText])
  const commitBounds = () => {
    if (hard.errors.length || soft.errors.length) return
    const norms: CheckDef['norms'] = {}
    if (Object.keys(hard.bounds).length) norms.hard = hard.bounds
    if (Object.keys(soft.bounds).length) norms.soft = soft.bounds
    onChange({ norms: Object.keys(norms).length ? norms : undefined })
  }
  const tryIt = async () => {
    if (!runId) return
    setError(null); setResult(null)
    try { setResult(await evaluateCheck(entry, runId, nodeId)) } catch (e) { setError((e as Error).message) }
  }
  const sameRuns = runs.filter((r) => r.pipeline === pipelineName)
  const shown = sameRuns.length ? sameRuns : runs
  return (
    <div style={card}>
      <div style={{ display: 'flex', gap: 6 }}>
        <input style={{ ...mono, flex: 1 }} value={entry.step} onChange={(e) => onChange({ step: e.target.value })} placeholder="step name" aria-label="step" />
        <select style={{ ...input, width: 'auto' }} value={entry.metric ?? 'nifti_stats'} onChange={(e) => onChange({ metric: e.target.value })} aria-label="metric" title={metrics.find((m) => m.name === entry.metric)?.description}>
          {(metrics.length ? metrics : [{ name: 'nifti_stats', description: '', builtin: true }]).map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
        </select>
        <label style={{ ...small, display: 'flex', gap: 3, alignItems: 'center' }}><input type="checkbox" checked={entry.live !== false} onChange={(e) => onChange({ live: e.target.checked })} /> live</label>
        <button style={btn} onClick={onRemove} title="remove this check">✕</button>
      </div>
      <input style={mono} value={entry.artifact ?? ''} onChange={(e) => onChange({ artifact: e.target.value })} placeholder="artifact, e.g. {fs_subject_dir}/mri/aseg.mgz" aria-label="artifact" />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        <div>
          <div style={small}>bad when (hard)</div>
          <textarea style={{ ...mono, minHeight: 34 }} value={hardText} onChange={(e) => setHardText(e.target.value)} onBlur={commitBounds} placeholder={'n_trs > 100\nmean between 50 500'} aria-label="hard bounds" />
          {hard.errors.map((x) => <div key={x} style={{ ...small, color: '#ef4444' }}>{x}</div>)}
        </div>
        <div>
          <div style={small}>suspicious when (soft)</div>
          <textarea style={{ ...mono, minHeight: 34 }} value={softText} onChange={(e) => setSoftText(e.target.value)} onBlur={commitBounds} placeholder="nonzero_fraction > 0.05" aria-label="soft bounds" />
          {soft.errors.map((x) => <div key={x} style={{ ...small, color: '#ef4444' }}>{x}</div>)}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <select style={{ ...input, flex: 1 }} value={runId} onFocus={() => { if (!runs.length) onLoadRuns() }} onChange={(e) => setRunId(e.target.value)} aria-label="run to try on">
          <option value="">try on a finished run…</option>
          {shown.map((r) => <option key={r.run_id} value={r.run_id}>{r.run_id} · sub-{r.subject} · {r.pipeline} · {r.status}</option>)}
        </select>
        <button style={btn} onClick={tryIt} disabled={!runId}>Try</button>
      </div>
      {error && <div style={{ ...small, color: '#ef4444' }}>{error}</div>}
      {result && !result.exists && <div style={{ ...small, color: '#f59e0b' }}>not found: <code>{result.artifact}</code></div>}
      {result?.checkpoint && (
        <div style={{ fontSize: 11 }}>
          <span style={{ color: VERDICT[result.checkpoint.verdict], fontWeight: 700, textTransform: 'uppercase' }}>{result.checkpoint.verdict}</span>
          {result.checkpoint.reasons.length > 0 && <span style={small}> · {result.checkpoint.reasons.join('; ')}</span>}
          <pre style={{ margin: '4px 0 0', fontSize: 10, maxHeight: 120, overflow: 'auto', background: 'var(--bg-primary)', padding: 6, borderRadius: 4 }}>{JSON.stringify(result.checkpoint.metrics, null, 1)}</pre>
        </div>
      )}
    </div>
  )
}
