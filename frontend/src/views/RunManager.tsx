import { useEffect, useCallback } from 'react'
import type { CSSProperties } from 'react'
import { useRunStore, COMPARE_MAX } from '../stores/run-store'
import { StageTimeline } from '../components/runs/StageTimeline'
import { SortableArtifactList } from '../components/results/SortableArtifactList'
import { RunComparison } from '../components/runs/RunComparison'
import type { RunSummary } from '../api/types'

// ── Styles ──

const headerStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 24,
}

const titleStyle: CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
}

const refreshBtn: CSSProperties = {
  padding: '8px 20px',
  fontSize: 12,
  fontWeight: 600,
  backgroundColor: 'rgba(0, 229, 255, 0.08)',
  border: '1px solid rgba(0, 229, 255, 0.25)',
  borderRadius: 6,
  color: 'var(--accent-cyan)',
  cursor: 'pointer',
  letterSpacing: 0.5,
}

const tableContainerStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
}

const tableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 13,
}

const thStyle: CSSProperties = {
  textAlign: 'left',
  padding: '12px 16px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  fontWeight: 700,
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const tdStyle: CSSProperties = {
  padding: '10px 16px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

const rowStyle = (selected: boolean): CSSProperties => ({
  cursor: 'pointer',
  backgroundColor: selected ? 'rgba(0, 229, 255, 0.05)' : 'transparent',
  transition: 'background-color 0.1s ease',
})

const detailPanel: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '24px',
  marginTop: 20,
}

const detailHeader: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 20,
}

const detailTitle: CSSProperties = {
  fontSize: 16,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
}

const closeBtn: CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontSize: 14,
  fontWeight: 700,
  padding: '4px 8px',
}

const sectionLabel: CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 20,
  marginBottom: 10,
}

const summaryGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
  gap: 12,
  marginBottom: 20,
}

const summaryCard: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '12px 14px',
}

const summaryLabel: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 4,
}

const summaryValue: CSSProperties = {
  fontSize: 15,
  fontWeight: 700,
  color: 'var(--text-primary)',
}


