/** Cross-dataset list of structural-QC reviews.
 *
 * One row per (dataset, subject) review. Filter by status, click a row
 * to open the StructuralQCModal for that subject.
 */

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { fetchAllReviews } from '../api/structural-qc'
import type { StructuralQCReview, StructuralQCStatus } from '../api/types'
import { StructuralQCModal } from '../components/workflow/StructuralQCModal'

const STATUSES: { value: StructuralQCStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'needs_edits', label: 'Needs edits' },
  { value: 'rejected', label: 'Rejected' },
]

const STATUS_COLOR: Record<StructuralQCStatus, string> = {
  pending: 'var(--text-secondary)',
  approved: 'var(--accent-green)',
  needs_edits: 'var(--accent-yellow)',
  rejected: 'var(--accent-red)',
}

const pageTitle: CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 4,
}

const pageDesc: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  marginBottom: 16,
}

const filterRow: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 8,
  marginBottom: 12,
}

const filterBtn = (active: boolean): CSSProperties => ({
  padding: '4px 10px',
  fontSize: 11,
  fontWeight: 600,
  borderRadius: 4,
  border: '1px solid var(--border)',
  background: active ? 'var(--accent-cyan)' : 'var(--bg-secondary)',
  color: active ? '#000' : 'var(--text-primary)',
  cursor: 'pointer',
})

const tableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 12,
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  overflow: 'hidden',
}

const thStyle: CSSProperties = {
  textAlign: 'left',
  padding: '8px 12px',
  background: 'var(--bg-secondary)',
  color: 'var(--text-secondary)',
  borderBottom: '1px solid var(--border)',
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 0.5,
  textTransform: 'uppercase',
}

const tdStyle: CSSProperties = {
  padding: '10px 12px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

const trClickable: CSSProperties = {
  cursor: 'pointer',
}

function StatusPill({ status }: { status: StructuralQCStatus }) {
  const color = STATUS_COLOR[status]
  const label = status.replace('_', ' ')
  return (
    <span
      style={{
        fontSize: 10,
        padding: '2px 8px',
        borderRadius: 8,
        background: status === 'pending' ? 'transparent' : `${color}22`,
        color,
        border: `1px solid ${color}66`,
        textTransform: 'uppercase',
        letterSpacing: 0.4,
        fontWeight: 700,
      }}
    >
      {label}
    </span>
  )
}


export function QCReviews() {
  const [reviews, setReviews] = useState<StructuralQCReview[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<StructuralQCStatus | 'all'>('all')
  const [modalSubject, setModalSubject] = useState<string | null>(null)

  const reload = () => {
    setLoading(true)
    setError(null)
    fetchAllReviews()
      .then((r) => setReviews(r))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }
  useEffect(() => {
    reload()
  }, [])

  const counts = useMemo(() => {
    const c: Record<StructuralQCStatus, number> = {
      pending: 0, approved: 0, needs_edits: 0, rejected: 0,
    }
    for (const r of reviews) c[r.status] = (c[r.status] || 0) + 1
    return c
  }, [reviews])

  const filtered = useMemo(() => {
    if (filter === 'all') return reviews
    return reviews.filter((r) => r.status === filter)
  }, [reviews, filter])

  return (
    <div>
      <div style={pageTitle}>Structural QC reviews</div>
      <div style={pageDesc}>
        Reviewer sign-offs across all subjects, filed under
        <code style={{ marginLeft: 4 }}>~/.fmriflow/structural_qc/</code>.
        Click a row to reopen the panel for that subject.
      </div>

      <div style={filterRow}>
        {STATUSES.map((s) => {
          const count = s.value === 'all'
            ? reviews.length
            : counts[s.value as StructuralQCStatus]
          return (
            <button
              key={s.value}
              style={filterBtn(filter === s.value)}
              onClick={() => setFilter(s.value)}
            >
              {s.label} ({count})
            </button>
          )
        })}
        <span style={{ flex: 1 }} />
        <button
          style={filterBtn(false)}
          onClick={reload}
          disabled={loading}
        >
          {loading ? '…' : 'Reload'}
        </button>
      </div>

      {error && (
        <div style={{ color: 'var(--accent-red)', fontSize: 12, marginBottom: 8 }}>
          {error}
        </div>
      )}

      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>Status</th>
            <th style={thStyle}>Dataset</th>
            <th style={thStyle}>Subject</th>
            <th style={thStyle}>Reviewer</th>
            <th style={thStyle}>Saved</th>
            <th style={thStyle}>Notes</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 && !loading && (
            <tr>
              <td style={{ ...tdStyle, color: 'var(--text-secondary)' }} colSpan={6}>
                No reviews{filter !== 'all' ? ` with status “${filter}”` : ''} yet.
              </td>
            </tr>
          )}
          {filtered.map((r) => (
            <tr
              key={`${r.dataset}|${r.subject}`}
              style={trClickable}
              onClick={() => setModalSubject(r.subject)}
            >
              <td style={tdStyle}><StatusPill status={r.status} /></td>
              <td style={tdStyle}>{r.dataset}</td>
              <td style={{ ...tdStyle, fontWeight: 600 }}>sub-{r.subject}</td>
              <td style={tdStyle}>{r.reviewer || <span style={{ color: 'var(--text-secondary)' }}>—</span>}</td>
              <td style={{ ...tdStyle, fontSize: 11, color: 'var(--text-secondary)' }}>
                {r.timestamp ? new Date(r.timestamp).toLocaleString() : '—'}
              </td>
              <td
                style={{
                  ...tdStyle,
                  fontSize: 11,
                  color: 'var(--text-secondary)',
                  maxWidth: 360,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={r.notes}
              >
                {r.notes || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {modalSubject && (
        <StructuralQCModal
          subject={modalSubject}
          onClose={() => {
            setModalSubject(null)
            reload()
          }}
        />
      )}
    </div>
  )
}
