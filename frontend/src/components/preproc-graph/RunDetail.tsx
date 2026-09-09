/** One pipeline run: graph with live status, checkpoints, node outputs, events, log, actions. */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocRunsStore } from '../../stores/preproc-runs-store'
import { usePreprocPipelineStore } from '../../stores/preproc-pipeline-store'
import { PipelineGraph, type NodeCheckpointStatus, type NodeRunStatus } from './PipelineGraph'
import { CheckpointFilmstrip, VERDICT_COLORS } from './CheckpointFilmstrip'
import { NodeOutputsPanel } from '../workflow/NodeOutputsPanel'
import { NipypeGraphModal } from '../workflow/NipypeGraphModal'
import { fetchPipelineRunLog, fetchRunCrash } from '../../api/preproc'
import { formatDuration } from '../../utils/format'
import type { CheckpointRecord, PipelineEvent, PipelineRunDetail } from '../../api/types'

const bar: CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, marginBottom: 10, flexWrap: 'wrap' }
const btn: CSSProperties = {
  padding: '5px 10px', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent',
  color: 'var(--text-primary)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
}
const section: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', margin: '12px 0 4px' }
const STATUS_COLOR: Record<string, string> = { running: '#3b82f6', done: '#10b981', failed: '#ef4444', cancelled: '#9ca3af', lost: '#f59e0b' }

export function statusOverlay(detail: PipelineRunDetail | null, events: PipelineEvent[]): Record<string, NodeRunStatus> {
  const out: Record<string, NodeRunStatus> = {}
  if (!detail) return out
  const wf = detail.workflow
  const top = (node: string | undefined) => {
    if (!node) return null
    const parts = node.split('.')
    if (wf && parts[0] === wf && parts.length >= 2) return parts[1]
    return parts.length >= 2 ? parts[1] : parts[0]
  }
  for (const n of detail.nodes) out[n.id] = { status: 'pending' }
  for (const ev of events) {
    const id = top(ev.node)
    if (!id || !(id in out)) continue
    const leafIsTop = (ev.node ?? '').split('.').length <= 2
    if (ev.event === 'node_start') out[id] = { status: 'running' }
    else if (ev.event === 'node_done' && leafIsTop) out[id] = { status: ev.cached ? 'cached' : 'ok', durationS: ev.duration_s ?? null }
    else if (ev.event === 'node_fail') out[id] = { status: 'failed' }
  }
  for (const rec of detail.result?.nodes ?? []) {
    if (rec.status !== 'pending') out[rec.node_id] = { status: rec.status, durationS: rec.duration_s }
  }
  return out
}

export function checkpointOverlay(checkpoints: CheckpointRecord[], workflow: string | null): Record<string, NodeCheckpointStatus> {
  const rank: Record<string, number> = { ok: 0, unknown: 1, suspicious: 2, bad: 3 }
  const out: Record<string, NodeCheckpointStatus> = {}
  for (const cp of checkpoints) {
    const parts = cp.node.split('.')
    const id = workflow && parts[0] === workflow && parts.length >= 2 ? parts[1] : parts[parts.length - 1]
    const cur = out[id]
    if (!cur) out[id] = { worst: cp.verdict, count: 1 }
    else out[id] = { worst: rank[cp.verdict] > rank[cur.worst] ? cp.verdict : cur.worst, count: cur.count + 1 }
  }
  return out
}

interface Props {
  compact?: boolean
}

