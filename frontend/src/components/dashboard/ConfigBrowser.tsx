/** Config browser sidebar with grouping and filters. */
import { useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { ConfigSummary } from '../../api/types'

interface ConfigBrowserProps {
  configs: ConfigSummary[]
  selectedFilename: string | null
  loading: boolean
  onSelect: (filename: string) => void
  onRescan: () => void
}

const sidebarStyle: CSSProperties = {
  width: 260,
  minWidth: 260,
  backgroundColor: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const searchInput: CSSProperties = {
  margin: '12px',
  padding: '8px 12px',
  fontSize: 12,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
  outline: 'none',
}

const groupHeader: CSSProperties = {
  padding: '8px 16px',
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  letterSpacing: 2,
  textTransform: 'uppercase',
  cursor: 'pointer',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  borderTop: '1px solid var(--border)',
}

const configItem = (active: boolean): CSSProperties => ({
  padding: '8px 16px 8px 24px',
  fontSize: 12,
  cursor: 'pointer',
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
})

const configName: CSSProperties = {
  fontWeight: 600,
  color: 'var(--text-primary)',
  marginBottom: 2,
}

const configMeta: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  display: 'flex',
  gap: 8,
  alignItems: 'center',
}

const runBadge = (n: number): CSSProperties => ({
  fontSize: 10,
  padding: '1px 5px',
  borderRadius: 3,
  backgroundColor: n > 0 ? 'rgba(0, 230, 118, 0.12)' : 'rgba(136, 136, 170, 0.12)',
  color: n > 0 ? 'var(--accent-green)' : 'var(--text-secondary)',
})

const rescanBtn: CSSProperties = {
  margin: '8px 12px 12px',
  padding: '6px',
  fontSize: 11,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: 'inherit',
}

export function ConfigBrowser({ configs, selectedFilename, loading, onSelect, onRescan }: ConfigBrowserProps) {
  const [search, setSearch] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())

  const filtered = useMemo(() => {
    if (!search) return configs
    const q = search.toLowerCase()
    return configs.filter(
      (c) =>
        c.filename.toLowerCase().includes(q) ||
        c.experiment.toLowerCase().includes(q) ||
        c.subject.toLowerCase().includes(q) ||
        c.model_type.toLowerCase().includes(q)
    )
  }, [configs, search])

  // Group configs by group field
  const groups = useMemo(() => {
    const map: Record<string, ConfigSummary[]> = {}
    for (const c of filtered) {
      if (!map[c.group]) map[c.group] = []
      map[c.group].push(c)
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b))
  }, [filtered])

  const toggleGroup = (group: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  return (
    <div style={sidebarStyle}>
      <input
        type="text"
        placeholder="Search configs..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={searchInput}
      />

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {groups.map(([group, items]) => (
          <div key={group}>
            <div style={groupHeader} onClick={() => toggleGroup(group)}>
              <span>{group}</span>
              <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                {collapsedGroups.has(group) ? '\u25B6' : '\u25BC'} {items.length}
              </span>
            </div>
            {!collapsedGroups.has(group) &&
              items.map((c) => (
                <div
                  key={c.filename}
                  style={configItem(selectedFilename === c.filename)}
                  onClick={() => onSelect(c.filename)}
                >
                  <div style={configName}>{c.filename.replace('.yaml', '')}</div>
                  <div style={configMeta}>
                    <span>{c.subject || '?'}</span>
                    <span>{c.model_type || '?'}</span>
                    <span style={runBadge(c.n_runs)}>
                      {c.n_runs} run{c.n_runs !== 1 ? 's' : ''}
                    </span>
                  </div>
                </div>
              ))}
          </div>
        ))}

        {configs.length === 0 && !loading && (
          <div style={{ padding: '24px 16px', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
            No configs found
          </div>
        )}
      </div>

      <button style={rescanBtn} onClick={onRescan} disabled={loading}>
        {loading ? 'Scanning...' : 'Rescan'}
      </button>
    </div>
  )
}
