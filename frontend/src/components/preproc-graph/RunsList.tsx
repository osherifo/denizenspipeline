/** All pipeline runs, newest first. */
import type { CSSProperties } from 'react'
import { usePreprocRunsStore } from '../../stores/preproc-runs-store'
import { VERDICT_COLORS } from './CheckpointFilmstrip'

const STATUS_COLOR: Record<string, string> = { running: '#3b82f6', done: '#10b981', failed: '#ef4444', cancelled: '#9ca3af', lost: '#f59e0b' }
const row = (selected: boolean): CSSProperties => ({
  display: 'grid', gridTemplateColumns: '10px 1fr auto', gap: 8, alignItems: 'center', padding: '8px 10px',
  borderBottom: '1px solid var(--border)', cursor: 'pointer', fontSize: 12,
  background: selected ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
})

interface Props {
  onSelect?: (runId: string) => void
}

export function RunsList({ onSelect }: Props) {
  const runs = usePreprocRunsStore((s) => s.runs)
  const selectedRunId = usePreprocRunsStore((s) => s.selectedRunId)
  const select = usePreprocRunsStore((s) => s.select)
  const remove = usePreprocRunsStore((s) => s.remove)
  if (runs.length === 0) return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 10 }}>No pipeline runs yet.</div>
  return (
    <div>
      {runs.map((r) => (
        <div key={r.run_id} style={row(r.run_id === selectedRunId)} onClick={() => { void select(r.run_id); onSelect?.(r.run_id) }}>
          <span style={{ width: 8, height: 8, borderRadius: 999, background: STATUS_COLOR[r.status] ?? '#9ca3af', display: 'inline-block' }} title={r.status} />
          <div>
            <div style={{ fontWeight: 600 }}>{r.pipeline ?? r.run_id} <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>· sub-{r.subject}</span></div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 10 }}>
              {new Date(r.started_at * 1000).toLocaleString()} · {r.n_nodes} nodes · {r.status}
              {r.checkpoints?.n > 0 && r.checkpoints.worst && <span style={{ color: VERDICT_COLORS[r.checkpoints.worst] }}> · ● {r.checkpoints.worst}</span>}
              {r.resumed_from && <span> · resumed</span>}
            </div>
          </div>
          {r.status !== 'running' && (
            <button
              title="delete run record"
              onClick={(e) => { e.stopPropagation(); if (confirm(`Delete run ${r.run_id}? Outputs on disk are kept.`)) void remove(r.run_id) }}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12 }}
            >✕</button>
          )}
        </div>
      ))}
    </div>
  )
}
