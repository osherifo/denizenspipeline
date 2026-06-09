import { useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useModuleStore } from '../stores/module-store'
import { ModuleCard } from '../components/modules/ModuleCard'
import { ModuleSourceEditor } from './ModuleSourceEditor'
import type { ModuleInfo } from '../api/types'

const headerStyle: CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 8,
}

const subtitleStyle: CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
  marginBottom: 24,
}

const searchWrapperStyle: CSSProperties = {
  marginBottom: 24,
}

const searchInputStyle: CSSProperties = {
  width: '100%',
  maxWidth: 480,
  padding: '10px 16px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  outline: 'none',
}

const gridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
  gap: 24,
  alignItems: 'start',
}

const stageColumnStyle: CSSProperties = {
  minWidth: 0,
}

const stageTitleStyle = (color?: string): CSSProperties => ({
  fontSize: 14,
  fontWeight: 700,
  color: color || 'var(--accent-cyan)',
  marginBottom: 4,
  textTransform: 'uppercase',
  letterSpacing: 1.5,
})

const stageDescStyle: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  marginBottom: 12,
}

const countBadge: CSSProperties = {
  display: 'inline-block',
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 10,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
  marginLeft: 8,
}

const loadingStyle: CSSProperties = {
  color: 'var(--text-secondary)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

const errorStyle: CSSProperties = {
  color: 'var(--accent-red)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

type Scope = 'subject' | 'group' | 'study'

const SCOPE_ORDER: Scope[] = ['subject', 'group', 'study']
const SCOPE_LABELS: Record<Scope, string> = {
  subject: 'Subject',
  group: 'Group',
  study: 'Study',
}

const tabsRow: CSSProperties = {
  display: 'flex',
  gap: 4,
  borderBottom: '1px solid var(--border)',
  marginBottom: 18,
}

const tabBtn = (active: boolean): CSSProperties => ({
  padding: '8px 16px',
  fontSize: 13,
  fontWeight: 600,
  border: 'none',
  background: 'transparent',
  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
  borderBottom: active ? '2px solid var(--accent-cyan)' : '2px solid transparent',
  cursor: 'pointer',
  letterSpacing: 0.5,
  textTransform: 'uppercase',
  fontFamily: 'inherit',
  marginBottom: -1,
})

const scopeBadge: CSSProperties = {
  display: 'inline-block',
  fontSize: 10,
  fontWeight: 600,
  padding: '1px 6px',
  borderRadius: 10,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
  marginLeft: 6,
}

export function ModuleBrowser() {
  const { modules, stages, loaded, loading, error } = useModuleStore()
  const [search, setSearch] = useState('')
  const [scope, setScope] = useState<Scope>('subject')
  const [editing, setEditing] = useState<{ category: string; name: string } | null>(null)

  const filteredByStage = useMemo(() => {
    const query = search.toLowerCase().trim()
    const result: Record<string, ModuleInfo[]> = {}
    for (const [category, moduleList] of Object.entries(modules)) {
      const filtered = query
        ? moduleList.filter(
            (p) =>
              p.name.toLowerCase().includes(query) ||
              (p.docstring && p.docstring.toLowerCase().includes(query))
          )
        : moduleList
      if (filtered.length > 0) {
        const stage = filtered[0]?.stage || category
        if (!result[stage]) result[stage] = []
        result[stage].push(...filtered)
      }
    }
    return result
  }, [modules, search])

  // Per-scope module counts for the tab badges.
  const scopeCounts = useMemo(() => {
    const counts: Record<Scope, number> = { subject: 0, group: 0, study: 0 }
    for (const st of stages) {
      const s = (st.scope ?? 'subject') as Scope
      counts[s] = (counts[s] ?? 0) + (filteredByStage[st.name]?.length ?? 0)
    }
    return counts
  }, [stages, filteredByStage])

  if (editing) {
    return (
      <ModuleSourceEditor
        category={editing.category}
        name={editing.name}
        onBack={() => setEditing(null)}
      />
    )
  }

  if (loading) {
    return <div style={loadingStyle}>Loading modules...</div>
  }

  if (error) {
    return <div style={errorStyle}>Error loading modules: {error}</div>
  }

  if (!loaded) {
    return <div style={loadingStyle}>Waiting for data...</div>
  }

  // Stages within the active scope, ordered by their per-scope index.
  // Stages with no ``scope`` field (older backend) default to subject
  // so the browser still works against a stale server.
  const visibleStages = stages
    .filter((s) => (s.scope ?? 'subject') === scope)
    .sort((a, b) => a.index - b.index)
  const totalModules = Object.values(modules).reduce((sum, list) => sum + list.length, 0)

  return (
    <div>
      <div style={headerStyle}>Module Browser</div>
      <div style={subtitleStyle}>
        {totalModules} modules across {stages.length} stages
      </div>

      <div style={tabsRow}>
        {SCOPE_ORDER.map((s) => (
          <button
            key={s}
            style={tabBtn(scope === s)}
            onClick={() => setScope(s)}
          >
            {SCOPE_LABELS[s]}
            <span style={scopeBadge}>{scopeCounts[s] ?? 0}</span>
          </button>
        ))}
      </div>

      <div style={searchWrapperStyle}>
        <input
          type="text"
          placeholder="Search modules by name or description..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={searchInputStyle}
        />
      </div>
      {visibleStages.length === 0 ? (
        <div style={{ ...loadingStyle, padding: '32px 0' }}>
          No {SCOPE_LABELS[scope].toLowerCase()}-scope stages registered.
        </div>
      ) : (
        <div style={gridStyle}>
          {visibleStages.map((stage) => {
            const stageModules = filteredByStage[stage.name] || []
            if (search && stageModules.length === 0) return null
            return (
              <div key={stage.name} style={stageColumnStyle}>
                <div style={stageTitleStyle(stage.color)}>
                  {stage.index}. {stage.name}
                  <span style={countBadge}>{stageModules.length}</span>
                </div>
                <div style={stageDescStyle}>{stage.description}</div>
                {stageModules.length === 0 ? (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                    No modules
                  </div>
                ) : (
                  <div style={{
                    maxHeight: 330,
                    overflowY: stageModules.length > 3 ? 'auto' : 'visible',
                    paddingRight: stageModules.length > 3 ? 4 : 0,
                  }}>
                    {stageModules.map((p) => (
                      <ModuleCard
                        key={`${p.category}-${p.name}`}
                        module={p}
                        onEdit={(category, name) => setEditing({ category, name })}
                      />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
