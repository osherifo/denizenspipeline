/** Error Knowledge Base browser — searchable list of known pipeline errors. */
import { useEffect, useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { fetchErrors } from '../api/client'
import type { ErrorEntry } from '../api/types'

// ── Styles ──

const headerStyle: CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 4,
}

const subtitleStyle: CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
  marginBottom: 20,
}

const searchRow: CSSProperties = {
  display: 'flex',
  gap: 12,
  marginBottom: 20,
  flexWrap: 'wrap',
  alignItems: 'center',
}

const searchInputStyle: CSSProperties = {
  flex: 1,
  minWidth: 200,
  maxWidth: 420,
  padding: '10px 16px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  outline: 'none',
}

const filterBtn = (active: boolean): CSSProperties => ({
  padding: '6px 14px',
  fontSize: 11,
  fontWeight: 600,
  border: active ? '1px solid rgba(0, 229, 255, 0.4)' : '1px solid var(--border)',
  borderRadius: 14,
  backgroundColor: active ? 'rgba(0, 229, 255, 0.1)' : 'transparent',
  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
  cursor: 'pointer',
  letterSpacing: 0.5,
  textTransform: 'uppercase' as const,
})

const cardStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '16px 20px',
  marginBottom: 10,
  cursor: 'pointer',
  transition: 'border-color 0.15s ease',
}

const cardHoverStyle: CSSProperties = {
  ...cardStyle,
  borderColor: 'var(--accent-cyan)',
}

const titleRow: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 10,
  marginBottom: 6,
}

const idBadge: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  padding: '2px 8px',
  borderRadius: 4,
  backgroundColor: 'rgba(0, 229, 255, 0.1)',
  color: 'var(--accent-cyan)',
  whiteSpace: 'nowrap',
  flexShrink: 0,
}

const stageBadge = (stage: string): CSSProperties => {
  const colors: Record<string, string> = {
    stimuli: '#00e5ff',
    responses: '#e040fb',
    features: '#ffd600',
    prepare: '#00e676',
    preprocess: '#00e676',       // legacy alias
    preparation: '#00e676',       // legacy alias
    preprocessing: '#00e676',     // legacy alias
    model: '#448aff',
    analyze: '#ff1744',
    report: '#ffffff',
    preproc: '#00e676',
  }
  const c = colors[stage] || '#8888aa'
  return {
    fontSize: 10,
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: 4,
    backgroundColor: `${c}18`,
    color: c,
    letterSpacing: 0.5,
    textTransform: 'uppercase' as const,
    whiteSpace: 'nowrap',
    flexShrink: 0,
  }
}

const tagStyle: CSSProperties = {
  display: 'inline-block',
  fontSize: 10,
  padding: '2px 6px',
  borderRadius: 3,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
  marginRight: 4,
  marginTop: 4,
}

const sectionLabel: CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  letterSpacing: 1.5,
  textTransform: 'uppercase' as const,
  marginBottom: 6,
  marginTop: 14,
}

const sectionText: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-primary)',
  lineHeight: 1.7,
  whiteSpace: 'pre-wrap',
}

const metaRow: CSSProperties = {
  display: 'flex',
  gap: 16,
  fontSize: 11,
  color: 'var(--text-secondary)',
  marginTop: 10,
}

