/** Live progress panel scoped to a GROUP run.
 *
 * Layout:
 *   - Header: group name, subject count, elapsed timer, dismiss
 *   - Group-stages tracker (collect, analyze, second_pass?, report)
 *   - Subject grid: one card per subject, each w/ its own 7-stage tracker
 *   - Event log (raw WS events, same shape as LiveProgress)
 *   - Failure log + KB-matches panel when the group run failed
 *
 * State is derived from the same ``events`` array that LiveProgress uses;
 * the GroupOrchestrator emits ``group_*`` and ``group_subject_*`` events
 * alongside the per-subject ``stage_*`` events (each tagged with a
 * ``subject`` field).
 */

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type { RunEvent, StageStatus } from '../../api/types'
import { StageTracker } from './StageTracker'
import { TriageMatches } from '../triage/TriageMatches'


interface Props {
  runId: string
  events: RunEvent[]
  startTime: number | null
  onDismiss?: () => void
}


const SUBJECT_STAGES = ['stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report']


// ── derived state ─────────────────────────────────────────────────────


function emptyStageState(): Record<string, StageStatus> {
  const out: Record<string, StageStatus> = {}
  for (const s of SUBJECT_STAGES) {
    out[s] = { status: 'pending', detail: '', elapsed_s: 0 }
  }
  return out
}


interface SubjectState {
  subject: string
  status: 'pending' | 'running' | 'ok' | 'failed' | 'warning'
  elapsed_s: number
  stages: Record<string, StageStatus>
}


interface GroupStageState {
  status: StageStatus['status']
  elapsed_s: number
  detail: string
  error?: string
}


function derive(events: RunEvent[]) {
  // Subject cards — keyed by subject id, ordered by first-seen.
  const subjectMap = new Map<string, SubjectState>()
  const order: string[] = []
  function getSub(sub: string): SubjectState {
    let s = subjectMap.get(sub)
    if (!s) {
      s = {
        subject: sub, status: 'pending', elapsed_s: 0,
        stages: emptyStageState(),
      }
      subjectMap.set(sub, s)
      order.push(sub)
    }
    return s
  }

  // Group-stage tracker — keyed by stage name in declared order.
  const groupStages: Record<string, GroupStageState> = {
    group_collect: { status: 'pending', elapsed_s: 0, detail: '' },
    subject_fanout: { status: 'pending', elapsed_s: 0, detail: '' },
    group_analyze: { status: 'pending', elapsed_s: 0, detail: '' },
    subject_second_pass: { status: 'pending', elapsed_s: 0, detail: '' },
    group_report: { status: 'pending', elapsed_s: 0, detail: '' },
  }

  let groupRunDir: string | undefined
  let groupName: string | undefined
  let nSubjects = 0

  for (const ev of events) {
    const anyEv = ev as any
    switch (ev.event) {
      case 'group_started':
        groupName = anyEv.group
        groupRunDir = anyEv.run_dir
        nSubjects = anyEv.n_subjects ?? (anyEv.subjects?.length ?? 0)
        for (const sub of anyEv.subjects ?? []) getSub(sub)
        break
      case 'group_stage_start':
        if (anyEv.stage && groupStages[anyEv.stage]) {
          groupStages[anyEv.stage] = {
            status: 'running', elapsed_s: 0, detail: '',
          }
        }
        break
      case 'group_stage_done':
        if (anyEv.stage && groupStages[anyEv.stage]) {
          groupStages[anyEv.stage] = {
            status: 'done', elapsed_s: anyEv.elapsed ?? 0,
            detail: anyEv.detail ?? '',
          }
        }
        break
      case 'group_stage_fail':
        if (anyEv.stage && groupStages[anyEv.stage]) {
          groupStages[anyEv.stage] = {
            status: 'failed', elapsed_s: anyEv.elapsed ?? 0,
            detail: anyEv.error ?? '', error: anyEv.error,
          }
        }
        break
      case 'group_subject_start': {
        if (!anyEv.subject) break
        const s = getSub(anyEv.subject)
        s.status = 'running'
        break
      }
      case 'group_subject_done': {
        if (!anyEv.subject) break
        const s = getSub(anyEv.subject)
        s.status = anyEv.status === 'failed' ? 'failed' : 'ok'
        s.elapsed_s = anyEv.elapsed ?? 0
        break
      }
      case 'stage_start':
      case 'stage_done':
      case 'stage_fail':
      case 'stage_warn': {
        const sub = anyEv.subject
        if (!sub || !anyEv.stage) break
        const s = getSub(sub)
        const cur = s.stages[anyEv.stage] ?? {
          status: 'pending', detail: '', elapsed_s: 0,
        }
        if (ev.event === 'stage_start') {
          s.stages[anyEv.stage] = { ...cur, status: 'running' }
        } else if (ev.event === 'stage_done') {
          s.stages[anyEv.stage] = {
            status: 'done', detail: anyEv.detail ?? '',
            elapsed_s: anyEv.elapsed ?? 0,
          }
        } else if (ev.event === 'stage_fail') {
          s.stages[anyEv.stage] = {
            status: 'failed', detail: anyEv.error ?? '',
            elapsed_s: anyEv.elapsed ?? 0,
          }
        } else if (ev.event === 'stage_warn') {
          s.stages[anyEv.stage] = {
            status: 'warning', detail: anyEv.detail ?? '',
            elapsed_s: anyEv.elapsed ?? 0,
          }
        }
        break
      }
      default:
        break
    }
  }

  const subjects = order.map((id) => subjectMap.get(id)!)
  return { subjects, groupStages, groupName, groupRunDir, nSubjects }
}


