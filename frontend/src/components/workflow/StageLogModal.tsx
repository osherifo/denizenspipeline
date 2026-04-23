/** Log modal dispatched from a workflow stage node — fetches the
 *  right stage endpoint based on stage type. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  fetchConvertRun,
  fetchPreprocRun,
  fetchAutoflattenRun,
  fetchInFlightRun,
  fetchBatchStatus,
} from '../../api/client'
import type { BatchSummary } from '../../api/types'

interface StageLogModalProps {
  stage: string
  runId: string
  subjectHint?: string
  onClose: () => void
}

interface LogDetail {
  title: string
  status: string
  pid?: number | null
  startedAt?: number
  finishedAt?: number
  error?: string | null
  logPath?: string | null
  logTail?: string
  extra?: [string, string][]
}

const overlay: CSSProperties = {
  position: 'fixed', inset: 0,
  backgroundColor: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 100,
}
const modal: CSSProperties = {
  width: 'min(1000px, 92vw)', height: '85vh',
  display: 'flex', flexDirection: 'column',
  backgroundColor: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 8, padding: '16px 20px', gap: 12,
}
const metaGrid: CSSProperties = {
  display: 'grid', gridTemplateColumns: '110px 1fr',
  gap: '4px 14px', fontSize: 11,
  padding: '8px 10px', backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
}
const metaLabel: CSSProperties = {
  color: 'var(--text-secondary)', fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: 0.5, fontSize: 10,
}
const metaValue: CSSProperties = {
  color: 'var(--text-primary)', fontFamily: 'monospace',
  wordBreak: 'break-all',
}
const pre: CSSProperties = {
  flex: 1, overflow: 'auto',
  backgroundColor: 'var(--bg-secondary)', borderRadius: 6,
  padding: '10px 12px', fontSize: 10, lineHeight: 1.5,
  fontFamily: 'monospace', color: 'var(--text-primary)',
  whiteSpace: 'pre-wrap', wordBreak: 'break-all',
  margin: 0, border: '1px solid var(--border)',
}
const btn: CSSProperties = {
  padding: '4px 12px', fontSize: 10, fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)', borderRadius: 4,
  backgroundColor: 'transparent', color: 'var(--text-secondary)',
  cursor: 'pointer',
}
const errBox: CSSProperties = {
  fontSize: 11, color: 'var(--accent-red)',
  backgroundColor: 'rgba(255,23,68,0.08)',
  border: '1px solid rgba(255,23,68,0.25)',
  borderRadius: 6, padding: '8px 12px',
  fontFamily: 'monospace', whiteSpace: 'pre-wrap',
}

function statusColor(status: string): string {
  switch (status) {
    case 'running': return 'var(--accent-cyan)'
    case 'done': return 'var(--accent-green)'
    case 'failed':
    case 'cancelled':
    case 'lost': return 'var(--accent-red)'
    default: return 'var(--text-secondary)'
  }
}

function formatWhen(ts: number | null | undefined): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

async function loadByStage(stage: string, runId: string): Promise<LogDetail> {
  if (stage === 'convert') {
    const r = await fetchConvertRun(runId)
    return {
      title: `${r.subject || 'convert'} — ${r.run_id}`,
      status: r.status, pid: r.pid,
      startedAt: r.started_at, finishedAt: r.finished_at,
      error: r.error, logPath: r.log_path, logTail: r.log_tail,
      extra: [['Manifest', r.manifest_path || '-']],
    }
  }
  if (stage === 'preproc') {
    const r = await fetchPreprocRun(runId)
    return {
      title: `${r.subject || 'preproc'} — ${r.run_id}`,
      status: r.status, pid: r.pid,
      startedAt: r.started_at, finishedAt: r.finished_at,
      error: r.error, logPath: r.log_path, logTail: r.log_tail,
      extra: [['Manifest', r.manifest_path || '-']],
    }
  }
  if (stage === 'autoflatten') {
    const r = await fetchAutoflattenRun(runId) as unknown as {
      run_id: string; subject: string; status: string; pid?: number | null
      started_at?: number; finished_at?: number; error?: string | null
      log_path?: string | null; log_tail?: string
    }
    return {
      title: `${r.subject || 'autoflatten'} — ${r.run_id}`,
      status: r.status, pid: r.pid,
      startedAt: r.started_at, finishedAt: r.finished_at,
      error: r.error, logPath: r.log_path, logTail: r.log_tail,
    }
  }
  // analysis
  const r = await fetchInFlightRun(runId)
  return {
    title: `${r.experiment || r.subject || 'analysis'} — ${r.run_id}`,
    status: r.status, pid: r.pid,
    startedAt: r.started_at, finishedAt: r.finished_at,
    error: r.error, logPath: r.log_path, logTail: r.log_tail,
    extra: [
      ['Experiment', r.experiment || '-'],
      ['Output dir', r.output_dir || '-'],
    ],
  }
}

export function StageLogModal({ stage, runId, subjectHint, onClose }: StageLogModalProps) {
  // Effective target — may be swapped to a specific job's run_id when
  // the initial `runId` was a batch_id.
  const [target, setTarget] = useState(runId)
  const [batch, setBatch] = useState<BatchSummary | null>(null)
  const [detail, setDetail] = useState<LogDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const isBatchHead = stage === 'convert' && target.startsWith('batch_')

  async function load() {
    setLoading(true)
    setError(null)
    try {
      if (isBatchHead) {
        setDetail(null)
        setBatch(await fetchBatchStatus(target))
      } else {
        setBatch(null)
        setDetail(await loadByStage(stage, target))
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [stage, target])

  // Auto-refresh every 3s while the current view is "running"
  useEffect(() => {
    const running = isBatchHead
      ? (batch?.status === 'running' || (batch?.counts?.running ?? 0) > 0)
      : detail?.status === 'running'
    if (!running) return
    const id = setInterval(load, 3000)
    return () => clearInterval(id)
  }, [detail?.status, batch?.status, batch?.counts?.running, isBatchHead])

  const canGoBack = target !== runId && isBatchHead === false

  const titleText = isBatchHead
    ? `batch — ${target}`
    : (detail?.title || (loading ? 'Loading…' : target))

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{
              fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
              letterSpacing: 1, color: 'var(--text-secondary)',
            }}>
              {stage} stage{subjectHint ? ` · ${subjectHint}` : ''}
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'monospace', color: 'var(--text-primary)' }}>
              {titleText}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {canGoBack && (
              <button style={btn} onClick={() => setTarget(runId)}>← Batch</button>
            )}
            <button style={btn} onClick={load}>{loading ? '…' : 'Refresh'}</button>
            {detail?.logTail && (
              <button style={btn} onClick={() => navigator.clipboard?.writeText(detail.logTail || '')}>
                Copy
              </button>
            )}
            <button style={btn} onClick={onClose}>Close</button>
          </div>
        </div>
        {error && <div style={errBox}>{error}</div>}

        {batch && (
          <>
            <div style={metaGrid}>
              <div style={metaLabel}>Status</div>
              <div style={{ ...metaValue, color: statusColor(batch.status), textTransform: 'uppercase' }}>
                {batch.status}
              </div>
              <div style={metaLabel}>Jobs</div>
              <div style={metaValue}>
                {batch.n_jobs} total
                {' · '}
                <span style={{ color: 'var(--accent-green)' }}>{batch.counts.done} done</span>
                {' · '}
                <span style={{ color: 'var(--accent-cyan)' }}>{batch.counts.running} running</span>
                {' · '}
                <span style={{ color: 'var(--accent-red)' }}>{batch.counts.failed} failed</span>
                {' · '}
                <span style={{ color: 'var(--text-secondary)' }}>{batch.counts.queued} queued</span>
              </div>
            </div>
            <div style={{
              flex: 1, overflow: 'auto',
              backgroundColor: 'var(--bg-secondary)', borderRadius: 6,
              padding: '10px 12px', border: '1px solid var(--border)',
            }}>
              <div style={{
                fontSize: 10, fontWeight: 700, color: 'var(--text-secondary)',
                textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8,
              }}>
                Per-job logs (click to open)
              </div>
              {batch.jobs.map((j) => {
                const hasLog = !!j.run_id
                return (
                  <div
                    key={j.job_id}
                    onClick={() => { if (hasLog) setTarget(j.run_id!) }}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 80px 100px auto',
                      alignItems: 'center', gap: 10,
                      padding: '8px 10px',
                      borderBottom: '1px solid var(--border)',
                      fontSize: 11, fontFamily: 'monospace',
                      cursor: hasLog ? 'pointer' : 'default',
                      opacity: hasLog ? 1 : 0.6,
                    }}
                  >
                    <div>
                      <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                        {j.subject}{j.session ? ` · ses-${j.session}` : ''}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                        {j.run_id || j.job_id}
                      </div>
                    </div>
                    <div style={{ color: statusColor(j.status), fontWeight: 700, textTransform: 'uppercase' }}>
                      {j.status}
                    </div>
                    <div style={{ color: 'var(--text-secondary)' }}>
                      {j.finished_at
                        ? `${Math.round(j.finished_at - j.started_at)}s`
                        : j.started_at ? 'running…' : '-'}
                    </div>
                    <div style={{
                      fontSize: 9, color: hasLog ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                      letterSpacing: 0.5, fontWeight: 600,
                    }}>
                      {hasLog ? 'OPEN LOG →' : '(no log yet)'}
                    </div>
                  </div>
                )
              })}
              {batch.jobs.some((j) => j.error) && (
                <div style={{ marginTop: 10 }}>
                  <div style={{
                    fontSize: 10, fontWeight: 700, color: 'var(--text-secondary)',
                    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6,
                  }}>
                    Errors
                  </div>
                  {batch.jobs.filter((j) => j.error).map((j) => (
                    <div key={j.job_id} style={{
                      fontSize: 10, color: 'var(--accent-red)',
                      fontFamily: 'monospace', marginBottom: 4,
                    }}>
                      <b>{j.subject}:</b> {j.error}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {detail && (
          <>
            <div style={metaGrid}>
              <div style={metaLabel}>Status</div>
              <div style={{ ...metaValue, color: statusColor(detail.status), textTransform: 'uppercase' }}>
                {detail.status}
              </div>
              <div style={metaLabel}>PID</div>
              <div style={metaValue}>{detail.pid ?? '-'}</div>
              <div style={metaLabel}>Started</div>
              <div style={metaValue}>{formatWhen(detail.startedAt)}</div>
              {!!detail.finishedAt && (
                <>
                  <div style={metaLabel}>Finished</div>
                  <div style={metaValue}>{formatWhen(detail.finishedAt)}</div>
                </>
              )}
              {detail.logPath && (
                <>
                  <div style={metaLabel}>Log file</div>
                  <div style={metaValue}>{detail.logPath}</div>
                </>
              )}
              {(detail.extra || []).map(([k, v]) => (
                <div key={k} style={{ display: 'contents' }}>
                  <div style={metaLabel}>{k}</div>
                  <div style={metaValue}>{v}</div>
                </div>
              ))}
              {detail.error && (
                <>
                  <div style={metaLabel}>Error</div>
                  <div style={{ ...metaValue, color: 'var(--accent-red)' }}>{detail.error}</div>
                </>
              )}
            </div>
            <pre style={pre}>
              {detail.logTail && detail.logTail.length > 0
                ? detail.logTail
                : '(log empty — the subprocess may not have written anything yet, or its output went elsewhere)'}
            </pre>
          </>
        )}
      </div>
    </div>
  )
}
