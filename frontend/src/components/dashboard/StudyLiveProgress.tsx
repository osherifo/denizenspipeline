/** Live progress panel scoped to a STUDY run.
 *
 * Layout:
 *   - Header: study name, group count, elapsed timer, dismiss
 *   - Study-stage strip: collect → fanout → analyze → report
 *   - Per-group cards: each shows the group's stage strip (collect /
 *     fanout / analyze / report) plus a subject-count line
 *     (e.g. "5/8 subjects ok"). Click into the Group Runs view for
 *     drill-down.
 *   - Event log + failure log + TriageMatches on failure
 *
 * Three-deep event routing:
 *   * `study_*`               — top-level
 *   * `group_*` w/ `study`    — into the right group card
 *   * `stage_*` w/ `group_label`+`subject` — into the right subject in
 *     that group
 */

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type { RunEvent } from '../../api/types'
import { TriageMatches } from '../triage/TriageMatches'
import { AnalysisGraphModal } from '../workflow/AnalysisGraphModal'
import { formatDuration } from '../../utils/format'


interface Props {
  runId: string
  events: RunEvent[]
  startTime: number | null
  onDismiss?: () => void
}


// ── derived state ─────────────────────────────────────────────────────


type SimpleStatus = 'pending' | 'running' | 'ok' | 'failed' | 'warning'


interface SubjectMini {
  subject: string
  status: SimpleStatus
}


interface GroupState {
  /** Study-scope label, from study_group_start event. */
  label: string
  /** Underlying group name, when known. */
  group_name?: string
  status: SimpleStatus
  elapsed_s: number
  /** Group-stage strip: collect / fanout / analyze / [second_pass?] / report. */
  group_stages: Record<string, { status: SimpleStatus; elapsed_s: number }>
  subjects: Record<string, SubjectMini>
}


function emptyGroupStages(): Record<string, { status: SimpleStatus; elapsed_s: number }> {
  return {
    group_collect: { status: 'pending', elapsed_s: 0 },
    subject_fanout: { status: 'pending', elapsed_s: 0 },
    group_analyze: { status: 'pending', elapsed_s: 0 },
    subject_second_pass: { status: 'pending', elapsed_s: 0 },
    group_report: { status: 'pending', elapsed_s: 0 },
  }
}


interface StudyStageState {
  status: SimpleStatus
  elapsed_s: number
  detail: string
}