// ── styles ────────────────────────────────────────────────────────────


const panelStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--accent-cyan)',
  borderRadius: 8,
  padding: '20px',
  marginBottom: 16,
}

const headerStyle: CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  marginBottom: 16,
}

const titleStyle: CSSProperties = {
  fontSize: 14, fontWeight: 700, color: 'var(--accent-cyan)',
  display: 'flex', alignItems: 'center', gap: 8,
}

const sectionLabel: CSSProperties = {
  fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)',
  textTransform: 'uppercase', letterSpacing: 1,
  marginTop: 16, marginBottom: 8,
}

const elapsedStyle: CSSProperties = {
  fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
}

const subjectGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
}

const subjectCard = (status: SubjectState['status']): CSSProperties => ({
  backgroundColor: 'var(--bg-secondary)',
  border: `1px solid ${
    status === 'running' ? 'var(--accent-cyan)' :
    status === 'failed' ? 'var(--accent-red)' :
    status === 'ok' ? 'var(--accent-green)' :
    'var(--border)'
  }`,
  borderRadius: 6,
  padding: '10px 12px',
})

const subjectHeader: CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  marginBottom: 8,
}

const subjectName: CSSProperties = {
  fontSize: 13, fontWeight: 700, color: 'var(--text-primary)',
  fontFamily: 'monospace',
}

const eventLogStyle: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)', borderRadius: 6,
  padding: '10px 12px', maxHeight: 180, overflowY: 'auto',
  fontSize: 11, lineHeight: 1.7, fontFamily: 'monospace',
}


function formatGroupStageLabel(name: string): string {
  switch (name) {
    case 'group_collect': return 'collect'
    case 'subject_fanout': return 'fanout'
    case 'group_analyze': return 'analyze'
    case 'subject_second_pass': return 'second pass'
    case 'group_report': return 'report'
    default: return name
  }
}

function ElapsedTimer({ startTime }: { startTime: number | null }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!startTime) return
    const t = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)
    return () => clearInterval(t)
  }, [startTime])
  if (!startTime) return null
  const min = Math.floor(elapsed / 60)
  const sec = elapsed % 60
  return <span style={elapsedStyle}>{min > 0 ? `${min}m ${sec}s` : `${sec}s`}</span>
}


