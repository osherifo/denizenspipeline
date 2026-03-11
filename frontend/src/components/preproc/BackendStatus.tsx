/** Tab 1: Backend availability list. */
import { useEffect } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'

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
  width: 120,
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

export function BackendStatus() {
  const { backends, backendsLoading, loadBackends } = usePreprocStore()

  useEffect(() => { loadBackends() }, [])

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <div style={titleStyle}>Backend Availability</div>
        <button style={btnStyle} onClick={loadBackends} disabled={backendsLoading}>
          {backendsLoading ? 'Checking...' : 'Refresh'}
        </button>
      </div>

      {backends.length === 0 && !backendsLoading && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '12px 0' }}>
          No backends registered.
        </div>
      )}

      {backends.map((b) => (
        <div key={b.name} style={rowStyle}>
          <span style={{ fontSize: 14, width: 20, textAlign: 'center' }}>
            {b.available
              ? <span style={{ color: 'var(--accent-green)' }}>{'\u2713'}</span>
              : <span style={{ color: 'var(--accent-red)' }}>{'\u2717'}</span>
            }
          </span>
          <span style={nameStyle}>{b.name}</span>
          <span style={detailStyle}>{b.detail}</span>
        </div>
      ))}
    </div>
  )
}
