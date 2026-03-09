import { useState, useMemo } from 'react'
import { usePluginStore } from '../stores/plugin-store'
import { PluginCard } from '../components/plugins/PluginCard'
import type { PluginInfo } from '../api/types'

const headerStyle: React.CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 8,
}

const subtitleStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
  marginBottom: 24,
}

const searchWrapperStyle: React.CSSProperties = {
  marginBottom: 24,
}

const searchInputStyle: React.CSSProperties = {
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

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
  gap: 24,
  alignItems: 'start',
}

const stageColumnStyle: React.CSSProperties = {
  minWidth: 0,
}

const stageTitleStyle = (color?: string): React.CSSProperties => ({
  fontSize: 14,
  fontWeight: 700,
  color: color || 'var(--accent-cyan)',
  marginBottom: 4,
  textTransform: 'uppercase',
  letterSpacing: 1.5,
})

const stageDescStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  marginBottom: 12,
}

const countBadge: React.CSSProperties = {
  display: 'inline-block',
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 10,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
  marginLeft: 8,
}

const loadingStyle: React.CSSProperties = {
  color: 'var(--text-secondary)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

const errorStyle: React.CSSProperties = {
  color: 'var(--accent-red)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

export function PluginBrowser() {
  const { plugins, stages, loaded, loading, error } = usePluginStore()
  const [search, setSearch] = useState('')

  const filteredByStage = useMemo(() => {
    const query = search.toLowerCase().trim()
    const result: Record<string, PluginInfo[]> = {}
    for (const [category, pluginList] of Object.entries(plugins)) {
      const filtered = query
        ? pluginList.filter(
            (p) =>
              p.name.toLowerCase().includes(query) ||
              (p.docstring && p.docstring.toLowerCase().includes(query))
          )
        : pluginList
      if (filtered.length > 0) {
        const stage = filtered[0]?.stage || category
        if (!result[stage]) result[stage] = []
        result[stage].push(...filtered)
      }
    }
    return result
  }, [plugins, search])

  if (loading) {
    return <div style={loadingStyle}>Loading plugins...</div>
  }

  if (error) {
    return <div style={errorStyle}>Error loading plugins: {error}</div>
  }

  if (!loaded) {
    return <div style={loadingStyle}>Waiting for data...</div>
  }

  const sortedStages = [...stages].sort((a, b) => a.index - b.index)
  const totalPlugins = Object.values(plugins).reduce((sum, list) => sum + list.length, 0)

  return (
    <div>
      <div style={headerStyle}>Plugin Browser</div>
      <div style={subtitleStyle}>
        {totalPlugins} plugins across {stages.length} stages
      </div>
      <div style={searchWrapperStyle}>
        <input
          type="text"
          placeholder="Search plugins by name or description..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={searchInputStyle}
        />
      </div>
      <div style={gridStyle}>
        {sortedStages.map((stage) => {
          const stagePlugins = filteredByStage[stage.name] || []
          if (search && stagePlugins.length === 0) return null
          return (
            <div key={stage.name} style={stageColumnStyle}>
              <div style={stageTitleStyle(stage.color)}>
                {stage.index}. {stage.name}
                <span style={countBadge}>{stagePlugins.length}</span>
              </div>
              <div style={stageDescStyle}>{stage.description}</div>
              {stagePlugins.length === 0 ? (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                  No plugins
                </div>
              ) : (
                stagePlugins.map((p) => <PluginCard key={`${p.category}-${p.name}`} plugin={p} />)
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
