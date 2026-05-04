import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { ModuleInfo, ParamField } from '../../api/types'
import { fetchModuleCode, type ModuleCode } from '../../api/client'

interface ModuleCardProps {
  module: ModuleInfo
  onEdit?: (category: string, name: string) => void
}

const cardStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  borderWidth: 1,
  borderStyle: 'solid',
  borderColor: 'var(--border)',
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

const sourceToggleStyle: CSSProperties = {
  fontSize: 11,
  color: 'var(--accent-cyan)',
  background: 'transparent',
  border: '1px solid var(--border)',
  borderRadius: 4,
  padding: '4px 10px',
  cursor: 'pointer',
  fontFamily: 'inherit',
}

const sourcePathStyle: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  marginTop: 10,
  fontFamily: 'monospace',
  wordBreak: 'break-all',
}

const sourcePreStyle: CSSProperties = {
  marginTop: 8,
  padding: 12,
  backgroundColor: 'var(--bg-deep, #0b0f14)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  fontSize: 11,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  lineHeight: 1.5,
  color: 'var(--text-primary)',
  maxHeight: 480,
  overflow: 'auto',
  whiteSpace: 'pre',
}

const lineNumStyle: CSSProperties = {
  display: 'inline-block',
  width: 40,
  paddingRight: 12,
  textAlign: 'right',
  color: 'var(--text-secondary)',
  userSelect: 'none',
  opacity: 0.5,
}

function SourceView({ code }: { code: ModuleCode }) {
  const containerRef = useRef<HTMLPreElement | null>(null)
  const lines = code.code.split('\n')
  const start = code.class_start
  const end = code.class_end

  useEffect(() => {
    const pre = containerRef.current
    if (!pre || start == null) return
    const target = pre.querySelector<HTMLElement>(`[data-line="${start}"]`)
    if (target) {
      pre.scrollTop = target.offsetTop - pre.offsetTop
    }
  }, [start])

  return (
    <>
      <div style={sourcePathStyle}>{code.path}</div>
      <pre ref={containerRef} style={sourcePreStyle} onClick={(e) => e.stopPropagation()}>
        {lines.map((line, i) => {
          const lineno = i + 1
          const inClass = start != null && end != null && lineno >= start && lineno <= end
          const rowStyle: CSSProperties = inClass
            ? { backgroundColor: 'rgba(0, 229, 255, 0.06)', display: 'block' }
            : { display: 'block' }
          return (
            <span key={lineno} data-line={lineno} style={rowStyle}>
              <span style={lineNumStyle}>{lineno}</span>
              {line || ' '}
              {'\n'}
            </span>
          )
        })}
      </pre>
    </>
  )
}

export function ModuleCard({ module, onEdit }: ModuleCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [showSource, setShowSource] = useState(false)
  const [code, setCode] = useState<ModuleCode | null>(null)
  const [codeLoading, setCodeLoading] = useState(false)
  const [codeError, setCodeError] = useState<string | null>(null)
  const paramCount = Object.keys(module.params).length

  async function toggleSource(e: React.MouseEvent) {
    e.stopPropagation()
    if (showSource) {
      setShowSource(false)
      return
    }
    setShowSource(true)
    if (code || codeLoading) return
    setCodeLoading(true)
    setCodeError(null)
    try {
      const c = await fetchModuleCode(module.category, module.name)
      setCode(c)
    } catch (err) {
      setCodeError(err instanceof Error ? err.message : String(err))
    } finally {
      setCodeLoading(false)
    }
  }

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
      {expanded && (
        <>
          <ParamTable params={module.params} />
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button type="button" style={sourceToggleStyle} onClick={toggleSource}>
              {showSource ? 'Hide source' : 'View source'}
            </button>
            {onEdit && (
              <button
                type="button"
                style={sourceToggleStyle}
                onClick={(e) => { e.stopPropagation(); onEdit(module.category, module.name) }}
              >
                Edit source
              </button>
            )}
          </div>
          {showSource && codeLoading && (
            <div style={{ ...docStyle, fontStyle: 'italic' }}>Loading source…</div>
          )}
          {showSource && codeError && (
            <div style={{ ...docStyle, color: 'var(--accent-red, #ff5252)' }}>
              {codeError}
            </div>
          )}
          {showSource && code && <SourceView code={code} />}
        </>
      )}
    </div>
  )
}
