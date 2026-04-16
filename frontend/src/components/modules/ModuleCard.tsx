import { useState } from 'react'
import type { CSSProperties } from 'react'
import type { ModuleInfo, ParamField } from '../../api/types'

interface ModuleCardProps {
  module: ModuleInfo
}

const cardStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '14px 16px',
  cursor: 'pointer',
  transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
  marginBottom: 8,
}

const cardHoverStyle: CSSProperties = {
  ...cardStyle,
  borderColor: 'var(--accent-cyan)',
  boxShadow: '0 0 12px rgba(0, 229, 255, 0.1)',
}

const nameStyle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 4,
}

const categoryBadgeStyle: CSSProperties = {
  display: 'inline-block',
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 4,
  backgroundColor: 'rgba(0, 229, 255, 0.1)',
  color: 'var(--accent-cyan)',
  marginRight: 8,
  letterSpacing: 0.5,
  textTransform: 'uppercase',
}

const dimsBadgeStyle: CSSProperties = {
  display: 'inline-block',
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 4,
  backgroundColor: 'rgba(0, 230, 118, 0.1)',
  color: 'var(--accent-green)',
  letterSpacing: 0.5,
}

const docStyle: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  marginTop: 6,
  lineHeight: 1.5,
}

const paramCountStyle: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  marginTop: 6,
}

const paramTableStyle: CSSProperties = {
  marginTop: 12,
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 11,
}

const thStyle: CSSProperties = {
  textAlign: 'left',
  padding: '6px 8px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  fontWeight: 600,
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const tdStyle: CSSProperties = {
  padding: '5px 8px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
  fontSize: 11,
}

function formatDefault(val: unknown): string {
  if (val === undefined || val === null) return '-'
  if (typeof val === 'boolean') return val ? 'true' : 'false'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function ParamTable({ params }: { params: Record<string, ParamField> }) {
  const entries = Object.entries(params)
  if (entries.length === 0) {
    return <div style={{ ...docStyle, fontStyle: 'italic' }}>No parameters</div>
  }
  return (
    <table style={paramTableStyle}>
      <thead>
        <tr>
          <th style={thStyle}>Param</th>
          <th style={thStyle}>Type</th>
          <th style={thStyle}>Default</th>
          <th style={thStyle}>Required</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([name, field]) => (
          <tr key={name}>
            <td style={{ ...tdStyle, color: 'var(--accent-cyan)', fontWeight: 600 }}>{name}</td>
            <td style={tdStyle}>
              {field.type}
              {field.enum ? ` [${field.enum.join(', ')}]` : ''}
            </td>
            <td style={tdStyle}>{formatDefault(field.default)}</td>
            <td style={tdStyle}>{field.required ? 'yes' : 'no'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ModuleCard({ module }: ModuleCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [hovered, setHovered] = useState(false)
  const paramCount = Object.keys(module.params).length

  return (
    <div
      style={hovered ? cardHoverStyle : cardStyle}
      onClick={() => setExpanded(!expanded)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={nameStyle}>{module.name}</div>
      <div>
        <span style={categoryBadgeStyle}>{module.category}</span>
        {module.n_dims != null && (
          <span style={dimsBadgeStyle}>{module.n_dims} dims</span>
        )}
      </div>
      <div style={docStyle}>{module.docstring}</div>
      <div style={paramCountStyle}>
        {paramCount} param{paramCount !== 1 ? 's' : ''}
        {!expanded && paramCount > 0 && (
          <span style={{ color: 'var(--accent-cyan)', marginLeft: 8, fontSize: 10 }}>
            click to expand
          </span>
        )}
      </div>
      {expanded && <ParamTable params={module.params} />}
    </div>
  )
}
