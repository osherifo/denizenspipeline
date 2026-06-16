import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { useGroupRunsStore } from '../stores/group-runs-store'
import { AnalysisGraphModal } from '../components/workflow/AnalysisGraphModal'
import { ConfigSnapshotModal } from '../components/runs/ConfigSnapshotModal'
import type { GraphTarget } from '../api/run-graph'
import type {
  GroupRunListing,
  GroupRunDetail,
  GroupSubjectSummary,
  GroupSubjectStage,
} from '../api/types'
import { formatDuration as formatElapsed } from '../utils/format'

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
          {run.run_id ? <code>{run.run_id}</code> : <em>legacy</em>}
          {' · '}{run.n_subjects} subjects
          {' · '}{formatTimestamp(run.started_at)}
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

function SubjectsTable({
  detail, onOpenSubjectGraph,
}: {
  detail: GroupRunDetail
  onOpenSubjectGraph?: (subject: string) => void
}) {
  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={thStyle}>Subject</th>
          <th style={thStyle}>Status</th>
          <th style={thStyle}>Elapsed</th>
          <th style={thStyle}>Stages</th>
          <th style={thStyle} />
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
              <td style={{ ...tdStyle, textAlign: 'right' }}>
                {onOpenSubjectGraph && (
                  <button
                    style={{
                      padding: '2px 8px', fontSize: 10, fontWeight: 600,
                      border: '1px solid rgba(0, 229, 255, 0.4)', borderRadius: 3,
                      background: 'rgba(0, 229, 255, 0.08)',
                      color: 'var(--accent-cyan)', cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                    onClick={() => onOpenSubjectGraph(s.subject)}
                  >
                    Graph
                  </button>
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

const linkBtn: CSSProperties = {
  color: 'var(--accent-cyan)',
  fontSize: 12,
  textDecoration: 'none',
  border: '1px solid rgba(0, 229, 255, 0.25)',
  padding: '4px 10px',
  borderRadius: 4,
}

const thumbGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
  gap: 10,
  padding: '8px 16px 16px',
}

const thumbCard: CSSProperties = {
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: 6,
  backgroundColor: 'var(--bg-secondary)',
  fontSize: 11,
  color: 'var(--text-secondary)',
}

const thumbImg: CSSProperties = {
  width: '100%',
  height: 'auto',
  display: 'block',
  cursor: 'zoom-in',
  borderRadius: 4,
}

/** Build the artifact-serving URL for one file inside the current run. */
function fileUrl(detail: GroupRunDetail, relPath: string): string {
  const name = encodeURIComponent(detail.group_name)
  if (detail.run_id) {
    return `/api/group-runs/${name}/${encodeURIComponent(detail.run_id)}/file/${relPath}`
  }
  return `/api/group-runs/${name}/file/${relPath}`
}

function isImage(path: string): boolean {
  return /\.(png|jpg|jpeg|svg)$/i.test(path)
}

function ArtifactGrid({
  detail, paths, basename,
}: { detail: GroupRunDetail; paths: string[]; basename?: (p: string) => string }) {
  if (paths.length === 0) return null
  const baseFn = basename ?? ((p: string) => p.split('/').pop() ?? p)
  return (
    <div style={thumbGrid}>
      {paths.map((p) => {
        const url = fileUrl(detail, p)
        const label = baseFn(p)
        return (
          <div key={p} style={thumbCard}>
            {isImage(p) ? (
              <a href={url} target="_blank" rel="noreferrer">
                <img src={url} alt={label} style={thumbImg} loading="lazy" />
              </a>
            ) : (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                style={{ color: 'var(--accent-cyan)', textDecoration: 'none' }}
              >
                ⬇ {label}
              </a>
            )}
            <div style={{ marginTop: 4, wordBreak: 'break-all' }}>{label}</div>
          </div>
        )
      })}
    </div>
  )
}

// Collapsible per-subject stage breakdown (stimuli…report with elapsed),
// mirroring the study view's drill-down so group runs expose timings down to
// every stage — not just the per-subject stage count in SubjectsTable.
function SubjectStageDetails({ detail }: { detail: GroupRunDetail }) {
  if (!detail.subject_summaries.length) {
    return <div style={emptyState}>No per-subject stages recorded.</div>
  }
  return (
    <div style={{ padding: '2px 16px 8px' }}>
      {detail.subject_summaries.map((s) => {
        const failed = (s.stages ?? []).some((st) => st.status === 'failed')
        return (
          <details key={s.subject} style={{ margin: '4px 0' }}>
            <summary style={{ cursor: 'pointer', padding: '4px 0', ...monoSmall }}>
              {s.subject} — {formatElapsed(s.total_elapsed_s)}
              {failed && ' · ⚠ failed'}
            </summary>
            <StagesTable stages={s.stages} />
          </details>
        )
      })}
    </div>
  )
}


function DetailPanel({
  detail, onOpenGraph,
}: {
  detail: GroupRunDetail
  onOpenGraph: (target: GraphTarget, title: string) => void
}) {
  const subjectsArt = detail.artifacts?.subjects ?? {}
  const groupArt = detail.artifacts?.group ?? []
  const [yamlOpen, setYamlOpen] = useState(false)
  return (
    <div style={cardStyle}>
      <div style={{ padding: '16px 18px' }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>{detail.group_name}</div>
        {detail.run_id && (
          <div style={{ ...monoSmall, marginTop: 2 }}>
            <code>{detail.run_id}</code>
          </div>
        )}
        <div style={{ ...monoSmall, marginTop: 4 }}>
          {detail.subjects.length} subjects · started{' '}
          {formatTimestamp(detail.started_at)} · {formatElapsed(detail.total_elapsed_s)} total
        </div>
        <div style={{ ...monoSmall, marginTop: 4 }}>
          <code>{detail.run_dir}</code>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {detail.html_report && (
            <a
              href={fileUrl(detail, detail.html_report)}
              target="_blank"
              rel="noreferrer"
              style={linkBtn}
            >
              Open HTML report ↗
            </a>
          )}
          {detail.group_log && (
            <a
              href={fileUrl(detail, detail.group_log)}
              target="_blank"
              rel="noreferrer"
              style={linkBtn}
            >
              Open group.log ↗
            </a>
          )}
          <button
            style={{
              ...linkBtn,
              cursor: 'pointer', fontFamily: 'inherit',
              background: 'rgba(0, 229, 255, 0.08)',
              border: '1px solid rgba(0, 229, 255, 0.4)',
              color: 'var(--accent-cyan)',
            }}
            onClick={() => onOpenGraph(
              { kind: 'group', groupName: detail.group_name, runId: detail.run_id },
              `${detail.group_name}/${detail.run_id} — group graph`,
            )}
            title="Show the group pipeline graph (click a subject to drill in)"
          >
            View graph
          </button>
          <button
            style={{
              ...linkBtn,
              cursor: 'pointer', fontFamily: 'inherit',
              background: 'rgba(0, 229, 255, 0.08)',
              border: '1px solid rgba(0, 229, 255, 0.4)',
              color: 'var(--accent-cyan)',
            }}
            onClick={() => setYamlOpen(true)}
            title="View the resolved YAML config that produced this group run"
            disabled={!detail.config_snapshot}
          >
            View YAML
          </button>
        </div>
      </div>

      {yamlOpen && (
        <ConfigSnapshotModal
          snapshot={detail.config_snapshot}
          title={`${detail.group_name}/${detail.run_id} — group config snapshot`}
          downloadName={`${detail.group_name}_${detail.run_id}.yaml`}
          onClose={() => setYamlOpen(false)}
        />
      )}
      <div style={sectionTitle}>Subjects</div>
      <SubjectsTable
        detail={detail}
        onOpenSubjectGraph={(sub) => onOpenGraph(
          { kind: 'group-subject', groupName: detail.group_name, runId: detail.run_id, subject: sub },
          `${detail.group_name}/${detail.run_id} · ${sub} — subject graph`,
        )}
      />
      <div style={sectionTitle}>Group stages</div>
      <StagesTable stages={detail.group_stages} />
      <div style={sectionTitle}>Per-subject stage timings</div>
      <SubjectStageDetails detail={detail} />
      {groupArt.length > 0 && (
        <>
          <div style={sectionTitle}>Group artifacts</div>
          <ArtifactGrid detail={detail} paths={groupArt} />
        </>
      )}
      {Object.entries(subjectsArt).map(([sub, paths]) => (
        <div key={sub}>
          <div style={sectionTitle}>{`Subject ${sub}`}</div>
          <ArtifactGrid
            detail={detail}
            paths={paths}
            basename={(p) => p.split('/').pop() ?? p}
          />
        </div>
      ))}
    </div>
  )
}

// ── View ──

export function GroupRunsView() {
  const {
    runs, selected, selectedKey, loading, loadingDetail, error,
    loadRuns, selectRun,
  } = useGroupRunsStore()
  const [graph, setGraph] = useState<{ target: GraphTarget; title: string } | null>(null)

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
                {runs.map((r) => {
                  const key = r.run_id ? `${r.group_name}/${r.run_id}` : r.group_name
                  return (
                    <RunListItem
                      key={key}
                      run={r}
                      selected={selectedKey === key}
                      onClick={() => selectRun(r.group_name, r.run_id)}
                    />
                  )
                })}
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
            <DetailPanel
              detail={selected}
              onOpenGraph={(target, title) => setGraph({ target, title })}
            />
          ) : (
            <div style={{ ...cardStyle, padding: 24, color: 'var(--text-secondary)' }}>
              Select a group run to see per-subject status and group stages.
            </div>
          )}
        </div>
      </div>

      {graph && (
        <AnalysisGraphModal
          target={graph.target}
          title={graph.title}
          onClose={() => setGraph(null)}
        />
      )}
    </div>
  )
}