function derive(events: RunEvent[]) {
  const groupMap = new Map<string, GroupState>()
  const order: string[] = []
  function getGroup(label: string, group_name?: string): GroupState {
    let g = groupMap.get(label)
    if (!g) {
      g = {
        label, group_name, status: 'pending', elapsed_s: 0,
        group_stages: emptyGroupStages(),
        subjects: {},
      }
      groupMap.set(label, g)
      order.push(label)
    } else if (group_name && !g.group_name) {
      g.group_name = group_name
    }
    return g
  }

  const studyStages: Record<string, StudyStageState> = {
    study_collect: { status: 'pending', elapsed_s: 0, detail: '' },
    groups_fanout: { status: 'pending', elapsed_s: 0, detail: '' },
    study_analyze: { status: 'pending', elapsed_s: 0, detail: '' },
    study_report: { status: 'pending', elapsed_s: 0, detail: '' },
  }

  let studyName: string | undefined
  let studyRunDir: string | undefined
  let nGroups = 0

  for (const ev of events) {
    const a = ev as any
    switch (ev.event) {
      case 'study_started':
        studyName = a.study
        studyRunDir = a.run_dir
        nGroups = a.n_groups ?? (a.groups?.length ?? 0)
        for (const label of a.groups ?? []) getGroup(label)
        break
      case 'study_stage_start':
        if (a.stage && studyStages[a.stage]) {
          studyStages[a.stage] = { status: 'running', elapsed_s: 0, detail: '' }
        }
        break
      case 'study_stage_done':
        if (a.stage && studyStages[a.stage]) {
          studyStages[a.stage] = {
            status: 'ok', elapsed_s: a.elapsed ?? 0, detail: a.detail ?? '',
          }
        }
        break
      case 'study_stage_fail':
        if (a.stage && studyStages[a.stage]) {
          studyStages[a.stage] = {
            status: 'failed', elapsed_s: a.elapsed ?? 0,
            detail: a.error ?? '',
          }
        }
        break

      case 'study_group_start': {
        if (!a.group_label) break
        const g = getGroup(a.group_label, a.group_name)
        g.status = 'running'
        break
      }
      case 'study_group_done': {
        if (!a.group_label) break
        const g = getGroup(a.group_label, a.group_name)
        g.status = a.status === 'failed' ? 'failed' : 'ok'
        g.elapsed_s = a.elapsed ?? 0
        break
      }

      // Group-scope events get tagged with study + group_label by
      // StudyOrchestrator's event_context wrap.
      case 'group_stage_start': {
        const label = a.group_label
        if (!label) break
        const g = getGroup(label)
        if (a.stage && g.group_stages[a.stage]) {
          g.group_stages[a.stage] = { status: 'running', elapsed_s: 0 }
        }
        break
      }
      case 'group_stage_done': {
        const label = a.group_label
        if (!label) break
        const g = getGroup(label)
        if (a.stage && g.group_stages[a.stage]) {
          g.group_stages[a.stage] = {
            status: 'ok', elapsed_s: a.elapsed ?? 0,
          }
        }
        break
      }
      case 'group_stage_fail': {
        const label = a.group_label
        if (!label) break
        const g = getGroup(label)
        if (a.stage && g.group_stages[a.stage]) {
          g.group_stages[a.stage] = {
            status: 'failed', elapsed_s: a.elapsed ?? 0,
          }
        }
        break
      }
      case 'group_subject_start':
      case 'group_subject_done': {
        const label = a.group_label
        const sub = a.subject
        if (!label || !sub) break
        const g = getGroup(label)
        const cur = g.subjects[sub] ?? { subject: sub, status: 'pending' as SimpleStatus }
        if (ev.event === 'group_subject_start') cur.status = 'running'
        else cur.status = a.status === 'failed' ? 'failed' : 'ok'
        g.subjects[sub] = cur
        break
      }

      default:
        break
    }
  }

  const groups = order.map((l) => groupMap.get(l)!)
  return { groups, studyStages, studyName, studyRunDir, nGroups }
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

const groupGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
}

const groupCard = (status: SimpleStatus): CSSProperties => ({
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

const groupCardHeader: CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  marginBottom: 8,
}

const groupLabel: CSSProperties = {
  fontSize: 13, fontWeight: 700, color: 'var(--text-primary)',
  fontFamily: 'monospace',
}

const eventLogStyle: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)', borderRadius: 6,
  padding: '10px 12px', maxHeight: 180, overflowY: 'auto',
  fontSize: 11, lineHeight: 1.7, fontFamily: 'monospace',
}


function statusColor(s: SimpleStatus): string {
  switch (s) {
    case 'ok': return 'var(--accent-green)'
    case 'running': return 'var(--accent-cyan)'
    case 'failed': return 'var(--accent-red)'
    case 'warning': return 'var(--accent-yellow)'
    default: return 'var(--text-secondary)'
  }
}


function formatStudyStageLabel(name: string): string {
  switch (name) {
    case 'study_collect': return 'collect'
    case 'groups_fanout': return 'fanout'
    case 'study_analyze': return 'analyze'
    case 'study_report': return 'report'
    default: return name
  }
}


