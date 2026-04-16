import { useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useModuleStore } from '../stores/module-store'
import { ModuleCard } from '../components/modules/ModuleCard'
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

export function ModuleBrowser() {
  const { modules, stages, loaded, loading, error } = useModuleStore()
  const [search, setSearch] = useState('')

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

  if (loading) {
    return <div style={loadingStyle}>Loading modules...</div>
  }

  if (error) {
    return <div style={errorStyle}>Error loading modules: {error}</div>
  }

  if (!loaded) {
    return <div style={loadingStyle}>Waiting for data...</div>
  }

  const sortedStages = [...stages].sort((a, b) => a.index - b.index)
  const totalModules = Object.values(modules).reduce((sum, list) => sum + list.length, 0)

  return (
    <div>
      <div style={headerStyle}>Module Browser</div>
      <div style={subtitleStyle}>
        {totalModules} modules across {stages.length} stages
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
      <div style={gridStyle}>
        {sortedStages.map((stage) => {
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
                  {stageModules.map((p) => <ModuleCard key={`${p.category}-${p.name}`} module={p} />)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