function formatEventLine(event: RunEvent): string {
  const a = event as any
  switch (event.event) {
    case 'group_started': return `▶ group ${a.group} — ${a.n_subjects} subjects`
    case 'group_subject_start': return `▶ subject ${a.subject}`
    case 'group_subject_done':
      return `${a.status === 'failed' ? '✗' : '✓'} subject ${a.subject} (${(a.elapsed ?? 0).toFixed(1)}s)`
    case 'group_stage_start': return `▶ ${a.stage}`
    case 'group_stage_done': return `✓ ${a.stage} (${(a.elapsed ?? 0).toFixed(1)}s)`
    case 'group_stage_fail': return `✗ ${a.stage}: ${a.error ?? 'failed'}`
    case 'group_done': return `✓ group done (${(a.elapsed ?? 0).toFixed(1)}s)`
    case 'stage_start': return `  · ${a.subject ?? '?'}: ▶ ${a.stage}`
    case 'stage_done': return `  · ${a.subject ?? '?'}: ✓ ${a.stage} (${(a.elapsed ?? 0).toFixed(1)}s)`
    case 'stage_fail': return `  · ${a.subject ?? '?'}: ✗ ${a.stage}: ${a.error ?? ''}`
    case 'stage_warn': return `  · ${a.subject ?? '?'}: ! ${a.stage}: ${a.detail ?? ''}`
    case 'started': return event.message || 'Run started'
    case 'run_done': return `✓ Run complete (${(a.total_elapsed ?? 0).toFixed(1)}s)`
    case 'run_failed': return `✗ Run failed: ${event.error || ''}`
    default: return event.event
  }
}


function formatTimestamp(ts: number | undefined): string {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}


// ── component ─────────────────────────────────────────────────────────


