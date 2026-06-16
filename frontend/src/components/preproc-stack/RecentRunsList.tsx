/**
 * RecentRunsList — compact list of historical stack runs.
 *
 * Fetched once on mount and refreshed after each launch. Clicking
 * a run loads its status into the active-run panel so the user can
 * inspect cache hits, errors, and the final manifest path without
 * leaving the page.
 */

import { useEffect } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'
import { fetchStackRun } from '../../api/client'
import type { StackRunSummary } from '../../api/types'


const panelStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: 12,
  marginTop: 16,
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: 8,
}

const headerLabelStyle: CSSProperties = {
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 1,
  color: 'var(--text-secondary)',
}

const refreshButton: CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  padding: '2px 8px',
  fontSize: 10,
  cursor: 'pointer',
  borderRadius: 4,
}

const rowStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr auto auto auto',
  gap: 8,
  padding: '6px 8px',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'pointer',
  alignItems: 'center',
}


const STATUS_COLOR: Record<string, string> = {
  done: 'var(--accent-green)',
  running: 'var(--accent-yellow)',
  failed: 'var(--accent-red)',
  cancelled: 'var(--accent-red)',
  lost: 'var(--text-secondary)',
}


function formatStarted(unix: number): string {
  if (!unix) return '—'
  const d = new Date(unix * 1000)
  // YYYY-MM-DD HH:MM — locale-agnostic, easy to scan.
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}


function statusBadgeStyle(status: string): CSSProperties {
  const color = STATUS_COLOR[status] ?? 'var(--text-secondary)'
  return {
    padding: '1px 6px',
    fontSize: 10,
    border: `1px solid ${color}`,
    borderRadius: 10,
    color,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  }
}


function cacheSummary(run: StackRunSummary): string {
  const hits = run.result?.stage_cache_hits ?? []
  if (hits.length === 0) return '—'
  const hitCount = hits.filter((h) => h).length
  return `${hitCount}/${hits.length} cached`
}


export function RecentRunsList() {
  const runHistory = usePreprocStackStore((s) => s.runHistory)
  const refreshHistory = usePreprocStackStore((s) => s.refreshHistory)
  const activeRunId = usePreprocStackStore((s) => s.activeRunId)

  useEffect(() => {
    void refreshHistory()
  }, [refreshHistory])

  // Refresh when the active run finishes — the new entry should show up.
  const activeStatus = usePreprocStackStore((s) => s.activeStatus)
  useEffect(() => {
    if (activeStatus && activeStatus !== 'running' && activeStatus !== 'launching') {
      void refreshHistory()
    }
  }, [activeStatus, refreshHistory])

  const onSelect = (runId: string) => {
    // Load the run into the active panel by fetching its current
    // status. Doesn't open a WebSocket — terminal runs don't need one.
    // Close any live socket the active panel might still hold so we
    // don't leak the connection + duplicate event handlers when the
    // user clicks history while a run is in flight.
    const existing = usePreprocStackStore.getState().websocket
    if (existing) {
      try {
        existing.close()
      } catch {
        /* already-closed sockets throw on some engines; ignore */
      }
    }
    void fetchStackRun(runId).then((summary) => {
      usePreprocStackStore.setState({
        activeRunId: summary.run_id,
        activeStatus: summary.status,
        activeEvents: [],
        activeResult: summary.result,
        activeError: summary.error,
        websocket: null,
      })
    })
  }

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <span style={headerLabelStyle}>
          Recent runs ({runHistory.length})
        </span>
        <button style={refreshButton} onClick={() => void refreshHistory()}>
          Refresh
        </button>
      </div>

      {runHistory.length === 0 && (
        <div
          style={{
            fontSize: 12,
            color: 'var(--text-secondary)',
            fontStyle: 'italic',
          }}
        >
          No stack runs yet. Launch one above.
        </div>
      )}

      {runHistory.map((run) => {
        const isActive = run.run_id === activeRunId
        return (
          <div
            key={run.run_id}
            onClick={() => onSelect(run.run_id)}
            style={{
              ...rowStyle,
              background: isActive ? 'var(--bg-input)' : 'transparent',
              border: isActive
                ? '1px solid var(--accent-cyan)'
                : '1px solid transparent',
            }}
            onMouseEnter={(e) => {
              if (!isActive) {
                ;(e.currentTarget as HTMLDivElement).style.background =
                  'var(--bg-input)'
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                ;(e.currentTarget as HTMLDivElement).style.background =
                  'transparent'
              }
            }}
          >
            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span style={{ color: 'var(--text-primary)' }}>{run.subject}</span>
              <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>
                {run.backend}
              </span>
            </div>
            <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
              {formatStarted(run.started_at)}
            </span>
            <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
              {cacheSummary(run)}
            </span>
            <span style={statusBadgeStyle(run.status)}>{run.status}</span>
          </div>
        )
      })}
    </div>
  )
}
