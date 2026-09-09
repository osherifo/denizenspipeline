/** One node of one run, in a modal with tabs: generic ones for every node, plus the
 *  views the node's capabilities unlock (an app's inner DAG, report, structural QC…).
 *  Self-sufficient — it fetches its own record, so any view can open it. */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type { CheckpointRecord, RunNodeRecord } from '../../api/types'
import { fetchRunCheckpoints, fetchRunNode } from '../../api/preproc'
import { formatDuration } from '../../utils/format'
import { KIND_COLORS, KIND_LABELS } from './PipelineNodeCard'
import { tabsFor, type NodePopupContext } from './app-views'

const backdrop: CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 950, display: 'flex', alignItems: 'center', justifyContent: 'center' }
const card: CSSProperties = { width: 'min(1400px, 96vw)', height: '92vh', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, display: 'flex', flexDirection: 'column', overflow: 'hidden' }
const header: CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderBottom: '1px solid var(--border)', fontSize: 12 }
const tabBar: CSSProperties = { display: 'flex', gap: 2, padding: '6px 10px 0', borderBottom: '1px solid var(--border)' }
const tabBtn = (on: boolean): CSSProperties => ({
  padding: '6px 12px', fontSize: 11, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', cursor: 'pointer', fontFamily: 'inherit',
  background: 'transparent', color: on ? 'var(--accent-cyan)' : 'var(--text-secondary)', border: 'none',
  borderBottom: `2px solid ${on ? 'var(--accent-cyan)' : 'transparent'}`, marginBottom: -1,
})
const STATUS_COLOR: Record<string, string> = { running: '#3b82f6', ok: '#10b981', done: '#10b981', cached: '#10b981', failed: '#ef4444', pending: '#9ca3af' }

interface Props {
  runId: string
  nodeId: string
  onClose: () => void
  initialTab?: string
}

export function NodePopup({ runId, nodeId, onClose, initialTab }: Props) {
  const [record, setRecord] = useState<RunNodeRecord | null>(null)
  const [checkpoints, setCheckpoints] = useState<CheckpointRecord[]>([])
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<string | null>(initialTab ?? null)

  const isRunning = record?.run_status === 'running'
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const r = await fetchRunNode(runId, nodeId)
        if (cancelled) return
        setRecord(r); setError(null)
        fetchRunCheckpoints(runId).then((c) => { if (!cancelled) setCheckpoints(c.checkpoints) }).catch(() => {})
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }
    void load()
    if (!isRunning) return () => { cancelled = true }
    const id = setInterval(load, 2000)
    return () => { cancelled = true; clearInterval(id) }
  }, [runId, nodeId, isRunning])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const ctx: NodePopupContext | null = useMemo(() => record ? { runId, nodeId, record, checkpoints, isRunning } : null, [runId, nodeId, record, checkpoints, isRunning])
  const tabs = useMemo(() => (ctx ? tabsFor(ctx) : []), [ctx])
  const active = tabs.find((t) => t.id === tab) ?? tabs[0]

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`node ${nodeId}`}>
        <div style={header}>
          <b style={{ fontSize: 14 }}>{nodeId}</b>
          {record?.kind && <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color: KIND_COLORS[record.kind] }}>{KIND_LABELS[record.kind]}</span>}
          {record && <span style={{ color: 'var(--text-secondary)' }}>{record.node_type}</span>}
          {record && <span style={{ color: STATUS_COLOR[record.status] ?? 'var(--text-primary)', fontWeight: 700, textTransform: 'uppercase', fontSize: 10, letterSpacing: 0.6 }}>{record.status}</span>}
          {record?.duration_s != null && <span style={{ color: 'var(--text-secondary)' }}>{formatDuration(record.duration_s)}</span>}
          {isRunning && <span style={{ fontSize: 10, color: '#3b82f6', fontWeight: 700 }}>LIVE</span>}
          <span style={{ flex: 1 }} />
          <code style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{runId}</code>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 16 }} aria-label="Close">✕</button>
        </div>
        {error && <div style={{ padding: 12, color: '#ef4444', fontSize: 12 }}>{error}</div>}
        {!error && !record && <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 12 }}>Loading…</div>}
        {ctx && (
          <>
            <div style={tabBar} role="tablist">
              {tabs.map((t) => (
                <button key={t.id} role="tab" aria-selected={active?.id === t.id} style={tabBtn(active?.id === t.id)} onClick={() => setTab(t.id)}>{t.label}</button>
              ))}
            </div>
            <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
              {active?.render(ctx)}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
