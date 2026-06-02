/** Run-history panel scoped to a single study config.
 *
 * One row per study invocation (i.e. one ``study_runs/<name>/<timestamp>/``
 * directory). Mirrors GroupRunHistory one scope up.
 */

import { useState } from 'react'
import type { CSSProperties } from 'react'
import type { StudyRunListing } from '../../api/types'
import { AnalysisGraphModal } from '../workflow/AnalysisGraphModal'


interface Props {
  runs: StudyRunListing[]
  loading: boolean
}


const containerStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
  marginBottom: 16,
}

const headerStyle: CSSProperties = {
  padding: '12px 16px',
  fontSize: 12,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
}

const tableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 12,
}

const thStyle: CSSProperties = {
  textAlign: 'left',
  padding: '8px 12px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  fontWeight: 700,
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const tdStyle: CSSProperties = {
  padding: '8px 12px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

const rowStyle = (selected: boolean): CSSProperties => ({
  cursor: 'pointer',
  backgroundColor: selected ? 'rgba(0, 229, 255, 0.05)' : 'transparent',
})


function statusBadge(label: string, color: string): CSSProperties {
  return {
    display: 'inline-block', padding: '2px 8px', borderRadius: 3,
    fontSize: 10, fontWeight: 700,
    backgroundColor: `${color}22`, color, textTransform: 'uppercase',
  }
}


function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}


function formatDuration(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`
}


function overallStatus(r: StudyRunListing): { label: string; color: string } {
  const sc = r.status_counts || { ok: 0, failed: 0 }
  if ((sc.failed ?? 0) > 0) return { label: 'failed', color: 'var(--accent-red)' }
  if ((sc.ok ?? 0) > 0) return { label: 'ok', color: 'var(--accent-green)' }
  return { label: 'unknown', color: 'var(--text-secondary)' }
}


export function StudyRunHistory({ runs, loading }: Props) {
  const [graphRun, setGraphRun] = useState<StudyRunListing | null>(null)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  if (runs.length === 0 && !loading) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>Study invocations</div>
        <div style={{
          padding: '24px 16px', fontSize: 12,
          color: 'var(--text-secondary)', textAlign: 'center',
        }}>
          No study invocations yet for this config.
        </div>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Study invocations ({runs.length})</div>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>Started</th>
            <th style={thStyle}>Run ID</th>
            <th style={thStyle}>Groups</th>
            <th style={thStyle}>Duration</th>
            <th style={thStyle}>Status</th>
            <th style={thStyle} />
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const key = `${r.study_name}/${r.run_id}`
            const isSelected = selectedKey === key
            const status = overallStatus(r)
            const sc = r.status_counts || { ok: 0, failed: 0 }
            return (
              <tr
                key={key}
                style={rowStyle(isSelected)}
                onClick={() => setSelectedKey(isSelected ? null : key)}
              >
                <td style={tdStyle}>{formatDate(r.started_at)}</td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>
                  {r.run_id}
                </td>
                <td style={tdStyle}>
                  {r.n_groups}
                  {' '}
                  <span style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
                    {sc.ok ? `${sc.ok} ok` : ''}
                    {sc.failed ? ` · ${sc.failed} failed` : ''}
                  </span>
                </td>
                <td style={tdStyle}>{formatDuration(r.total_elapsed_s)}</td>
                <td style={tdStyle}>
                  <span style={statusBadge(status.label, status.color)}>
                    {status.label}
                  </span>
                </td>
                <td style={{ ...tdStyle, textAlign: 'right' }}>
                  <button
                    onClick={(e) => { e.stopPropagation(); setGraphRun(r) }}
                    style={{
                      padding: '2px 8px', fontSize: 10, fontWeight: 600,
                      border: '1px solid rgba(0, 229, 255, 0.4)', borderRadius: 3,
                      background: 'rgba(0, 229, 255, 0.08)',
                      color: 'var(--accent-cyan)', cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                    title="Show the analysis graph for this invocation"
                  >
                    Graph
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {graphRun && (
        <AnalysisGraphModal
          target={{
            // AnalysisGraphModal doesn't carry a 'study' GraphTarget kind
            // yet (that lands in Phase 5). For now fall back to 'group'
            // for the first listed group so the modal still renders
            // something meaningful — full study graph support comes next.
            kind: 'group',
            groupName: graphRun.group_labels[0] ?? graphRun.study_name,
            runId: graphRun.run_id,
          }}
          title={`${graphRun.study_name}/${graphRun.run_id} — study graph (placeholder)`}
          onClose={() => setGraphRun(null)}
        />
      )}
    </div>
  )
}