export function GroupLiveProgress({ runId, events, startTime, onDismiss }: Props) {
  const lastEvent = events[events.length - 1]
  const isDone = lastEvent?.event === 'run_done' || lastEvent?.event === 'group_done'
  const isFailed = lastEvent?.event === 'run_failed'
  const isFinished = isDone || isFailed

  const { subjects, groupStages, groupName, groupRunDir, nSubjects } = useMemo(
    () => derive(events), [events],
  )

  // Render group stages in display order; skip the ones that never fired
  // and never finished (e.g. subject_second_pass when the config doesn't
  // need it).
  const visibleGroupStages = [
    'group_collect', 'subject_fanout', 'group_analyze',
    'subject_second_pass', 'group_report',
  ].filter((s) => groupStages[s].status !== 'pending')
   .concat(
      // Always include collect + fanout + report-or-analyze as a hint,
      // even before any event arrives, so the panel doesn't look empty.
      events.length === 0 ? ['group_collect', 'subject_fanout'] : [],
    )

  return (
    <div style={{
      ...panelStyle,
      borderColor: isDone ? 'var(--accent-green)' :
        isFailed ? 'var(--accent-red)' : 'var(--accent-cyan)',
    }}>
      <div style={headerStyle}>
        <div style={titleStyle}>
          {!isFinished && <span style={{ animation: 'pulse 1.5s infinite' }}>●</span>}
          {isDone && <span style={{ color: 'var(--accent-green)' }}>✓</span>}
          {isFailed && <span style={{ color: 'var(--accent-red)' }}>✗</span>}
          <span>
            {isDone ? 'Group Complete' : isFailed ? 'Group Failed' :
              `Running ${groupName || 'group'}`}
          </span>
          {nSubjects > 0 && (
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 500 }}>
              · {subjects.length}/{nSubjects} subjects
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ElapsedTimer startTime={isFinished ? null : startTime} />
          {isFinished && onDismiss && (
            <button
              onClick={onDismiss}
              style={{
                background: 'none', border: 'none', color: 'var(--text-secondary)',
                cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
              }}
            >
              Dismiss
            </button>
          )}
        </div>
      </div>

      {groupRunDir && (
        <div style={{
          fontSize: 10, color: 'var(--text-secondary)',
          fontFamily: 'monospace', wordBreak: 'break-all', marginBottom: 8,
        }}>
          {groupRunDir}
        </div>
      )}

      {/* Group-stage tracker */}
      <div style={sectionLabel}>Group stages</div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
        gap: 8,
      }}>
        {visibleGroupStages.map((name) => {
          const st = groupStages[name]
          const color =
            st.status === 'done' ? 'var(--accent-green)' :
            st.status === 'running' ? 'var(--accent-cyan)' :
            st.status === 'failed' ? 'var(--accent-red)' :
            'var(--text-secondary)'
          return (
            <div
              key={name}
              style={{
                border: `1px solid ${st.status === 'pending' ? 'var(--border)' : color}`,
                borderRadius: 5, padding: '6px 10px', textAlign: 'center',
                background: 'var(--bg-secondary)',
              }}
            >
              <div style={{
                fontSize: 10, fontWeight: 700, color, textTransform: 'uppercase',
                letterSpacing: 0.5,
              }}>
                {formatGroupStageLabel(name)}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                {st.status === 'pending' ? '·' : st.status}
                {st.elapsed_s > 0 && ` · ${st.elapsed_s.toFixed(1)}s`}
              </div>
            </div>
          )
        })}
      </div>

      {/* Per-subject grid */}
      {subjects.length > 0 && (
        <>
          <div style={sectionLabel}>Subjects</div>
          <div style={subjectGrid}>
            {subjects.map((s) => (
              <div key={s.subject} style={subjectCard(s.status)}>
                <div style={subjectHeader}>
                  <span style={subjectName}>{s.subject}</span>
                  <span style={{
                    fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                    color:
                      s.status === 'running' ? 'var(--accent-cyan)' :
                      s.status === 'ok' ? 'var(--accent-green)' :
                      s.status === 'failed' ? 'var(--accent-red)' :
                      'var(--text-secondary)',
                  }}>
                    {s.status}
                    {s.elapsed_s > 0 && ` · ${s.elapsed_s.toFixed(0)}s`}
                  </span>
                </div>
                <StageTracker stageStatuses={s.stages} />
              </div>
            ))}
          </div>
        </>
      )}

      {/* Triage KB matches on failure */}
      {isFailed && <TriageMatches runId={runId} poll />}

      {/* Failure log */}
      {isFailed && (() => {
        const failed = events.slice().reverse().find((e) => e.event === 'run_failed')
        const tail = failed?.log_tail || ''
        const tb = failed?.traceback || ''
        const path = failed?.log_path || ''
        if (!tail && !tb) return null
        return (
          <>
            <div style={sectionLabel}>
              Failure log {path && (
                <span style={{ fontWeight: 400, fontSize: 10, color: 'var(--text-secondary)' }}>
                  · <code>{path}</code>
                </span>
              )}
            </div>
            <pre style={{
              backgroundColor: 'var(--bg-secondary)', padding: '10px 12px',
              borderRadius: 6, fontSize: 10, lineHeight: 1.55,
              color: 'var(--text-primary)', overflow: 'auto', maxHeight: 400,
              whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
            }}>
              {tb ? `${tb}\n\n--- pipeline.log (tail) ---\n${tail}` : tail}
            </pre>
          </>
        )
      })()}

      {/* Event log */}
      {events.length > 0 && (
        <>
          <div style={sectionLabel}>Event Log</div>
          <div style={eventLogStyle}>
            {events.map((event, i) => (
              <div key={i} style={{
                color: 'var(--text-secondary)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                <span style={{ color: 'var(--text-secondary)', marginRight: 8 }}>
                  {formatTimestamp(event.timestamp)}
                </span>
                <span style={{
                  color:
                    event.event === 'stage_fail' || event.event === 'run_failed' ||
                    event.event === 'group_stage_fail'
                      ? 'var(--accent-red)' :
                    event.event === 'stage_done' || event.event === 'run_done' ||
                    event.event === 'group_stage_done' || event.event === 'group_subject_done'
                      ? 'var(--accent-green)' :
                    event.event === 'stage_start' || event.event === 'group_stage_start' ||
                    event.event === 'group_subject_start' || event.event === 'group_started'
                      ? 'var(--accent-cyan)' :
                    'var(--text-secondary)',
                }}>
                  {formatEventLine(event)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
