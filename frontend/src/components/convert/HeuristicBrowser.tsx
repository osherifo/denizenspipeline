/** Tab 2: Heuristic browser — list available heuristic files with details. */
import { useEffect, useState } from 'react'
import { useConvertStore } from '../../stores/convert-store'
import type { HeuristicInfo } from '../../api/types'

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

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 12,
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 10px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  fontWeight: 700,
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const tdStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

const tagStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 6px',
  borderRadius: 3,
  fontSize: 10,
  fontWeight: 600,
  backgroundColor: 'rgba(0, 229, 255, 0.1)',
  color: 'var(--accent-cyan)',
  marginRight: 4,
  marginBottom: 2,
}

const detailPanel: React.CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '16px 20px',
  marginTop: 16,
}

const fieldLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 2,
}

const fieldValue: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
  marginBottom: 12,
}

export function HeuristicBrowser() {
  const { heuristics, heuristicsLoading, loadHeuristics } = useConvertStore()
  const [selected, setSelected] = useState<HeuristicInfo | null>(null)

  useEffect(() => { loadHeuristics() }, [])

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <div style={titleStyle}>Heuristic Files</div>
        <button style={btnStyle} onClick={loadHeuristics} disabled={heuristicsLoading}>
          {heuristicsLoading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {heuristics.length === 0 && !heuristicsLoading && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '12px 0' }}>
          No heuristic files found.
        </div>
      )}

      {heuristics.length > 0 && (
        <div style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 6, overflow: 'hidden' }}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Scanner Pattern</th>
                <th style={thStyle}>Version</th>
                <th style={thStyle}>Tasks</th>
                <th style={thStyle}>Description</th>
              </tr>
            </thead>
            <tbody>
              {heuristics.map((h) => (
                <tr
                  key={h.name}
                  style={{
                    cursor: 'pointer',
                    backgroundColor: selected?.name === h.name ? 'rgba(0, 229, 255, 0.06)' : 'transparent',
                  }}
                  onClick={() => setSelected(selected?.name === h.name ? null : h)}
                >
                  <td style={{ ...tdStyle, fontWeight: 700, color: 'var(--accent-cyan)' }}>{h.name}</td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>
                    {h.scanner_pattern || '\u2014'}
                  </td>
                  <td style={tdStyle}>{h.version || '\u2014'}</td>
                  <td style={tdStyle}>
                    {h.tasks && h.tasks.length > 0
                      ? h.tasks.map((t) => <span key={t} style={tagStyle}>{t}</span>)
                      : <span style={{ color: 'var(--text-secondary)' }}>{'\u2014'}</span>
                    }
                  </td>
                  <td style={{ ...tdStyle, color: 'var(--text-secondary)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {h.description || '\u2014'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div style={detailPanel}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>
            {selected.name}
          </div>
          <div style={fieldLabel}>Description</div>
          <div style={fieldValue}>{selected.description || 'No description available'}</div>
          <div style={fieldLabel}>Scanner Pattern</div>
          <div style={{ ...fieldValue, fontFamily: 'monospace', fontSize: 12 }}>
            {selected.scanner_pattern || 'None'}
          </div>
          <div style={fieldLabel}>Version</div>
          <div style={fieldValue}>{selected.version || 'Not specified'}</div>
          <div style={fieldLabel}>Tasks</div>
          <div style={fieldValue}>
            {selected.tasks && selected.tasks.length > 0
              ? selected.tasks.map((t) => <span key={t} style={tagStyle}>{t}</span>)
              : 'None defined'
            }
          </div>
          <div style={fieldLabel}>Path</div>
          <div style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
            {selected.path}
          </div>
        </div>
      )}
    </div>
  )
}