const loadingStyle: CSSProperties = {
  color: 'var(--text-secondary)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

const emptyStyle: CSSProperties = {
  color: 'var(--text-secondary)',
  fontSize: 13,
  padding: '40px 0',
  textAlign: 'center',
  fontStyle: 'italic',
}

const errorStyle: CSSProperties = {
  color: 'var(--accent-red)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

// ── Helpers ──

function statusBadge(status: string): CSSProperties {
  let bg: string
  let fg: string
  switch (status.toLowerCase()) {
    case 'ok':
    case 'success':
    case 'completed':
    case 'done':
      bg = 'rgba(0, 230, 118, 0.12)'; fg = 'var(--accent-green)'; break
    case 'running':
      bg = 'rgba(0, 229, 255, 0.12)'; fg = 'var(--accent-cyan)'; break
    case 'failed':
    case 'error':
      bg = 'rgba(255, 23, 68, 0.12)'; fg = 'var(--accent-red)'; break
    default:
      bg = 'rgba(136, 136, 170, 0.12)'; fg = 'var(--text-secondary)'; break
  }
  return {
    display: 'inline-block',
    padding: '3px 10px',
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 700,
    backgroundColor: bg,
    color: fg,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  }
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatScore(score: number | null): string {
  if (score == null) return '-'
  return score.toFixed(4)
}

// ── Detail View ──

function RunDetail({
  run, onClose, onRefresh,
}: {
  run: RunSummary
  onClose: () => void
  onRefresh: () => void
}) {
  const artifacts = run.artifacts ? Object.values(run.artifacts) : []

  return (
    <div style={detailPanel}>
      <div style={detailHeader}>
        <div style={detailTitle}>Run {run.run_id}</div>
        <button style={closeBtn} onClick={onClose}>Close</button>
      </div>

      {/* Summary cards */}
      <div style={summaryGrid}>
        <div style={summaryCard}>
          <div style={summaryLabel}>Experiment</div>
          <div style={summaryValue}>{run.experiment || '-'}</div>
        </div>
        <div style={summaryCard}>
          <div style={summaryLabel}>Subject</div>
          <div style={summaryValue}>{run.subject || '-'}</div>
        </div>
        <div style={summaryCard}>
          <div style={summaryLabel}>Mean Score</div>
          <div style={{ ...summaryValue, color: run.mean_score != null ? 'var(--accent-green)' : 'var(--text-secondary)' }}>
            {formatScore(run.mean_score)}
          </div>
        </div>
        <div style={summaryCard}>
          <div style={summaryLabel}>Duration</div>
          <div style={summaryValue}>
            {run.total_elapsed_s < 60
              ? `${run.total_elapsed_s.toFixed(1)}s`
              : `${Math.floor(run.total_elapsed_s / 60)}m ${(run.total_elapsed_s % 60).toFixed(0)}s`}
          </div>
        </div>
        <div style={summaryCard}>
          <div style={summaryLabel}>Status</div>
          <div><span style={statusBadge(run.status)}>{run.status}</span></div>
        </div>
        <div style={summaryCard}>
          <div style={summaryLabel}>Output</div>
          <div style={{ ...summaryValue, fontSize: 11, fontFamily: 'monospace', wordBreak: 'break-all' }}>
            {run.output_dir || '-'}
          </div>
        </div>
      </div>

      {/* Stage timeline */}
      {run.stages && run.stages.length > 0 && (
        <>
          <div style={sectionLabel}>Stage Timeline</div>
          <StageTimeline stages={run.stages} />
        </>
      )}

      {/* Artifacts */}
      {artifacts.length > 0 && (
        <>
          <div style={sectionLabel}>Results ({artifacts.length})</div>
          <SortableArtifactList
            artifacts={artifacts}
            runId={run.run_id}
            onArtifactDeleted={onRefresh}
          />
        </>
      )}

      {/* Log tail */}
      {run.log_tail && (
        <>
          <div style={sectionLabel}>Log (tail)</div>
          <pre
            style={{
              backgroundColor: 'var(--bg-secondary)',
              padding: '12px 14px',
              borderRadius: 6,
              fontSize: 11,
              lineHeight: 1.6,
              color: 'var(--text-secondary)',
              overflow: 'auto',
              maxHeight: 300,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}
          >
            {run.log_tail}
          </pre>
        </>
      )}
    </div>
  )
}

// ── Main View ──

export function RunManager() {
  const {
    runs, selectedRun, loading, error, loadRuns, selectRun, clearSelection,
    compareIds, compareSelection, comparing, toggleCompare, clearCompare,
    openComparison, closeComparison,
  } = useRunStore()

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  const handleRefresh = useCallback(() => {
    loadRuns()
  }, [loadRuns])

  if (error) {
    return <div style={errorStyle}>Error loading runs: {error}</div>
  }

  return (
    <div>
      <div style={headerStyle}>
        <div style={titleStyle}>Run History</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {compareIds.length > 0 && (
            <>
              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                {compareIds.length}/{COMPARE_MAX} selected
                {compareIds.length < 2 && ' (need 2+)'}
              </span>
              <button
                style={{
                  padding: '8px 16px',
                  fontSize: 12,
                  fontWeight: 600,
                  fontFamily: 'inherit',
                  borderRadius: 6,
                  border: 'none',
                  cursor: compareIds.length >= 2 ? 'pointer' : 'not-allowed',
                  backgroundColor: compareIds.length >= 2 ? 'var(--accent-cyan)' : 'var(--bg-input)',
                  color: compareIds.length >= 2 ? '#000' : 'var(--text-secondary)',
                  opacity: comparing ? 0.6 : 1,
                }}
                disabled={compareIds.length < 2 || comparing}
                onClick={openComparison}
              >
                {comparing ? 'Loading...' : `Compare (${compareIds.length})`}
              </button>
              <button style={refreshBtn} onClick={clearCompare}>
                Clear
              </button>
            </>
          )}
          <button style={refreshBtn} onClick={handleRefresh} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {loading && runs.length === 0 ? (
        <div style={loadingStyle}>Loading runs...</div>
      ) : runs.length === 0 ? (
        <div style={emptyStyle}>No runs yet. Configure and launch a pipeline to see results here.</div>
      ) : (
        <div style={tableContainerStyle}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={{ ...thStyle, width: 32 }}></th>
                <th style={thStyle}>Date</th>
                <th style={thStyle}>Experiment</th>
                <th style={thStyle}>Subject</th>
                <th style={thStyle}>Model</th>
                <th style={thStyle}>Mean Score</th>
                <th style={thStyle}>Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const isSelected = selectedRun?.run_id === run.run_id
                const isCompare = compareIds.includes(run.run_id)
                return (
                  <tr
                    key={run.run_id}
                    style={rowStyle(isSelected)}
                    onClick={() => (isSelected ? clearSelection() : selectRun(run.run_id))}
                    onMouseEnter={(e) => {
                      if (!isSelected) (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(0, 229, 255, 0.03)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent'
                    }}
                  >
                    <td style={{ ...tdStyle, textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isCompare}
                        onChange={() => toggleCompare(run.run_id)}
                        title="Select to compare with another run"
                      />
                    </td>
                    <td style={tdStyle}>{formatDate(run.started_at)}</td>
                    <td style={{ ...tdStyle, color: 'var(--accent-cyan)', fontWeight: 600 }}>
                      {run.experiment || '-'}
                    </td>
                    <td style={tdStyle}>{run.subject || '-'}</td>
                    <td style={tdStyle}>
                      {(run.config_snapshot as any)?.model?.type || '-'}
                    </td>
                    <td style={{
                      ...tdStyle,
                      color: run.mean_score != null ? 'var(--accent-green)' : 'var(--text-secondary)',
                      fontWeight: 600,
                    }}>
                      {formatScore(run.mean_score)}
                    </td>
                    <td style={tdStyle}>
                      <span style={statusBadge(run.status)}>{run.status}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail panel */}
      {selectedRun && (
        <RunDetail
          run={selectedRun}
          onClose={clearSelection}
          onRefresh={() => selectRun(selectedRun.run_id)}
        />
      )}

      {/* Comparison overlay */}
      {compareSelection && (
        <RunComparison runs={compareSelection} onClose={closeComparison} />
      )}
    </div>
  )
}
