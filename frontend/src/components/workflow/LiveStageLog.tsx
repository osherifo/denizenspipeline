/** Live log pane for the active stage of a workflow run.
 *
 *  Active-stage resolution:
 *    - first running stage
 *    - else first failed stage
 *    - else the last stage that has a child run_id
 *
 *  For convert stages whose run_id is a batch_id, resolves to the first
 *  running (or failed, or last) job inside the batch and tails that job's
 *  stdout.log.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { WorkflowStageStatus } from '../../api/types'
import { TriageMatches } from '../triage/TriageMatches'
import {
  fetchConvertRun,
  fetchPreprocRun,
  fetchAutoflattenRun,
  fetchInFlightRun,
  fetchBatchStatus,
} from '../../api/client'

interface ResolvedTarget {
  stage: string
  runId: string
  status: string
  isBatchJob: boolean
  batchJobSubject?: string
}

interface LogPayload {
  logTail: string
  status: string
  error?: string | null
  logPath?: string | null
}

function pickActive(stages: WorkflowStageStatus[]): WorkflowStageStatus | null {
  if (!stages.length) return null
  const running = stages.find((s) => s.status === 'running')
  if (running) return running
  const failed = stages.find((s) => s.status === 'failed' || s.status === 'cancelled')
  if (failed) return failed
  // last with a run_id
  for (let i = stages.length - 1; i >= 0; i--) {
    if (stages[i].run_id) return stages[i]
  }
  return stages[stages.length - 1]
}

async function resolveTarget(stage: WorkflowStageStatus): Promise<ResolvedTarget | null> {
  if (!stage.run_id) return null
  // convert batch → pick a job
  if (stage.stage === 'convert' && stage.run_id.startsWith('batch_')) {
    try {
      const batch = await fetchBatchStatus(stage.run_id)
      const running = batch.jobs.find((j) => j.status === 'running' && j.run_id)
      const failed = batch.jobs.find((j) => j.status === 'failed' && j.run_id)
      const anyWithId = batch.jobs.filter((j) => j.run_id)
      const picked = running ?? failed ?? anyWithId[anyWithId.length - 1]
      if (picked && picked.run_id) {
        return {
          stage: 'convert',
          runId: picked.run_id,
          status: picked.status,
          isBatchJob: true,
          batchJobSubject: picked.subject + (picked.session ? ` · ses-${picked.session}` : ''),
        }
      }
      return null
    } catch {
      return null
    }
  }
  return {
    stage: stage.stage,
    runId: stage.run_id,
    status: stage.status,
    isBatchJob: false,
  }
}

async function fetchLog(stage: string, runId: string): Promise<LogPayload> {
  if (stage === 'convert') {
    const r = await fetchConvertRun(runId)
    return { logTail: r.log_tail ?? '', status: r.status, error: r.error, logPath: r.log_path }
  }
  if (stage === 'preproc') {
    const r = await fetchPreprocRun(runId)
    return { logTail: r.log_tail ?? '', status: r.status, error: r.error, logPath: r.log_path }
  }
  if (stage === 'autoflatten') {
    const r = await fetchAutoflattenRun(runId) as unknown as {
      log_tail?: string; status: string; error?: string | null; log_path?: string | null
    }
    return { logTail: r.log_tail ?? '', status: r.status, error: r.error ?? null, logPath: r.log_path ?? null }
  }
  const r = await fetchInFlightRun(runId)
  return { logTail: r.log_tail ?? '', status: r.status, error: r.error, logPath: r.log_path }
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

const panelStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '14px 18px',
  marginTop: 12,
  marginBottom: 12,
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
}

const headerRow: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
}

const titleStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const badge = (color: string): CSSProperties => ({
  fontSize: 9,
  fontWeight: 700,
  padding: '2px 8px',
  borderRadius: 4,
  backgroundColor: `${color}22`,
  color,
  border: `1px solid ${color}66`,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginLeft: 8,
})

const logPre: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
  fontSize: 10,
  lineHeight: 1.5,
  fontFamily: 'monospace',
  color: 'var(--text-primary)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  margin: 0,
  border: '1px solid var(--border)',
  height: 260,
  overflow: 'auto',
}

const btn: CSSProperties = {
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 4,
  cursor: 'pointer',
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
}

const metaLine: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  fontFamily: 'monospace',
  wordBreak: 'break-all',
}

interface LiveStageLogProps {
  stages: WorkflowStageStatus[]
  onOpenFull?: (stage: string, runId: string) => void
}

export function LiveStageLog({ stages, onOpenFull }: LiveStageLogProps) {
  const active = useMemo(() => pickActive(stages), [stages])
  const [target, setTarget] = useState<ResolvedTarget | null>(null)
  const [log, setLog] = useState<LogPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const preRef = useRef<HTMLPreElement | null>(null)

  // Re-resolve the target when the active stage (or its run_id) changes.
  useEffect(() => {
    let cancelled = false
    if (!active) {
      setTarget(null)
      setLog(null)
      return
    }
    ;(async () => {
      const t = await resolveTarget(active)
      if (!cancelled) setTarget(t)
    })()
    return () => { cancelled = true }
  }, [active?.stage, active?.run_id, active?.status])

  // Fetch + poll the log for the resolved target.
  useEffect(() => {
    if (!target) {
      setLog(null)
      return
    }
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const payload = await fetchLog(target!.stage, target!.runId)
        if (!cancelled) setLog(payload)
      } catch (e) {
        if (!cancelled) setLog({ logTail: `(log fetch failed: ${e})`, status: 'failed' })
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    if (target.status !== 'running') return
    const id = setInterval(load, 2500)
    return () => { cancelled = true; clearInterval(id) }
  }, [target?.stage, target?.runId, target?.status])

  // Auto-scroll on update when user hasn't manually scrolled up.
  useEffect(() => {
    if (!autoScroll || !preRef.current) return
    preRef.current.scrollTop = preRef.current.scrollHeight
  }, [log?.logTail, autoScroll])

  if (!active || !target || !log) {
    return null
  }

  const headerColor = statusColor(log.status)
  const subjectHint = target.isBatchJob ? ` · ${target.batchJobSubject}` : ''

  return (
    <div style={panelStyle}>
      <div style={headerRow}>
        <div>
          <span style={titleStyle}>Live log — {target.stage}{subjectHint}</span>
          <span style={badge(headerColor)}>{log.status}</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            auto-scroll
          </label>
          {onOpenFull && (
            <button style={btn} onClick={() => onOpenFull(target.stage, target.runId)}>
              Open full log
            </button>
          )}
        </div>
      </div>
      {log.error && (
        <div style={{ ...metaLine, color: 'var(--accent-red)' }}>{log.error}</div>
      )}
      {log.logPath && <div style={metaLine}>{log.logPath}</div>}
      {/* KB matches — appears only when the run has a triage record.
          Polls for a few seconds on a just-failed run because the
          triage thread hasn't written triage.json yet. */}
      <TriageMatches runId={target.runId} poll={log.status === 'failed'} />
      <pre ref={preRef} style={logPre}>
        {log.logTail && log.logTail.length > 0
          ? log.logTail
          : loading ? '(loading…)' : '(log empty — subprocess may not have written anything yet)'}
      </pre>
    </div>
  )
}