export function RunDetail({ compact = false }: Props) {
  const detail = usePreprocRunsStore((s) => s.detail)
  const events = usePreprocRunsStore((s) => s.events)
  const checkpoints = usePreprocRunsStore((s) => s.checkpoints)
  const error = usePreprocRunsStore((s) => s.error)
  const cancel = usePreprocRunsStore((s) => s.cancel)
  const resume = usePreprocRunsStore((s) => s.resume)
  const restart = usePreprocRunsStore((s) => s.restart)
  const library = usePreprocPipelineStore((s) => s.library)
  const loadLibrary = usePreprocPipelineStore((s) => s.loadLibrary)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [showInner, setShowInner] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const [logTotal, setLogTotal] = useState<number | null>(null)
  const [showTrace, setShowTrace] = useState(false)
  const [crash, setCrash] = useState<{ name: string; text: string } | null>(null)
  const [askRecover, setAskRecover] = useState(false)

  useEffect(() => { if (library.length === 0) void loadLibrary() }, [library.length, loadLibrary])
  useEffect(() => {
    if (!showLog || !detail) return
    let cancelled = false
    const load = () => fetchPipelineRunLog(detail.run_id, 500).then((r) => { if (!cancelled) { setLog(r.lines); setLogTotal(r.total ?? null) } }).catch(() => {})
    void load()
    const id = setInterval(load, 2000)
    return () => { cancelled = true; clearInterval(id) }
  }, [showLog, detail])
  // A run that did not finish cleanly opens its log by itself; the reason is in there.
  useEffect(() => {
    setShowTrace(false); setCrash(null)
    if (detail && (detail.status === 'failed' || detail.status === 'lost')) setShowLog(true)
  }, [detail?.run_id, detail?.status])  // eslint-disable-line react-hooks/exhaustive-deps

  const statusByNode = useMemo(() => statusOverlay(detail, events), [detail, events])
  const checkpointsByNode = useMemo(() => checkpointOverlay(checkpoints, detail?.workflow ?? null), [checkpoints, detail?.workflow])

  if (!detail) return <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{error ?? 'Select a run.'}</div>

  const pipeline = detail.job?.pipeline ?? { name: detail.pipeline ?? '', inputs: {}, nodes: detail.nodes.map((n) => ({ id: n.id, type: n.type, kind: n.kind, data: { params: {} }, position: { x: 0, y: 0 } })), edges: [], manifest: {} }
  const running = detail.status === 'running'
  const recoverable = detail.status === 'lost' || detail.status === 'failed' || detail.status === 'cancelled'
  const elapsed = detail.finished_at ? detail.finished_at - detail.started_at : Date.now() / 1000 - detail.started_at
  const hasInner = (detail.nipype_status?.counts.total_seen ?? 0) > 0
  const nodeSummary = selectedNode ? detail.result?.nodes.find((n) => n.node_id === selectedNode) : null
  const innerNodePath = selectedNode && detail.workflow ? `${detail.workflow}.${selectedNode}` : selectedNode

  return (
    <div>
      <div style={bar}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{detail.pipeline ?? detail.run_id}</span>
        <span style={{ color: 'var(--text-secondary)' }}>sub-{detail.subject}</span>
        <span style={{ color: STATUS_COLOR[detail.status] ?? 'var(--text-primary)', fontWeight: 700, textTransform: 'uppercase', fontSize: 10, letterSpacing: 0.6 }}>{detail.status}</span>
        <span style={{ color: 'var(--text-secondary)' }}>{formatDuration(elapsed)}</span>
        {detail.checkpoints?.n > 0 && detail.checkpoints.worst && (
          <span style={{ color: VERDICT_COLORS[detail.checkpoints.worst], fontSize: 11 }}>● {detail.checkpoints.n} checkpoints · worst {detail.checkpoints.worst}</span>
        )}
        <span style={{ flex: 1 }} />
        {hasInner && <button style={btn} onClick={() => setShowInner(true)}>Inner DAG</button>}
        <button style={btn} onClick={() => setShowLog(!showLog)}>{showLog ? 'Hide log' : 'Log'}</button>
        {running && <button style={{ ...btn, color: '#ef4444' }} onClick={() => cancel(detail.run_id)}>Cancel</button>}
        {recoverable && <button style={btn} onClick={() => setAskRecover(true)}>Resume / Restart…</button>}
      </div>
      {(detail.cause || detail.error) && (
        <div style={{ border: '1px solid #ef4444', borderRadius: 6, padding: 10, marginBottom: 10, fontSize: 12, background: 'var(--bg-card)' }}>
          <div style={{ color: '#ef4444', fontWeight: 700, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{detail.cause ?? detail.error}</div>
          {detail.cause && detail.error && detail.cause !== detail.error && (
            <div style={{ color: 'var(--text-secondary)', marginTop: 4, whiteSpace: 'pre-wrap' }}>{detail.error}</div>
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {(detail.errors?.length ?? 0) > 0 && (
              <button style={btn} onClick={() => setShowTrace(!showTrace)}>{showTrace ? 'Hide traceback' : 'Traceback'}</button>
            )}
            {(detail.crashes?.length ?? 0) > 0 && <span style={{ color: 'var(--text-secondary)' }}>crash files:</span>}
            {detail.crashes?.map((c) => (
              <button key={c.name} style={{ ...btn, color: crash?.name === c.name ? 'var(--accent-cyan)' : undefined }} title={`${c.name} · ${c.size} bytes`}
                onClick={() => crash?.name === c.name ? setCrash(null) : fetchRunCrash(detail.run_id, c.name).then(setCrash).catch(() => {})}>
                {c.node ?? c.name}
              </button>
            ))}
          </div>
          {showTrace && (
            <pre style={{ maxHeight: 320, overflow: 'auto', fontSize: 10, background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: 8, marginTop: 8, marginBottom: 0, whiteSpace: 'pre-wrap' }}>{detail.errors.join('\n\n')}</pre>
          )}
          {crash && (
            <pre style={{ maxHeight: 320, overflow: 'auto', fontSize: 10, background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: 8, marginTop: 8, marginBottom: 0, whiteSpace: 'pre-wrap' }}>{crash.text}</pre>
          )}
        </div>
      )}
      {askRecover && (
        <div style={{ border: '1px solid var(--accent-cyan)', borderRadius: 6, padding: 10, fontSize: 12, marginBottom: 10, background: 'var(--bg-card)' }}>
          <div style={{ marginBottom: 8 }}>
            This run is <b>{detail.status}</b>. <b>Resume</b> launches the same job again and nipype skips every node whose inputs are unchanged.
            <b> Restart</b> ignores the cache and re-executes everything.
          </div>
          <button style={btn} onClick={() => { setAskRecover(false); void resume(detail.run_id) }}>Resume (keep finished nodes)</button>{' '}
          <button style={btn} onClick={() => { setAskRecover(false); void restart(detail.run_id) }}>Restart from scratch</button>{' '}
          <button style={btn} onClick={() => setAskRecover(false)}>Cancel</button>
        </div>
      )}

      <PipelineGraph
        pipeline={pipeline}
        library={library}
        statusByNode={statusByNode}
        checkpointsByNode={checkpointsByNode}
        selectedNodeId={selectedNode}
        onSelect={setSelectedNode}
        height={compact ? 300 : 380}
        fitViewKey={detail.run_id}
      />

      {selectedNode && (
        <div style={{ marginTop: 8, fontSize: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
          <b>{selectedNode}</b>
          {nodeSummary && <span style={{ color: 'var(--text-secondary)' }}>{nodeSummary.status} · {formatDuration(nodeSummary.duration_s)}</span>}
          {nodeSummary?.error && <span style={{ color: '#ef4444' }}>{nodeSummary.error}</span>}
          <span style={{ flex: 1 }} />
          <button style={btn} onClick={() => setShowLog(false)}>Outputs ▾</button>
        </div>
      )}
      {selectedNode && innerNodePath && (
        <NodeOutputsPanel runId={detail.run_id} node={innerNodePath} onClose={() => setSelectedNode(null)} />
      )}

      <div style={section}>Checkpoints</div>
      <CheckpointFilmstrip runId={detail.run_id} checkpoints={checkpoints} nodeFilter={selectedNode} />

      {showLog && (
        <>
          <div style={section}>Log <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>· stdout.log{logTotal != null ? ` · last ${Math.min(log.length, 500)} of ${logTotal} lines` : ''}</span></div>
          <pre style={{ maxHeight: 360, overflow: 'auto', fontSize: 10, background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: 8, margin: 0, whiteSpace: 'pre-wrap' }}>{log.length ? log.join('\n') : '(empty — the runner wrote nothing to stdout.log yet)'}</pre>
        </>
      )}

      {!compact && (
        <>
          <div style={section}>Events</div>
          <div style={{ maxHeight: 180, overflow: 'auto', fontSize: 11, fontFamily: 'monospace', border: '1px solid var(--border)', borderRadius: 6, padding: 6 }}>
            {events.slice(-200).map((ev, i) => (
              <div key={i} style={{ color: ev.event === 'node_fail' || ev.event === 'failed' ? '#ef4444' : ev.event === 'checkpoint' ? VERDICT_COLORS[ev.verdict ?? 'unknown'] : 'var(--text-primary)' }}>
                {new Date(((ev.t ?? ev.timestamp) ?? 0) * 1000).toLocaleTimeString()} {ev.event} {ev.leaf ?? ev.node ?? ''} {ev.step ?? ''} {ev.cached ? '(cached)' : ''} {ev.reasons?.join('; ') ?? ''}
              </div>
            ))}
          </div>
        </>
      )}

      {showInner && (
        <NipypeGraphModal runId={detail.run_id} isRunning={running} onClose={() => setShowInner(false)} />
      )}
    </div>
  )
}