function formatGroupStageLabel(name: string): string {
  switch (name) {
    case 'group_collect': return 'collect'
    case 'subject_fanout': return 'subjects'
    case 'group_analyze': return 'analyze'
    case 'subject_second_pass': return '2nd pass'
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


// Short "group/subject:" prefix for subject-tagged events. Falls
// back gracefully when an event only carries one of the two tags
// (e.g. a top-level group run won't have group_label, just group).
function _subjectTag(a: any): string {
  const group = a.group_label ?? a.group
  if (group && a.subject) return `    · ${group}/${a.subject}`
  if (a.subject) return `    · ${a.subject}`
  if (group) return `  · ${group}`
  return ''
}

function formatEventLine(event: RunEvent): string {
  const a = event as any
  switch (event.event) {
    case 'study_started': return `▶ study ${a.study} — ${a.n_groups} groups`
    case 'study_group_start': return `▶ group ${a.group_label}`
    case 'study_group_done':
      return `${a.status === 'failed' ? '✗' : '✓'} group ${a.group_label} (${formatDuration(a.elapsed ?? 0)})`
    case 'study_stage_start': return `▶ ${a.stage}`
    case 'study_stage_done': return `✓ ${a.stage} (${formatDuration(a.elapsed ?? 0)})`
    case 'study_stage_fail': return `✗ ${a.stage}: ${a.error ?? 'failed'}`
    case 'study_done': return `✓ study done (${formatDuration(a.elapsed ?? 0)})`
    case 'group_stage_start': return `  · ${a.group_label ?? a.group ?? '?'}: ▶ ${a.stage}`
    case 'group_stage_done': return `  · ${a.group_label ?? a.group ?? '?'}: ✓ ${a.stage}`
    case 'group_subject_start':
      return `${_subjectTag(a)}: ▶ subject pipeline`
    case 'group_subject_done':
      return `${_subjectTag(a)}: ${a.status === 'failed' ? '✗' : '✓'} subject pipeline${a.elapsed != null ? ` (${formatDuration(a.elapsed)})` : ''}`
    case 'stage_start':
      return `${_subjectTag(a)}: ▶ ${a.stage}`
    case 'stage_done':
      return `${_subjectTag(a)}: ✓ ${a.stage}${a.elapsed != null ? ` (${formatDuration(a.elapsed)})` : ''}${a.detail ? ` — ${a.detail}` : ''}`
    case 'stage_fail':
      return `${_subjectTag(a)}: ✗ ${a.stage}: ${a.error ?? 'failed'}`
    case 'stage_warn':
      return `${_subjectTag(a)}: ⚠ ${a.stage}${a.detail ? ` — ${a.detail}` : ''}`
    case 'log': return event.message || ''
    case 'started': return event.message || 'Run started'
    case 'run_done': return `✓ Run complete (${formatDuration(a.total_elapsed ?? 0)})`
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


export function StudyLiveProgress({ runId, events, startTime, onDismiss }: Props) {
  const [graphOpen, setGraphOpen] = useState(false)
  const lastEvent = events[events.length - 1]
  const isDone = lastEvent?.event === 'run_done' || lastEvent?.event === 'study_done'
  const isFailed = lastEvent?.event === 'run_failed'
  const isFinished = isDone || isFailed

  const { groups, studyStages, studyName, studyRunDir, nGroups } = useMemo(
    () => derive(events), [events],
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
            {isDone ? 'Study Complete' : isFailed ? 'Study Failed' :
              `Running ${studyName || 'study'}`}
          </span>
          {nGroups > 0 && (
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 500 }}>
              · {groups.length}/{nGroups} groups
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            onClick={() => setGraphOpen(true)}
            style={{
              padding: '3px 10px', fontSize: 11, fontWeight: 600,
              border: '1px solid rgba(0, 229, 255, 0.4)', borderRadius: 4,
              background: 'rgba(0, 229, 255, 0.08)',
              color: 'var(--accent-cyan)', cursor: 'pointer',
              fontFamily: 'inherit',
            }}
            title={isFinished
              ? 'Open the pipeline graph (final state)'
              : 'Open the pipeline graph (live — polls until the run ends)'}
          >
            View graph
          </button>
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

      {studyRunDir && (
        <div style={{
          fontSize: 10, color: 'var(--text-secondary)',
          fontFamily: 'monospace', wordBreak: 'break-all', marginBottom: 8,
        }}>
          {studyRunDir}
        </div>
      )}

      {/* Study-stage strip */}
      <div style={sectionLabel}>Study stages</div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
        gap: 8,
      }}>
        {(['study_collect', 'groups_fanout', 'study_analyze', 'study_report'] as const).map((name) => {
          const st = studyStages[name]
          const color = statusColor(st.status)
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
                {formatStudyStageLabel(name)}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                {st.status === 'pending' ? '·' : st.status}
                {st.elapsed_s > 0 && ` · ${formatDuration(st.elapsed_s)}`}
              </div>
            </div>
          )
        })}
      </div>

      {/* Per-group cards */}
      {groups.length > 0 && (
        <>
          <div style={sectionLabel}>Groups</div>
          <div style={groupGrid}>
            {groups.map((g) => {
              const subjects = Object.values(g.subjects)
              const sok = subjects.filter((s) => s.status === 'ok').length
              const sfail = subjects.filter((s) => s.status === 'failed').length
              const srun = subjects.filter((s) => s.status === 'running').length
              return (
                <div key={g.label} style={groupCard(g.status)}>
                  <div style={groupCardHeader}>
                    <span style={groupLabel}>{g.label}</span>
                    <span style={{
                      fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                      color: statusColor(g.status),
                    }}>
                      {g.status}
                      {g.elapsed_s > 0 && ` · ${formatDuration(g.elapsed_s)}`}
                    </span>
                  </div>
                  {g.group_name && (
                    <div style={{
                      fontSize: 10, color: 'var(--text-secondary)',
                      fontFamily: 'monospace', marginBottom: 6,
                    }}>
                      {g.group_name}
                    </div>
                  )}
                  {/* Group-stage strip inside the card */}
                  <div style={{
                    display: 'flex', gap: 4, marginBottom: 6, flexWrap: 'wrap',
                  }}>
                    {(['group_collect', 'subject_fanout', 'group_analyze', 'group_report'] as const).map((name) => {
                      const st = g.group_stages[name]
                      const color = statusColor(st.status)
                      return (
                        <span
                          key={name}
                          style={{
                            fontSize: 9, fontWeight: 600,
                            padding: '1px 6px', borderRadius: 3,
                            color, border: `1px solid ${st.status === 'pending' ? 'var(--border)' : color}`,
                            textTransform: 'uppercase', letterSpacing: 0.5,
                          }}
                          title={`${name}: ${st.status}`}
                        >
                          {formatGroupStageLabel(name)}
                        </span>
                      )
                    })}
                  </div>
                  {subjects.length > 0 && (
                    <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                      {sok}/{subjects.length} ok
                      {sfail > 0 && (
                        <span style={{ color: 'var(--accent-red)' }}> · {sfail} failed</span>
                      )}
                      {srun > 0 && (
                        <span style={{ color: 'var(--accent-cyan)' }}> · {srun} running</span>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* Triage on failure */}
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
            {events
              .filter((e) => !e.event.startsWith('node_'))
              .map((event, i) => (
              <div key={i} style={{
                color: 'var(--text-secondary)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                <span style={{ color: 'var(--text-secondary)', marginRight: 8 }}>
                  {formatTimestamp(event.timestamp)}
                </span>
                <span style={{
                  color:
                    event.event === 'study_stage_fail' || event.event === 'run_failed' ||
                    event.event === 'group_stage_fail'
                      ? 'var(--accent-red)' :
                    event.event === 'study_stage_done' || event.event === 'run_done' ||
                    event.event === 'study_group_done' || event.event === 'group_stage_done'
                      ? 'var(--accent-green)' :
                    event.event === 'study_stage_start' || event.event === 'study_group_start' ||
                    event.event === 'study_started' || event.event === 'group_stage_start'
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

      {graphOpen && (
        <AnalysisGraphModal
          target={{ kind: 'in-flight', runId }}
          title={`Study ${studyName || runId} — live pipeline graph`}
          onClose={() => setGraphOpen(false)}
        />
      )}
    </div>
  )
}
