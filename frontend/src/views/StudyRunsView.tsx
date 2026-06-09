/** Study Runs view — list invocations on the left, detail panel right.
 *
 * Mirrors GroupRunsView one scope up: detail panel shows the included
 * groups (with status pills), study-stage timings, the study.log /
 * study_summary.html links, and a thumbnail grid for study + per-group
 * artifacts (served over HTTP via /api/study-runs/.../file/...).
 *
 * "View graph" opens the AnalysisGraphModal with a 'study' target;
 * clicking a group node inside that graph drills into the group's
 * full graph via {kind: 'study-group'}.
 */

import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { useStudyRunsStore } from '../stores/study-runs-store'
import { AnalysisGraphModal } from '../components/workflow/AnalysisGraphModal'
import type { GraphTarget } from '../api/run-graph'
import type { StudyRunDetail, StudyRunListing } from '../api/types'


// ── styles ────────────────────────────────────────────────────────────


const headerStyle: CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  marginBottom: 24,
}

const titleStyle: CSSProperties = {
  fontSize: 22, fontWeight: 700, color: 'var(--text-primary)',
}

const refreshBtn: CSSProperties = {
  padding: '8px 20px', fontSize: 12, fontWeight: 600,
  backgroundColor: 'rgba(0, 229, 255, 0.08)',
  border: '1px solid rgba(0, 229, 255, 0.25)',
  borderRadius: 6, color: 'var(--accent-cyan)',
  cursor: 'pointer', letterSpacing: 0.5,
}

const layoutStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(320px, 1fr) minmax(420px, 2fr)',
  gap: 20, alignItems: 'start',
}

const cardStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8, overflow: 'hidden',
}

const tableStyle: CSSProperties = {
  width: '100%', borderCollapse: 'collapse', fontSize: 13,
}

const thStyle: CSSProperties = {
  textAlign: 'left', padding: '10px 14px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-secondary)', fontWeight: 700,
  fontSize: 11, textTransform: 'uppercase', letterSpacing: 1,
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
  padding: '10px 16px', fontSize: 11, fontWeight: 700,
  color: 'var(--text-secondary)', textTransform: 'uppercase',
  letterSpacing: 1, backgroundColor: 'var(--bg-secondary)',
  borderTop: '1px solid var(--border)',
  borderBottom: '1px solid var(--border)',
}

const monoSmall: CSSProperties = {
  fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'monospace',
  wordBreak: 'break-all',
}

const emptyState: CSSProperties = {
  padding: '40px 16px', fontSize: 13, color: 'var(--text-secondary)',
  textAlign: 'center',
}

const linkBtn: CSSProperties = {
  color: 'var(--accent-cyan)', fontSize: 12,
  textDecoration: 'none',
  border: '1px solid rgba(0, 229, 255, 0.25)',
  padding: '4px 10px', borderRadius: 4,
}

const thumbGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
  gap: 10, padding: '8px 16px 16px',
}

const thumbCard: CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 6, padding: 6,
  backgroundColor: 'var(--bg-secondary)',
  fontSize: 11, color: 'var(--text-secondary)',
}

const thumbImg: CSSProperties = {
  width: '100%', height: 'auto', display: 'block',
  cursor: 'zoom-in', borderRadius: 4,
}


// ── helpers ───────────────────────────────────────────────────────────


function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}


