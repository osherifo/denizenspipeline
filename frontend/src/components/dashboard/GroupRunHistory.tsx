/** Run-history panel scoped to a single group config.
 *
 * One row per group invocation (i.e. one ``group_runs/<name>/<timestamp>/``
 * directory), NOT per per-subject run. Clicking a row opens the
 * preview graph for that invocation; the "Open in Group Runs"
 * link jumps to the full GroupRunsView for drilling into subjects.
 */

import { useState } from 'react'
import type { CSSProperties } from 'react'
import type { GroupRunListing } from '../../api/types'
import { AnalysisGraphModal } from '../workflow/AnalysisGraphModal'


interface Props {
  runs: GroupRunListing[]
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


/** Roll the per-subject status counts up to one badge. */
function overallStatus(r: GroupRunListing): { label: string; color: string } {
  const sc = r.status_counts || {}
  if ((sc.failed ?? 0) > 0) return { label: 'failed', color: 'var(--accent-red)' }
  if ((sc.warning ?? 0) > 0) return { label: 'warning', color: 'var(--accent-yellow)' }
  if ((sc.unknown ?? 0) > 0 && (sc.ok ?? 0) === 0) {
    return { label: 'unknown', color: 'var(--text-secondary)' }
  }
  return { label: 'ok', color: 'var(--accent-green)' }
}


export function GroupRunHistory({ runs, loading }: Props) {
  const [graphRun, setGraphRun] = useState<GroupRunListing | null>(null)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  if (runs.length === 0 && !loading) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>Group invocations</div>
        <div style={{
          padding: '24px 16px', fontSize: 12,
          color: 'var(--text-secondary)', textAlign: 'center',
        }}>
          No group invocations yet for this config.
        </div>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Group invocations ({runs.length})</div>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>Started</th>
            <th style={thStyle}>Run ID</th>
            <th style={thStyle}>Subjects</th>
            <th style={thStyle}>Duration</th>
            <th style={thStyle}>Status</th>
            <th style={thStyle} />
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const key = `${r.group_name}/${r.run_id || 'legacy'}`
            const isSelected = selectedKey === key
            const status = overallStatus(r)
            const sc = r.status_counts || {}
            return (
              <tr
                key={key}
                style={rowStyle(isSelected)}
                onClick={() => setSelectedKey(isSelected ? null : key)}
              >
                <td style={tdStyle}>{formatDate(r.started_at)}</td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>
                  {r.run_id || '(legacy)'}
                </td>
                <td style={tdStyle}>
                  {r.n_subjects}
                  {' '}
                  <span style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
                    {sc.ok ? `${sc.ok} ok` : ''}
                    {sc.failed ? ` · ${sc.failed} failed` : ''}
                    {sc.warning ? ` · ${sc.warning} warn` : ''}
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
                      fontFamily: 'inherit', marginRight: 6,
                    }}
                    title="Show the analysis graph for this invocation"
                  >
                    Graph
                  </button>
                  <a
                    href={`#group-runs`}
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      fontSize: 10, color: 'var(--text-secondary)',
                      textDecoration: 'none',
                    }}
                    title="Open the Group Runs page to drill into subjects"
                  >
                    Open ↗
                  </a>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {graphRun && (
        <AnalysisGraphModal
          target={{
            kind: 'group',
            groupName: graphRun.group_name,
            runId: graphRun.run_id,
          }}
          title={`${graphRun.group_name}/${graphRun.run_id} — group graph`}
          onClose={() => setGraphRun(null)}
        />
      )}
    </div>
  )
}