const loadingStyle: CSSProperties = {
  color: 'var(--text-secondary)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

// ── Component ──

export function ErrorBrowser() {
  const [errors, setErrors] = useState<ErrorEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [stageFilter, setStageFilter] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | number | null>(null)
  const [hoveredId, setHoveredId] = useState<string | number | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchErrors()
      .then((entries) => { setErrors(entries); setLoading(false) })
      .catch((e) => { setLoadError(String(e)); setLoading(false) })
  }, [])

  // Unique stages for filter buttons
  const stages = useMemo(() => {
    const s = new Set(errors.map((e) => e.stage).filter(Boolean))
    return [...s].sort()
  }, [errors])

  // Filtered list
  const filtered = useMemo(() => {
    let list = errors
    if (stageFilter) {
      list = list.filter((e) => e.stage === stageFilter)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(
        (e) =>
          e.title.toLowerCase().includes(q) ||
          e.symptoms.toLowerCase().includes(q) ||
          e.root_cause.toLowerCase().includes(q) ||
          e.fix.toLowerCase().includes(q) ||
          e.tags.some((t) => t.toLowerCase().includes(q)),
      )
    }
    return list
  }, [errors, stageFilter, search])

  if (loading) return <div style={loadingStyle}>Loading error knowledge base...</div>
  if (loadError) return <div style={{ ...loadingStyle, color: 'var(--accent-red)' }}>Failed to load: {loadError}</div>

  return (
    <div>
      <div style={headerStyle}>Error Knowledge Base</div>
      <div style={subtitleStyle}>
        {errors.length} documented errors &mdash; search by symptom, stage, or keyword
      </div>

      {/* Search + stage filters */}
      <div style={searchRow}>
        <input
          type="text"
          placeholder="Search errors..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={searchInputStyle}
        />
        {stages.map((s) => (
          <button
            key={s}
            style={filterBtn(stageFilter === s)}
            onClick={() => setStageFilter(stageFilter === s ? null : s)}
          >
            {s}
          </button>
        ))}
        {stageFilter && (
          <button
            style={{ ...filterBtn(false), color: 'var(--accent-red)', borderColor: 'rgba(255,23,68,0.3)' }}
            onClick={() => setStageFilter(null)}
          >
            Clear
          </button>
        )}
      </div>

      {/* Results count */}
      {search || stageFilter ? (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>
          Showing {filtered.length} of {errors.length}
        </div>
      ) : null}

      {/* Error cards */}
      {filtered.length === 0 ? (
        <div style={loadingStyle}>No matching errors</div>
      ) : (
        filtered.map((entry) => {
          const isExpanded = expandedId === entry.id
          const isHovered = hoveredId === entry.id
          return (
            <div
              key={entry.id}
              style={isHovered ? cardHoverStyle : cardStyle}
              onClick={() => setExpandedId(isExpanded ? null : entry.id)}
              onMouseEnter={() => setHoveredId(entry.id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              {/* Title row */}
              <div style={titleRow}>
                <span style={idBadge}>#{entry.id}</span>
                <span style={stageBadge(entry.stage)}>{entry.stage}</span>
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                  {entry.title}
                </span>
              </div>

              {/* Tags */}
              {entry.tags.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  {entry.tags.map((t) => (
                    <span
                      key={t}
                      style={tagStyle}
                      onClick={(e) => { e.stopPropagation(); setSearch(t); setStageFilter(null) }}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {/* Collapsed preview */}
              {!isExpanded && (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.5 }}>
                  {entry.symptoms.split('\n')[0].slice(0, 120)}
                  {entry.symptoms.length > 120 ? '...' : ''}
                </div>
              )}

              {/* Expanded detail */}
              {isExpanded && (
                <div>
                  <div style={sectionLabel}>Symptoms</div>
                  <div style={sectionText}>{entry.symptoms}</div>

                  <div style={sectionLabel}>Root Cause</div>
                  <div style={sectionText}>{entry.root_cause}</div>

                  {entry.diagnosis && (
                    <>
                      <div style={sectionLabel}>Diagnosis</div>
                      <div style={sectionText}>{entry.diagnosis}</div>
                    </>
                  )}

                  <div style={sectionLabel}>Fix</div>
                  <div style={sectionText}>{entry.fix}</div>

                  {entry.config_note && (
                    <>
                      <div style={sectionLabel}>Config Note</div>
                      <div style={sectionText}>{entry.config_note}</div>
                    </>
                  )}

                  {entry.references.length > 0 && (
                    <>
                      <div style={sectionLabel}>References</div>
                      <div style={sectionText}>
                        {entry.references.map((r, i) => <div key={i}>{r}</div>)}
                      </div>
                    </>
                  )}

                  <div style={metaRow}>
                    <span>{entry.author}</span>
                    <span>{entry.date}</span>
                  </div>
                </div>
              )}
            </div>
          )
        })
      )}
    </div>
  )
}
