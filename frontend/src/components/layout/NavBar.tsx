const navStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '0 32px',
  height: 56,
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  position: 'sticky',
  top: 0,
  zIndex: 100,
}

const titleStyle: React.CSSProperties = {
  fontSize: 18,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
  letterSpacing: 3,
  textDecoration: 'none',
}

const linksStyle: React.CSSProperties = {
  display: 'flex',
  gap: 8,
}

interface NavBarProps {
  currentRoute: string
}

function linkStyle(active: boolean): React.CSSProperties {
  return {
    padding: '8px 16px',
    fontSize: 13,
    fontWeight: 600,
    textDecoration: 'none',
    color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
    backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
    borderRadius: 6,
    border: active ? '1px solid rgba(0, 229, 255, 0.25)' : '1px solid transparent',
    transition: 'all 0.15s ease',
    cursor: 'pointer',
    letterSpacing: 1,
  }
}

const routes = [
  { key: 'plugins', label: 'Plugins', hash: '#plugins' },
  { key: 'composer', label: 'Composer', hash: '#composer' },
  { key: 'runs', label: 'Runs', hash: '#runs' },
  { key: 'editor', label: 'Editor', hash: '#editor' },
]

export function NavBar({ currentRoute }: NavBarProps) {
  return (
    <nav style={navStyle}>
      <a href="#plugins" style={titleStyle}>DENIZENS</a>
      <div style={linksStyle}>
        {routes.map((r) => (
          <a key={r.key} href={r.hash} style={linkStyle(currentRoute === r.key)}>
            {r.label}
          </a>
        ))}
      </div>
    </nav>
  )
}
