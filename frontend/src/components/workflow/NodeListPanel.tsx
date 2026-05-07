/** Collapsible, searchable, hierarchical list of nipype nodes.
 *
 * The dotted nipype paths form a workflow tree
 * (`fmriprep_wf.sub_AN_wf.anat_fit_wf.surface_recon_wf.autorecon1`).
 * We render that tree as nested rows: workflow headers with rolled-up
 * counts, expandable to reveal their children. Click a leaf → opens
 * the outputs drawer (same callback the graph uses).
 */

import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type {
  NipypeNodeStatus,
  NipypeNodeStatusKind,
} from '../../api/types'
import { buildNipypeTree, type NipypeTreeNode } from './nipype_tree'

const STATUS_COLOR: Record<string, string> = {
  running: '#00e5ff',
  ok: '#00e676',
  failed: '#ff1744',
  completed_assumed: '#52c98f',
  cached: '#888',
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
  width: 280,
  minWidth: 280,
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

const listScroll: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
}

const leafRow = (active: boolean, depth: number): CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: `3px 8px 3px ${8 + depth * 12}px`,
  borderBottom: '1px solid var(--border)',
  cursor: 'pointer',
  background: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
})

const wfRow = (depth: number): CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  padding: `3px 8px 3px ${4 + depth * 12}px`,
  borderBottom: '1px solid var(--border)',
  cursor: 'pointer',
  background: 'rgba(255,255,255,0.02)',
  fontWeight: 700,
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
  { value: 'cached', label: 'Cached' },
]


interface Props {
  nodes: NipypeNodeStatus[]
  selected: string | null
  onSelect: (node: string) => void
}


function _wfColor(c: NonNullable<NipypeTreeNode['counts']>): string {
  if (c.failed > 0) return STATUS_COLOR.failed
  if (c.running > 0) return STATUS_COLOR.running
  if (c.ok > 0) return STATUS_COLOR.ok
  if (c.completed_assumed > 0) return STATUS_COLOR.completed_assumed
  if (c.cached > 0) return STATUS_COLOR.cached
  return 'var(--text-secondary)'
}


export function NodeListPanel({ nodes, selected, onSelect }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterStatus>('all')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const counts = useMemo(() => {
    const c: Record<string, number> = {
      all: nodes.length,
      running: 0, ok: 0, failed: 0, completed_assumed: 0, cached: 0,
    }
    for (const n of nodes) c[n.status] = (c[n.status] ?? 0) + 1
    return c
  }, [nodes])

  // Build the workflow tree from the same dotted paths the DAG uses.
  // Then filter leaves by status + search; keep ancestors of any
  // surviving leaf so the hierarchy is preserved.
  const { byParent, kept } = useMemo(() => {
    const tree = buildNipypeTree(nodes)
    const byId = new Map(tree.nodes.map((n) => [n.id, n]))
    const byParent = new Map<string | null, NipypeTreeNode[]>()
    for (const n of tree.nodes) {
      const list = byParent.get(n.parentId) ?? []
      list.push(n)
      byParent.set(n.parentId, list)
    }
    // Sort: workflows first, then leaves; alpha within each.
    for (const list of byParent.values()) {
      list.sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === 'workflow' ? -1 : 1
        return a.label.localeCompare(b.label)
      })
    }

    const q = query.trim().toLowerCase()
    const matches = (leaf: NipypeTreeNode): boolean => {
      if (leaf.kind !== 'leaf') return false
      if (filter !== 'all' && leaf.status !== filter) return false
      if (!q) return true
      return leaf.id.toLowerCase().includes(q)
        || leaf.label.toLowerCase().includes(q)
    }
    const kept = new Set<string>()
    for (const n of tree.nodes) {
      if (matches(n)) {
        let cur: NipypeTreeNode | undefined = n
        while (cur) {
          if (kept.has(cur.id)) break
          kept.add(cur.id)
          cur = cur.parentId ? byId.get(cur.parentId) : undefined
        }
      }
    }
    return { byParent, kept }
  }, [nodes, query, filter])

  // When searching/filtering, auto-expand surviving workflows so
  // matches are visible without clicking through.
  const isSearching = query.trim() !== '' || filter !== 'all'

  function isOpen(id: string): boolean {
    // User toggle (if any) always wins, so collapse/expand keeps
    // working during search. Default: open while searching (so hits
    // are visible), collapsed by default otherwise so the user sees
    // the top-level workflows first.
    if (id in expanded) return expanded[id]
    if (isSearching) return kept.has(id)
    return false
  }

  function toggle(id: string) {
    setExpanded((prev) => ({
      ...prev,
      [id]: !isOpen(id),
    }))
  }

  function renderChildren(parentId: string | null, depth: number): React.ReactNode {
    const children = byParent.get(parentId) ?? []
    return children.map((n) => {
      if (!kept.has(n.id) && isSearching) return null
      if (n.kind === 'workflow') {
        const open = isOpen(n.id)
        const c = n.counts ?? {
          running: 0, ok: 0, failed: 0, completed_assumed: 0, cached: 0, total: 0,
        }
        const color = _wfColor(c)
        return (
          <div key={n.id}>
            <div
              style={wfRow(depth)}
              onClick={() => toggle(n.id)}
              title={n.id}
            >
              <span style={{ width: 10, fontSize: 9, color: 'var(--text-secondary)' }}>
                {open ? '▼' : '▶'}
              </span>
              <span style={dot(color)} />
              <span style={{
                fontSize: 11, flex: 1, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {n.label}
              </span>
              <span style={{
                fontSize: 9, color: 'var(--text-secondary)', fontWeight: 400,
              }}>
                {c.running > 0 && <span style={{ color: STATUS_COLOR.running }}>{c.running}▶ </span>}
                {c.ok > 0 && <span style={{ color: STATUS_COLOR.ok }}>{c.ok}✓ </span>}
                {c.failed > 0 && <span style={{ color: STATUS_COLOR.failed }}>{c.failed}✗ </span>}
                {c.completed_assumed > 0 && (
                  <span style={{ color: STATUS_COLOR.completed_assumed }}>{c.completed_assumed}? </span>
                )}
                {c.cached > 0 && (
                  <span style={{ color: STATUS_COLOR.cached }}>{c.cached}◌ </span>
                )}
                {c.total === 0 && <span>—</span>}
              </span>
            </div>
            {open && renderChildren(n.id, depth + 1)}
          </div>
        )
      }
      // Leaf
      const color = STATUS_COLOR[n.status ?? ''] ?? 'var(--text-secondary)'
      const active = selected === n.id
      return (
        <div
          key={n.id}
          style={leafRow(active, depth)}
          onClick={() => onSelect(n.full_node ?? n.id)}
          title={n.id}
        >
          <span style={dot(color)} />
          <span style={{
            fontSize: 11, fontWeight: 600, flex: 1,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {n.label}
          </span>
          {n.elapsed !== undefined && n.elapsed > 0 && (
            <span style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
              {n.elapsed.toFixed(1)}s
            </span>
          )}
        </div>
      )
    })
  }

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

  const roots = byParent.get(null) ?? []
  const anyVisible = roots.some((n) => !isSearching || kept.has(n.id))

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
      <div style={listScroll}>
        {!anyVisible && (
          <div style={{
            padding: 10, fontSize: 11, color: 'var(--text-secondary)',
          }}>
            No matches.
          </div>
        )}
        {renderChildren(null, 0)}
      </div>
    </div>
  )
}
