/** Tab 1: Tool availability list — heudiconv, dcm2niix, bids-validator, etc. */
import { useEffect } from 'react'
import { useConvertStore } from '../../stores/convert-store'

const containerStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '20px 24px',
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 16,
}

const titleStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '10px 0',
  borderBottom: '1px solid var(--border)',
}

const nameStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: 'var(--text-primary)',
  width: 140,
}

const versionStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--accent-cyan)',
  width: 100,
}

const detailStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  flex: 1,
}

const btnStyle: React.CSSProperties = {
  padding: '6px 16px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 5,
  cursor: 'pointer',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}

export function ToolStatusPanel() {
  const { tools, toolsLoading, loadTools } = useConvertStore()

  useEffect(() => { loadTools() }, [])

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <div style={titleStyle}>Tool Availability</div>
        <button style={btnStyle} onClick={loadTools} disabled={toolsLoading}>
          {toolsLoading ? 'Checking...' : 'Refresh'}
        </button>
      </div>

      {tools.length === 0 && !toolsLoading && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '12px 0' }}>
          No tools registered.
        </div>
      )}

      {tools.map((t) => (
        <div key={t.name} style={rowStyle}>
          <span style={{ fontSize: 14, width: 20, textAlign: 'center' }}>
            {t.available
              ? <span style={{ color: 'var(--accent-green)' }}>{'\u2713'}</span>
              : <span style={{ color: 'var(--accent-red)' }}>{'\u2717'}</span>
            }
          </span>
          <span style={nameStyle}>{t.name}</span>
          <span style={versionStyle}>{t.version || '\u2014'}</span>
          <span style={detailStyle}>{t.detail}</span>
        </div>
      ))}
    </div>
  )
}
