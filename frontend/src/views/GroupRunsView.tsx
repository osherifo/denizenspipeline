import { useEffect } from 'react'
import type { CSSProperties } from 'react'
import { useGroupRunsStore } from '../stores/group-runs-store'
import type {
  GroupRunListing,
  GroupRunDetail,
  GroupSubjectSummary,
  GroupSubjectStage,
} from '../api/types'

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

const layoutStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(320px, 1fr) minmax(420px, 2fr)',
  gap: 20,
  alignItems: 'start',
}

const cardStyle: CSSProperties = {
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
  padding: '10px 14px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  fontWeight: 700,
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const tdStyle: CSSProperties = {
  padding: '8px 14px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

const rowStyle = (selected: boolean): CSSProperties => ({
  cursor: 'pointer',
  backgroundColor: selected ? 'rgba(0, 229, 255, 0.06)' : 'transparent',
  transition: 'background-color 0.1s ease',
})

const sectionTitle: CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  margin: '20px 16px 8px',
}

const emptyState: CSSProperties = {
  padding: '32px 16px',
  textAlign: 'center',
  color: 'var(--text-secondary)',
  fontSize: 13,
}

const statusPill = (status: string): CSSProperties => {
  const color =
    status === 'ok'
      ? 'var(--accent-green)'
      : status === 'failed'
        ? 'var(--accent-red)'
        : status === 'warning'
          ? 'var(--accent-yellow)'
          : 'var(--text-secondary)'
  return {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 600,
    color,
    border: `1px solid ${color}`,
    backgroundColor: 'transparent',
    letterSpacing: 0.5,
  }
}

const monoSmall: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
}

// ── Helpers ──

function subjectStatus(s: GroupSubjectSummary): string {
  const statuses = new Set(s.stages.map((st) => st.status))
  if (statuses.has('failed')) return 'failed'
  if (statuses.has('warning')) return 'warning'
  if (statuses.size === 0) return 'unknown'
  return 'ok'
}

