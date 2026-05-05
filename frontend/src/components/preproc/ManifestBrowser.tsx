/** Tab 2: Left sidebar — manifest list + right panel — manifest details. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'
import { ManifestDetail } from './ManifestDetail'
import { fetchAllReviews } from '../../api/structural-qc'
import type { StructuralQCReview, StructuralQCStatus } from '../../api/types'

const QC_STATUS_COLOR: Record<StructuralQCStatus, string> = {
  pending: 'var(--text-secondary)',
  approved: 'var(--accent-green)',
  needs_edits: 'var(--accent-yellow)',
  rejected: 'var(--accent-red)',
}

const QC_STATUS_LABEL: Record<StructuralQCStatus, string> = {
  pending: 'pending',
  approved: 'approved',
  needs_edits: 'needs edits',
  rejected: 'rejected',
}

function QcPill({ status }: { status: StructuralQCStatus }) {
  const color = QC_STATUS_COLOR[status]
  return (
    <span
      style={{
        fontSize: 9,
        padding: '1px 6px',
        borderRadius: 8,
        background: status === 'pending' ? 'transparent' : `${color}22`,
        color,
        border: `1px solid ${color}66`,
        textTransform: 'uppercase',
        letterSpacing: 0.4,
        fontWeight: 700,
      }}
      title={`structural QC: ${QC_STATUS_LABEL[status]}`}
    >
      {QC_STATUS_LABEL[status]}
    </span>
  )
}

const containerStyle: CSSProperties = {
  display: 'flex',
  height: 'calc(100vh - 48px - 80px)',
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
}

const sidebarStyle: CSSProperties = {
  width: 240,
  backgroundColor: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const sidebarHeader: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '12px 16px',
  borderBottom: '1px solid var(--border)',
}

const sidebarTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const listStyle: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
}

const itemStyle = (active: boolean): CSSProperties => ({
  padding: '10px 16px',
  cursor: 'pointer',
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
  borderBottom: '1px solid var(--border)',
})

const mainPanel: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '20px 24px',
}

const emptyState: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--text-secondary)',
  fontSize: 13,
  gap: 8,
  height: '100%',
}

const rescanBtn: CSSProperties = {
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 4,
  cursor: 'pointer',
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
}

export function ManifestBrowser() {
  const {
    manifests, manifestsLoading, selectedSubject, selectedManifest,
    loadManifests, rescan, selectManifest,
  } = usePreprocStore()
  const [reviews, setReviews] = useState<Map<string, StructuralQCReview>>(
    new Map(),
  )

  useEffect(() => { loadManifests() }, [])

  // Reviews are fetched once per manifest list refresh and indexed by
  // `dataset|subject` so we can stamp a status pill on each row.
  useEffect(() => {
    let cancelled = false
    fetchAllReviews()
      .then((rs) => {
        if (cancelled) return
        const map = new Map<string, StructuralQCReview>()
        for (const r of rs) map.set(`${r.dataset}|${r.subject}`, r)
        setReviews(map)
      })
      .catch(() => { /* ignore — pill simply won't show */ })
    return () => { cancelled = true }
  }, [manifests.length])

  return (
    <div style={containerStyle}>
      <div style={sidebarStyle}>
        <div style={sidebarHeader}>
          <span style={sidebarTitle}>Manifests ({manifests.length})</span>
          <button style={rescanBtn} onClick={rescan} disabled={manifestsLoading}>
            {manifestsLoading ? '...' : 'Rescan'}
          </button>
        </div>
        <div style={listStyle}>
          {manifests.map((m) => {
            const review = reviews.get(`${m.dataset}|${m.subject}`)
            return (
              <div
                key={m.subject}
                style={itemStyle(selectedSubject === m.subject)}
                onClick={() => selectManifest(m.subject)}
              >
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span>sub-{m.subject}</span>
                  <span style={{ flex: 1 }} />
                  {review && <QcPill status={review.status} />}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                  {m.backend} {m.backend_version} &middot; {m.n_runs} runs
                </div>
              </div>
            )
          })}
          {manifests.length === 0 && !manifestsLoading && (
            <div style={{ padding: 16, fontSize: 11, color: 'var(--text-secondary)' }}>
              No manifests found. Use the Collect tab to create one, or check --derivatives-dir.
            </div>
          )}
        </div>
      </div>

      <div style={mainPanel}>
        {selectedManifest ? (
          <ManifestDetail manifest={selectedManifest} />
        ) : (
          <div style={emptyState}>
            <div style={{ fontSize: 28, color: 'var(--text-secondary)' }}>{'\u2630'}</div>
            <div>Select a manifest to view details</div>
          </div>
        )}
      </div>
    </div>
  )
}
