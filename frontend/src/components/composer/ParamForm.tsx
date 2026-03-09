import type { ParamSchema, ParamField } from '../../api/types'

interface ParamFormProps {
  schema: ParamSchema
  values: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}

const formGroupStyle: React.CSSProperties = {
  marginBottom: 12,
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  marginBottom: 4,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  outline: 'none',
}

const pathInputStyle: React.CSSProperties = {
  ...inputStyle,
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  fontSize: 12,
}

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: 'pointer',
}

const checkboxWrapperStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const checkboxStyle: React.CSSProperties = {
  width: 16,
  height: 16,
  cursor: 'pointer',
  accentColor: 'var(--accent-cyan)',
}

const textareaStyle: React.CSSProperties = {
  ...inputStyle,
  minHeight: 80,
  resize: 'vertical',
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  fontSize: 12,
}

const descStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  marginTop: 2,
  fontStyle: 'italic',
}

const rangeHint: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  marginTop: 2,
}

function parseNumber(val: string, isFloat: boolean): number | undefined {
  if (val === '') return undefined
  const n = isFloat ? parseFloat(val) : parseInt(val, 10)
  return isNaN(n) ? undefined : n
}

function parseList(val: string, itemType: string): unknown[] {
  return val
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s !== '')
    .map((s) => (itemType.includes('int') || itemType.includes('float') ? Number(s) : s))
}

function formatListValue(val: unknown): string {
  if (Array.isArray(val)) return val.join(', ')
  return ''
}

function FieldInput({
  name,
  field,
  value,
  onChange,
}: {
  name: string
  field: ParamField
  value: unknown
  onChange: (value: unknown) => void
}) {
  const type = field.type.toLowerCase()

  // Boolean
  if (type === 'bool' || type === 'boolean') {
    return (
      <div style={checkboxWrapperStyle}>
        <input
          type="checkbox"
          id={`param-${name}`}
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          style={checkboxStyle}
        />
        <label htmlFor={`param-${name}`} style={{ fontSize: 13, color: 'var(--text-primary)', cursor: 'pointer' }}>
          {name}
        </label>
      </div>
    )
  }

  // Enum select
  if (field.enum && field.enum.length > 0) {
    return (
      <select
        value={String(value ?? '')}
        onChange={(e) => onChange(e.target.value)}
        style={selectStyle}
      >
        <option value="">-- select --</option>
        {field.enum.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    )
  }

  // Integer / Float
  if (type === 'int' || type === 'integer' || type === 'float' || type === 'number') {
    const isFloat = type === 'float' || type === 'number'
    return (
      <>
        <input
          type="number"
          value={value != null ? String(value) : ''}
          step={isFloat ? 'any' : '1'}
          min={field.min}
          max={field.max}
          onChange={(e) => onChange(parseNumber(e.target.value, isFloat))}
          style={inputStyle}
        />
        {(field.min != null || field.max != null) && (
          <div style={rangeHint}>
            Range: {field.min ?? '-inf'} to {field.max ?? 'inf'}
          </div>
        )}
      </>
    )
  }

  // List types
  if (type.startsWith('list')) {
    return (
      <input
        type="text"
        value={formatListValue(value)}
        placeholder="comma-separated values"
        onChange={(e) => onChange(parseList(e.target.value, type))}
        style={inputStyle}
      />
    )
  }

  // Dict / JSON
  if (type === 'dict' || type === 'object' || type === 'json') {
    const jsonStr = typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)
    return (
      <textarea
        value={jsonStr}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value))
          } catch {
            // keep raw string while user types
            onChange(e.target.value)
          }
        }}
        style={textareaStyle}
        placeholder="{}"
      />
    )
  }

  // Path
  if (type === 'path' || type === 'filepath') {
    return (
      <input
        type="text"
        value={String(value ?? '')}
        onChange={(e) => onChange(e.target.value)}
        style={pathInputStyle}
        placeholder="/path/to/..."
      />
    )
  }

  // Default: string
  return (
    <input
      type="text"
      value={String(value ?? '')}
      onChange={(e) => onChange(e.target.value)}
      style={inputStyle}
    />
  )
}

export function ParamForm({ schema, values, onChange }: ParamFormProps) {
  const entries = Object.entries(schema)
  if (entries.length === 0) {
    return (
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic', padding: '8px 0' }}>
        No configurable parameters
      </div>
    )
  }

  return (
    <div>
      {entries.map(([name, field]) => {
        const isBool = field.type.toLowerCase() === 'bool' || field.type.toLowerCase() === 'boolean'
        return (
          <div key={name} style={formGroupStyle}>
            {!isBool && (
              <label style={labelStyle}>
                {name}
                {field.required && <span style={{ color: 'var(--accent-red)', marginLeft: 4 }}>*</span>}
              </label>
            )}
            <FieldInput
              name={name}
              field={field}
              value={values[name] ?? field.default}
              onChange={(val) => onChange(name, val)}
            />
            {field.description && <div style={descStyle}>{field.description}</div>}
          </div>
        )
      })}
    </div>
  )
}