function formatElapsed(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`
}


function statusPill(status: string): CSSProperties {
  const color =
    status === 'ok' ? 'var(--accent-green)' :
    status === 'failed' ? 'var(--accent-red)' :
    status === 'warning' ? 'var(--accent-yellow)' :
    'var(--text-secondary)'
  return {
    display: 'inline-block', padding: '2px 8px', borderRadius: 3,
    fontSize: 10, fontWeight: 700,
    backgroundColor: `${color}22`, color, textTransform: 'uppercase',
  }
}


function fileUrl(detail: StudyRunDetail, relPath: string): string {
  const name = encodeURIComponent(detail.study_name)
  const rid = encodeURIComponent(detail.run_id)
  return `/api/study-runs/${name}/${rid}/file/${relPath}`
}


function isImage(path: string): boolean {
  return /\.(png|jpg|jpeg|svg)$/i.test(path)
}


// ── subcomponents ─────────────────────────────────────────────────────


function RunListItem({
  run, selected, onClick,
}: { run: StudyRunListing; selected: boolean; onClick: () => void }) {
  const status =
    (run.status_counts?.failed ?? 0) > 0 ? 'failed' :
    (run.status_counts?.ok ?? 0) > 0 ? 'ok' : 'unknown'
  return (
    <tr style={rowStyle(selected)} onClick={onClick}>
      <td style={tdStyle}>
        <div style={{ fontWeight: 600 }}>{run.study_name}</div>
        <div style={monoSmall}>
          <code>{run.run_id}</code> · {formatTimestamp(run.started_at)}
        </div>
        <div style={{ ...monoSmall, marginTop: 2 }}>
          {run.n_groups} group{run.n_groups !== 1 ? 's' : ''}
          {' · '}{formatElapsed(run.total_elapsed_s)}
        </div>
      </td>
      <td style={{ ...tdStyle, textAlign: 'right' }}>
        <span style={statusPill(status)}>{status}</span>
      </td>
    </tr>
  )
}


function GroupsTable({ detail }: { detail: StudyRunDetail }) {
  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={thStyle}>Label</th>
          <th style={thStyle}>Group name</th>
          <th style={thStyle}>Run ID</th>
          <th style={thStyle}>Elapsed</th>
          <th style={thStyle}>Status</th>
        </tr>
      </thead>
      <tbody>
        {detail.group_summaries.map((g, i) => {
          const a = g as Record<string, any>
          const label = detail.group_labels[i] || a.group_name || '?'
          const subjects = (a.subject_summaries ?? []) as Array<Record<string, any>>
          const nFailed = subjects.filter((s) =>
            (s.stages ?? []).some((st: any) => st.status === 'failed'),
          ).length
          const status = nFailed > 0 ? 'failed' : 'ok'
          return (
            <tr key={`${label}-${i}`}>
              <td style={tdStyle}>{label}</td>
              <td style={tdStyle}>{a.group_name ?? '?'}</td>
              <td style={tdStyle}><code style={monoSmall}>{a.run_id ?? '—'}</code></td>
              <td style={tdStyle}>{formatElapsed(a.total_elapsed_s ?? 0)}</td>
              <td style={tdStyle}>
                <span style={statusPill(status)}>
                  {status}
                  {nFailed > 0 && ` (${nFailed} failed)`}
                </span>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}


function StagesTable({ detail }: { detail: StudyRunDetail }) {
  if (!detail.study_stages.length) {
    return <div style={emptyState}>No study stages recorded.</div>
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
        {detail.study_stages.map((s, i) => (
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


function ArtifactGrid({
  detail, paths,
}: { detail: StudyRunDetail; paths: string[] }) {
  if (paths.length === 0) return null
  return (
    <div style={thumbGrid}>
      {paths.map((p) => {
        const url = fileUrl(detail, p)
        const label = p.split('/').pop() ?? p
        return (
          <div key={p} style={thumbCard}>
            {isImage(p) ? (
              <a href={url} target="_blank" rel="noreferrer">
                <img src={url} alt={label} style={thumbImg} loading="lazy" />
              </a>
            ) : (
              <a href={url} target="_blank" rel="noreferrer"
                 style={{ color: 'var(--accent-cyan)', textDecoration: 'none' }}>
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


function DetailPanel({
  detail, onOpenGraph,
}: {
  detail: StudyRunDetail
  onOpenGraph: (target: GraphTarget, title: string) => void
}) {
  const studyArt = detail.artifacts?.study ?? []
  const groupArt = detail.artifacts?.groups ?? {}
  return (
    <div style={cardStyle}>
      <div style={{ padding: '16px 18px' }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>{detail.study_name}</div>
        <div style={{ ...monoSmall, marginTop: 2 }}>
          <code>{detail.run_id}</code>
        </div>
        <div style={{ ...monoSmall, marginTop: 4 }}>
          {detail.group_labels.length} group{detail.group_labels.length !== 1 ? 's' : ''} ·
          started {formatTimestamp(detail.started_at)} ·
          {' '}{formatElapsed(detail.total_elapsed_s)} total
        </div>
        <div style={{ ...monoSmall, marginTop: 4 }}>
          <code>{detail.run_dir}</code>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {detail.html_report && (
            <a href={fileUrl(detail, detail.html_report)} target="_blank"
               rel="noreferrer" style={linkBtn}>
              Open HTML report ↗
            </a>
          )}
          {detail.study_log && (
            <a href={fileUrl(detail, detail.study_log)} target="_blank"
               rel="noreferrer" style={linkBtn}>
              Open study.log ↗
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
              { kind: 'study', studyName: detail.study_name, runId: detail.run_id },
              `${detail.study_name}/${detail.run_id} — study graph`,
            )}
            title="Show the study pipeline graph (click a group to drill in)"
          >
            View graph
          </button>
        </div>
      </div>
      <div style={sectionTitle}>Groups</div>
      <GroupsTable detail={detail} />
      <div style={sectionTitle}>Study stages</div>
      <StagesTable detail={detail} />
      {studyArt.length > 0 && (
        <>
          <div style={sectionTitle}>Study artifacts</div>
          <ArtifactGrid detail={detail} paths={studyArt} />
        </>
      )}
      {Object.entries(groupArt).map(([label, files]) => (
        <div key={label}>
          <div style={sectionTitle}>Group · {label}</div>
          <ArtifactGrid detail={detail} paths={files} />
        </div>
      ))}
    </div>
  )
}


// ── view ──────────────────────────────────────────────────────────────


export function StudyRunsView() {
  const {
    runs, selected, selectedKey, loading, loadingDetail, error,
    loadRuns, selectRun,
  } = useStudyRunsStore()
  const [graph, setGraph] = useState<{ target: GraphTarget; title: string } | null>(null)

  useEffect(() => { loadRuns() }, [loadRuns])

  return (
    <div>
      <div style={headerStyle}>
        <div style={titleStyle}>Study Runs</div>
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
            <div style={emptyState}>Loading study runs…</div>
          ) : runs.length === 0 ? (
            <div style={emptyState}>
              No study runs found.<br />
              <span style={{ fontSize: 12 }}>
                Run <code>fmriflow run-study &lt;config&gt;.yaml</code> to create one.
              </span>
            </div>
          ) : (
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={thStyle}>Study</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => {
                  const key = `${r.study_name}/${r.run_id}`
                  return (
                    <RunListItem
                      key={key}
                      run={r}
                      selected={selectedKey === key}
                      onClick={() => selectRun(r.study_name, r.run_id)}
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
              Loading study detail…
            </div>
          ) : selected ? (
            <DetailPanel
              detail={selected}
              onOpenGraph={(target, title) => setGraph({ target, title })}
            />
          ) : (
            <div style={{ ...cardStyle, padding: 24, color: 'var(--text-secondary)' }}>
              Select a study run to see its groups, stages, and artifacts.
            </div>
          )}
        </div>
      </div>

      {graph && (
        <AnalysisGraphModal
          target={graph.target}
          title={graph.title}
          onClose={() => setGraph(null)}
          onGroupClick={(label) => {
            if (graph.target.kind === 'study') {
              setGraph({
                target: {
                  kind: 'study-group',
                  studyName: graph.target.studyName,
                  runId: graph.target.runId,
                  groupLabel: label,
                },
                title: `${graph.target.studyName}/${graph.target.runId} · ${label} — group graph`,
              })
            }
          }}
        />
      )}
    </div>
  )
}