function formatElapsed(seconds: number): string {
  if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)}h`
  if (seconds >= 60) return `${(seconds / 60).toFixed(1)}m`
  return `${seconds.toFixed(1)}s`
}

function formatTimestamp(iso: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── Subcomponents ──

function RunListItem({
  run, selected, onClick,
}: { run: GroupRunListing; selected: boolean; onClick: () => void }) {
  return (
    <tr style={rowStyle(selected)} onClick={onClick}>
      <td style={tdStyle}>
        <div style={{ fontWeight: 600 }}>{run.group_name}</div>
        <div style={monoSmall}>
          {run.n_subjects} subjects · {formatTimestamp(run.started_at)}
        </div>
      </td>
      <td style={{ ...tdStyle, textAlign: 'right' }}>
        <span style={{ ...statusPill('ok'), marginRight: 4 }}>
          {run.status_counts.ok}
        </span>
        {run.status_counts.failed > 0 && (
          <span style={statusPill('failed')}>{run.status_counts.failed}</span>
        )}
      </td>
    </tr>
  )
}

function SubjectsTable({ detail }: { detail: GroupRunDetail }) {
  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={thStyle}>Subject</th>
          <th style={thStyle}>Status</th>
          <th style={thStyle}>Elapsed</th>
          <th style={thStyle}>Stages</th>
        </tr>
      </thead>
      <tbody>
        {detail.subject_summaries.map((s) => {
          const status = subjectStatus(s)
          const failed = s.stages.filter((st) => st.status === 'failed').length
          return (
            <tr key={s.subject}>
              <td style={tdStyle}>{s.subject}</td>
              <td style={tdStyle}><span style={statusPill(status)}>{status}</span></td>
              <td style={tdStyle}>{formatElapsed(s.total_elapsed_s)}</td>
              <td style={tdStyle}>
                {s.stages.length}
                {failed > 0 && (
                  <span style={{ color: 'var(--accent-red)' }}> ({failed} failed)</span>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function StagesTable({ stages }: { stages: GroupSubjectStage[] }) {
  if (stages.length === 0) {
    return <div style={emptyState}>No group stages recorded.</div>
  }
  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={thStyle}>Stage</th>
          <th style={thStyle}>Status</th>
          <th style={thStyle}>Elapsed</th>
          <th style={thStyle}>Detail</th>
        </tr>
      </thead>
      <tbody>
        {stages.map((s, i) => (
          <tr key={`${s.name}-${i}`}>
            <td style={tdStyle}>{s.name}</td>
            <td style={tdStyle}><span style={statusPill(s.status)}>{s.status}</span></td>
            <td style={tdStyle}>{formatElapsed(s.elapsed_s)}</td>
            <td style={{ ...tdStyle, color: 'var(--text-secondary)', fontSize: 12 }}>
              {s.detail || '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function DetailPanel({ detail }: { detail: GroupRunDetail }) {
  return (
    <div style={cardStyle}>
      <div style={{ padding: '16px 18px' }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>{detail.group_name}</div>
        <div style={{ ...monoSmall, marginTop: 4 }}>
          {detail.subjects.length} subjects · started{' '}
          {formatTimestamp(detail.started_at)} · {formatElapsed(detail.total_elapsed_s)} total
        </div>
        <div style={{ ...monoSmall, marginTop: 4 }}>
          <code>{detail.run_dir}</code>
        </div>
        {detail.html_report && (
          <div style={{ marginTop: 12 }}>
            <a
              href={`file://${detail.run_dir}/${detail.html_report}`}
              target="_blank"
              rel="noreferrer"
              style={{
                color: 'var(--accent-cyan)',
                fontSize: 12,
                textDecoration: 'none',
                border: '1px solid rgba(0, 229, 255, 0.25)',
                padding: '4px 10px',
                borderRadius: 4,
              }}
            >
              Open HTML report ↗
            </a>
          </div>
        )}
      </div>
      <div style={sectionTitle}>Subjects</div>
      <SubjectsTable detail={detail} />
      <div style={sectionTitle}>Group stages</div>
      <StagesTable stages={detail.group_stages} />
    </div>
  )
}

// ── View ──

export function GroupRunsView() {
  const {
    runs, selected, selectedName, loading, loadingDetail, error,
    loadRuns, selectRun,
  } = useGroupRunsStore()

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  return (
    <div>
      <div style={headerStyle}>
        <div style={titleStyle}>Group Runs</div>
        <button style={refreshBtn} onClick={() => loadRuns()}>
          Refresh
        </button>
      </div>
      {error && (
        <div style={{
          backgroundColor: 'rgba(255, 23, 68, 0.08)',
          border: '1px solid var(--accent-red)',
          color: 'var(--accent-red)',
          padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13,
        }}>
          {error}
        </div>
      )}
      <div style={layoutStyle}>
        <div style={cardStyle}>
          {loading && runs.length === 0 ? (
            <div style={emptyState}>Loading group runs…</div>
          ) : runs.length === 0 ? (
            <div style={emptyState}>
              No group runs found.<br />
              <span style={{ fontSize: 12 }}>
                Run <code>fmriflow run-group &lt;config&gt;.yaml</code> to create one.
              </span>
            </div>
          ) : (
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={thStyle}>Group</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <RunListItem
                    key={r.group_name}
                    run={r}
                    selected={selectedName === r.group_name}
                    onClick={() => selectRun(r.group_name)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div>
          {loadingDetail ? (
            <div style={{ ...cardStyle, padding: 24, color: 'var(--text-secondary)' }}>
              Loading group detail…
            </div>
          ) : selected ? (
            <DetailPanel detail={selected} />
          ) : (
            <div style={{ ...cardStyle, padding: 24, color: 'var(--text-secondary)' }}>
              Select a group run to see per-subject status and group stages.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
