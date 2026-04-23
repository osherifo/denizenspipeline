import { useState, useEffect } from 'react'
import type { CSSProperties } from 'react'

interface NavBarProps {
  currentRoute: string
}

const sidebarStyle: CSSProperties = {
  width: 210,
  minWidth: 210,
  height: '100vh',
  backgroundColor: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  position: 'sticky',
  top: 0,
  zIndex: 100,
  overflowY: 'auto',
}

const logoStyle: CSSProperties = {
  fontSize: 16,
  fontWeight: 800,
  color: 'var(--accent-cyan)',
  letterSpacing: 3,
  textDecoration: 'none',
  padding: '20px 16px 20px',
  display: 'block',
  borderBottom: '1px solid var(--border)',
  marginBottom: 8,
}

// Category header — clickable, distinct background
function groupHeaderStyle(expanded: boolean, hasActive: boolean): CSSProperties {
  return {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 16px',
    margin: '4px 8px',
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    cursor: 'pointer',
    userSelect: 'none',
    borderRadius: 6,
    color: hasActive ? 'var(--accent-cyan)' : '#9898bb',
    backgroundColor: expanded ? '#1e1e3a' : 'transparent',
    transition: 'all 0.15s ease',
  }
}

const chevronStyle = (expanded: boolean): CSSProperties => ({
  fontSize: 10,
  transition: 'transform 0.15s ease',
  transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
  opacity: 0.5,
})

// Sub-items — indented, slightly lighter bg when section open
function linkStyle(active: boolean): CSSProperties {
  return {
    display: 'block',
    padding: '7px 16px 7px 28px',
    fontSize: 12,
    fontWeight: active ? 600 : 500,
    textDecoration: 'none',
    color: active ? 'var(--accent-cyan)' : '#7878a0',
    backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
    borderLeft: active ? '2px solid var(--accent-cyan)' : '2px solid transparent',
    cursor: 'pointer',
    letterSpacing: 0.3,
    transition: 'all 0.12s ease',
    marginLeft: 8,
  }
}

const groups = [
  {
    label: 'Pipeline',
    items: [
      { key: 'graph', label: 'Pipeline Graph', hash: '#graph' },
      { key: 'workflows', label: 'Workflows', hash: '#workflows' },
    ],
  },
  {
    label: 'Preprocessing',
    items: [
      { key: 'convert', label: 'DICOM \u2192 BIDS', hash: '#convert' },
      { key: 'preproc', label: 'Preproc', hash: '#preproc' },
      { key: 'autoflatten', label: 'Autoflatten', hash: '#autoflatten' },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { key: 'dashboard', label: 'Dashboard', hash: '#dashboard' },
      { key: 'modules', label: 'Modules', hash: '#modules' },
      { key: 'composer', label: 'Composer', hash: '#composer' },
      { key: 'runs', label: 'Runs', hash: '#runs' },
      { key: 'editor', label: 'Editor', hash: '#editor' },
    ],
  },
  {
    label: 'Reference',
    items: [
      { key: 'errors', label: 'Errors', hash: '#errors' },
    ],
  },
]

function groupForRoute(route: string): string | null {
  for (const g of groups) {
    if (g.items.some((i) => i.key === route)) return g.label
  }
  return null
}

export function NavBar({ currentRoute }: NavBarProps) {
  // Auto-expand the group containing the active route
  const activeGroup = groupForRoute(currentRoute)
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {}
    for (const g of groups) {
      init[g.label] = g.label === activeGroup
    }
    return init
  })

  // When route changes, make sure its group is expanded
  useEffect(() => {
    if (activeGroup && !expanded[activeGroup]) {
      setExpanded((prev) => ({ ...prev, [activeGroup]: true }))
    }
  }, [activeGroup])

  const toggle = (label: string) => {
    setExpanded((prev) => ({ ...prev, [label]: !prev[label] }))
  }

  return (
    <nav style={sidebarStyle}>
      <a href="#dashboard" style={logoStyle}>fMRIflow</a>
      {groups.map((g) => {
        const isExpanded = expanded[g.label] ?? false
        const hasActive = g.items.some((i) => i.key === currentRoute)
        return (
          <div key={g.label}>
            <div
              style={groupHeaderStyle(isExpanded, hasActive)}
              onClick={() => toggle(g.label)}
            >
              <span>{g.label}</span>
              <span style={chevronStyle(isExpanded)}>{'\u25B6'}</span>
            </div>
            {isExpanded && (
              <div style={{ paddingBottom: 4 }}>
                {g.items.map((r) => (
                  <a key={r.key} href={r.hash} style={linkStyle(currentRoute === r.key)}>
                    {r.label}
                  </a>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </nav>
  )
}
