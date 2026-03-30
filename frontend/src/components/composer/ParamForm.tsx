import type { ParamSchema, ParamField } from '../../api/types'

interface ParamFormProps {
  schema: ParamSchema
  values: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  /** Optional autocomplete suggestions keyed by field name. */
  suggestions?: Record<string, string[]>
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

/** Render a <datalist> if suggestions exist for this field. */
function Suggestions({ id, options }: { id: string; options?: string[] }) {
  if (!options || options.length === 0) return null
  return (
    <datalist id={id}>
      {options.map((opt) => (
        <option key={opt} value={opt} />
      ))}
    </datalist>
  )
}

function FieldInput({
  name,
  field,
  value,
  onChange,
  suggestions,
}: {
  name: string
  field: ParamField
  value: unknown
  onChange: (value: unknown) => void
  suggestions?: string[]
}) {
  const type = field.type.toLowerCase()
  const listId = suggestions && suggestions.length > 0 ? `dl-${name}` : undefined

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
    // Filter suggestions to only JSON strings (dict values from other configs)
    const dictSuggestions = (suggestions || []).filter((s) => s.startsWith('{'))
    return (
      <>
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
        {dictSuggestions.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
            {dictSuggestions.map((s, i) => {
              // Show a short preview of the dict
              let label: string
              try {
                const obj = JSON.parse(s)
                const keys = Object.keys(obj)
                label = keys.length <= 3
                  ? keys.map((k) => `${k}: ${obj[k]}`).join(', ')
                  : `${keys.slice(0, 2).map((k) => `${k}: ${obj[k]}`).join(', ')} … (${keys.length} keys)`
              } catch {
                label = s.slice(0, 40)
              }
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    try { onChange(JSON.parse(s)) } catch { onChange(s) }
                  }}
                  style={{
                    fontSize: 10,
                    padding: '3px 8px',
                    backgroundColor: 'rgba(0, 229, 255, 0.08)',
                    border: '1px solid rgba(0, 229, 255, 0.2)',
                    borderRadius: 4,
                    color: 'var(--accent-cyan)',
                    cursor: 'pointer',
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                  title={JSON.stringify(JSON.parse(s), null, 2)}
                >
                  {label}
                </button>
              )
            })}
          </div>
        )}
      </>
    )
  }

  // Path
  if (type === 'path' || type === 'filepath') {
    return (
      <>
        <input
          type="text"
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          style={pathInputStyle}
          placeholder="/path/to/..."
          list={listId}
        />
        <Suggestions id={listId!} options={suggestions} />
      </>
    )
  }

  // Default: string
  return (
    <>
      <input
        type="text"
        value={String(value ?? '')}
        onChange={(e) => onChange(e.target.value)}
        style={inputStyle}
        list={listId}
      />
      <Suggestions id={listId!} options={suggestions} />
    </>
  )
}

/** Merge schema defaults into suggestions so every field offers its default value. */
function mergedSuggestions(field: ParamField, external?: string[]): string[] | undefined {
  // Fields with enums use <select>, not datalist — skip
  if (field.enum && field.enum.length > 0) return undefined

  const result = new Set(external || [])

  // Add default value as a suggestion
  if (field.default != null) {
    const def = field.default
    if (typeof def === 'string') {
      result.add(def)
    } else if (Array.isArray(def)) {
      result.add(def.join(', '))
    } else if (typeof def === 'object') {
      result.add(JSON.stringify(def))
    } else {
      result.add(String(def))
    }
  }

  return result.size > 0 ? [...result] : undefined
}

export function ParamForm({ schema, values, onChange, suggestions }: ParamFormProps) {
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
              suggestions={mergedSuggestions(field, suggestions?.[name])}
            />
            {field.description && <div style={descStyle}>{field.description}</div>}
          </div>
        )
      })}
    </div>
  )
}
