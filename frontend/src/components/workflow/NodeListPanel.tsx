/** Collapsible, searchable list of nipype nodes for the DAG modal.
 *
 * Sits on the left edge of the DAG modal. Click a row → opens the
 * outputs drawer (same callback the graph uses on leaf clicks).
 */

import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type {
  NipypeNodeStatus,
  NipypeNodeStatusKind,
} from '../../api/types'

const STATUS_COLOR: Record<string, string> = {
  running: '#00e5ff',
  ok: '#00e676',
  failed: '#ff1744',
  completed_assumed: '#52c98f',
}


// ── styles ──────────────────────────────────────────────────────────────


const collapsedRail: CSSProperties = {
  width: 24,
  borderRight: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'center',
  paddingTop: 6,
}

const panel: CSSProperties = {
  width: 260,
  minWidth: 260,
  borderRight: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const panelHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 8px',
  borderBottom: '1px solid var(--border)',
  fontSize: 11,
  fontWeight: 700,
}

const searchInput: CSSProperties = {
  width: 'calc(100% - 16px)',
  padding: '4px 8px',
  fontSize: 11,
  border: '1px solid var(--border)',
  borderRadius: 3,
  background: 'var(--bg-card)',
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
  margin: '6px 8px',
  boxSizing: 'border-box',
}

const filterRow: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 3,
  padding: '0 8px 6px 8px',
}

const filterChip = (active: boolean, color: string): CSSProperties => ({
  fontSize: 9,
  padding: '1px 5px',
  borderRadius: 8,
  background: active ? `${color}33` : 'transparent',
  color: active ? color : 'var(--text-secondary)',
  border: `1px solid ${color}66`,
  cursor: 'pointer',
  textTransform: 'uppercase',
  letterSpacing: 0.4,
  fontWeight: 700,
})

const list: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
}

const row = (active: boolean): CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '4px 8px',
  borderBottom: '1px solid var(--border)',
  cursor: 'pointer',
  background: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
})

const dot = (color: string): CSSProperties => ({
  width: 7, height: 7, borderRadius: '50%', backgroundColor: color, flexShrink: 0,
})

const toggleBtn: CSSProperties = {
  padding: '2px 6px',
  fontSize: 11,
  border: '1px solid var(--border)',
  borderRadius: 3,
  background: 'var(--bg-card)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
}


// ── component ───────────────────────────────────────────────────────────


type FilterStatus = NipypeNodeStatusKind | 'all'

const FILTERS: { value: FilterStatus; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'running', label: 'Run' },
  { value: 'ok', label: 'Ok' },
  { value: 'failed', label: 'Fail' },
  { value: 'completed_assumed', label: '?' },
]


interface Props {
  nodes: NipypeNodeStatus[]
  selected: string | null
  onSelect: (node: string) => void
}


export function NodeListPanel({ nodes, selected, onSelect }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterStatus>('all')

  const counts = useMemo(() => {
    const c: Record<string, number> = {
      all: nodes.length,
      running: 0, ok: 0, failed: 0, completed_assumed: 0,
    }
    for (const n of nodes) c[n.status] = (c[n.status] ?? 0) + 1
    return c
  }, [nodes])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return nodes.filter((n) => {
      if (filter !== 'all' && n.status !== filter) return false
      if (!q) return true
      return n.node.toLowerCase().includes(q) || n.leaf.toLowerCase().includes(q)
    })
  }, [nodes, query, filter])

  if (collapsed) {
    return (
      <div style={collapsedRail}>
        <button
          style={toggleBtn}
          onClick={() => setCollapsed(false)}
          title="Show node list"
          aria-label="Show node list"
        >
          ☰
        </button>
      </div>
    )
  }

  return (
    <div style={panel}>
      <div style={panelHeader}>
        <span>Nodes ({nodes.length})</span>
        <span style={{ flex: 1 }} />
        <button
          style={toggleBtn}
          onClick={() => setCollapsed(true)}
          title="Collapse node list"
          aria-label="Collapse node list"
        >
          ←
        </button>
      </div>
      <input
        style={searchInput}
        placeholder="Search by leaf or path…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div style={filterRow}>
        {FILTERS.map((f) => {
          const color = f.value === 'all'
            ? 'var(--text-secondary)'
            : STATUS_COLOR[f.value as keyof typeof STATUS_COLOR]
          return (
            <button
              key={f.value}
              style={filterChip(filter === f.value, color)}
              onClick={() => setFilter(f.value)}
            >
              {f.label} {counts[f.value] ?? 0}
            </button>
          )
        })}
      </div>
      <div style={list}>
        {filtered.length === 0 && (
          <div style={{
            padding: 10, fontSize: 11, color: 'var(--text-secondary)',
          }}>
            No matches.
          </div>
        )}
        {filtered.map((n) => {
          const color = STATUS_COLOR[n.status] ?? 'var(--text-secondary)'
          const active = selected === n.node
          return (
            <div
              key={n.node}
              style={row(active)}
              onClick={() => onSelect(n.node)}
              title={n.node}
            >
              <span style={dot(color)} />
              <span style={{ fontSize: 11, fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {n.leaf}
              </span>
              {n.elapsed > 0 && (
                <span style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
                  {n.elapsed.toFixed(1)}s
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
