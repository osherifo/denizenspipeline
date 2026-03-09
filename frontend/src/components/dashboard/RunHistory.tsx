/** Run history table scoped to a config's experiment+subject. */
import type { RunSummary, ArtifactInfo } from '../../api/types'
import { StageTimeline } from '../runs/StageTimeline'
import { artifactUrl } from '../../api/client'

interface RunHistoryProps {
  runs: RunSummary[]
  selectedRun: RunSummary | null
  loading: boolean
  onSelectRun: (runId: string) => void
  onClearRun: () => void
}

const containerStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
  marginBottom: 16,
}

const headerStyle: React.CSSProperties = {
  padding: '12px 16px',
  fontSize: 12,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
}

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 12,
}

const thStyle: React.CSSProperties = {
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

const tdStyle: React.CSSProperties = {
  padding: '8px 12px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

const rowStyle = (selected: boolean): React.CSSProperties => ({
  cursor: 'pointer',
  backgroundColor: selected ? 'rgba(0, 229, 255, 0.05)' : 'transparent',
})

function statusBadge(status: string): React.CSSProperties {
  let bg: string; let fg: string
  switch (status.toLowerCase()) {
    case 'ok': case 'done': bg = 'rgba(0, 230, 118, 0.12)'; fg = 'var(--accent-green)'; break
    case 'running': bg = 'rgba(0, 229, 255, 0.12)'; fg = 'var(--accent-cyan)'; break
    case 'failed': bg = 'rgba(255, 23, 68, 0.12)'; fg = 'var(--accent-red)'; break
    case 'warning': bg = 'rgba(255, 214, 0, 0.12)'; fg = 'var(--accent-yellow)'; break
    default: bg = 'rgba(136, 136, 170, 0.12)'; fg = 'var(--text-secondary)'; break
  }
  return {
    display: 'inline-block', padding: '2px 8px', borderRadius: 3,
    fontSize: 10, fontWeight: 700, backgroundColor: bg, color: fg, textTransform: 'uppercase',
  }
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

function formatDuration(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const detailPanel: React.CSSProperties = {
  padding: '16px',
  borderTop: '1px solid var(--border)',
  backgroundColor: 'var(--bg-secondary)',
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)',
  textTransform: 'uppercase', letterSpacing: 1, marginTop: 16, marginBottom: 8,
}

const summaryGrid: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
  gap: 8, marginBottom: 12,
}

const summaryCard: React.CSSProperties = {
  backgroundColor: 'var(--bg-card)', borderRadius: 6, padding: '8px 10px',
}

const summaryCardLabel: React.CSSProperties = {
  fontSize: 9, fontWeight: 600, color: 'var(--text-secondary)',
  textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2,
}

const summaryCardValue: React.CSSProperties = {
  fontSize: 13, fontWeight: 700, color: 'var(--text-primary)',
}

export function RunHistory({ runs, selectedRun, loading, onSelectRun, onClearRun }: RunHistoryProps) {
  if (runs.length === 0 && !loading) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>Run History</div>
        <div style={{ padding: '24px 16px', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
          No runs yet for this config
        </div>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Run History ({runs.length})</div>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>Date</th>
            <th style={thStyle}>Score</th>
            <th style={thStyle}>Duration</th>
            <th style={thStyle}>Status</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const isSelected = selectedRun?.run_id === run.run_id
            return (
              <tr
                key={run.run_id}
                style={rowStyle(isSelected)}
                onClick={() => isSelected ? onClearRun() : onSelectRun(run.run_id)}
              >
                <td style={tdStyle}>{formatDate(run.started_at)}</td>
                <td style={{
                  ...tdStyle, fontWeight: 600,
                  color: run.mean_score != null ? 'var(--accent-green)' : 'var(--text-secondary)',
                }}>
                  {run.mean_score != null ? run.mean_score.toFixed(4) : '-'}
                </td>
                <td style={tdStyle}>{formatDuration(run.total_elapsed_s)}</td>
                <td style={tdStyle}><span style={statusBadge(run.status)}>{run.status}</span></td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* Expanded run detail */}
      {selectedRun && (
        <div style={detailPanel}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-cyan)' }}>
              Run {selectedRun.run_id}
            </span>
            <button
              style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}
              onClick={onClearRun}
            >
              Close
            </button>
          </div>

          <div style={summaryGrid}>
            <div style={summaryCard}>
              <div style={summaryCardLabel}>Score</div>
              <div style={{
                ...summaryCardValue,
                color: selectedRun.mean_score != null ? 'var(--accent-green)' : 'var(--text-secondary)',
              }}>
                {selectedRun.mean_score != null ? selectedRun.mean_score.toFixed(4) : '-'}
              </div>
            </div>
            <div style={summaryCard}>
              <div style={summaryCardLabel}>Duration</div>
              <div style={summaryCardValue}>{formatDuration(selectedRun.total_elapsed_s)}</div>
            </div>
            <div style={summaryCard}>
              <div style={summaryCardLabel}>Status</div>
              <div><span style={statusBadge(selectedRun.status)}>{selectedRun.status}</span></div>
            </div>
            <div style={summaryCard}>
              <div style={summaryCardLabel}>Output</div>
              <div style={{ ...summaryCardValue, fontSize: 9, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {selectedRun.output_dir || '-'}
              </div>
            </div>
          </div>

          {selectedRun.stages?.length > 0 && (
            <>
              <div style={sectionLabel}>Stage Timeline</div>
              <StageTimeline stages={selectedRun.stages} />
            </>
          )}

          {selectedRun.artifacts && Object.keys(selectedRun.artifacts).length > 0 && (
            <>
              <div style={sectionLabel}>Artifacts</div>
              {Object.values(selectedRun.artifacts).map((art: ArtifactInfo) => (
                <div key={art.name} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 10px', backgroundColor: 'var(--bg-card)', borderRadius: 4, marginBottom: 4, fontSize: 11,
                }}>
                  <span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{art.name}</span>
                    <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>{formatSize(art.size)}</span>
                  </span>
                  <a
                    href={artifactUrl(selectedRun.run_id, art.name)}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--accent-cyan)', textDecoration: 'none', fontWeight: 600 }}
                  >
                    View
                  </a>
                </div>
              ))}
            </>
          )}

          {selectedRun.log_tail && (
            <>
              <div style={sectionLabel}>Log (tail)</div>
              <pre style={{
                backgroundColor: 'var(--bg-card)', padding: '10px 12px', borderRadius: 6,
                fontSize: 10, lineHeight: 1.6, color: 'var(--text-secondary)',
                overflow: 'auto', maxHeight: 200, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              }}>
                {selectedRun.log_tail}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  )
}
