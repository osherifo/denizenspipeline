/** ModuleSlot — module picker + ParamForm for one slot.
 *
 * Used in every stage that selects exactly one module
 * (stimulus, response loader/reader, model, etc.) and as the
 * inner cell of ModuleStack for stages that take a list.
 *
 * Replaces every per-section + per-node form component the
 * previous Composer + PipelineGraph had. ParamForm is the only
 * form rendering primitive in the new design.
 */

import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import { ParamForm } from './ParamForm'
import type { ModuleInfo } from '../../api/types'

interface ModuleSlotProps {
  /** Display label for the slot (e.g. "Loader", "Reader"). Optional. */
  label?: string
  /** Modules the user can pick from. */
  available: ModuleInfo[]
  /** Currently selected module name (or empty string for "no selection"). */
  selectedName: string
  /** All param values for this slot's module (passed through to ParamForm). */
  values: Record<string, unknown>
  /** Called when the user picks a different module. */
  onSelect: (name: string) => void
  /** Called for every param change. */
  onParamChange: (key: string, value: unknown) => void
  /** Optional field-name → suggestion list map for autocomplete. */
  suggestions?: Record<string, string[]>
  /** Rendered as the placeholder option (defaults to "-- select --"). */
  placeholder?: string
  /** When true, hide the docstring panel even if available. */
  hideDocstring?: boolean
  /** Schema fields to hide from the ParamForm (rendered separately by the
   * caller, e.g. a list-of-dicts field handled as a ModuleStack). */
  hiddenFields?: string[]
}

const wrapperStyle: CSSProperties = {
  marginBottom: 4,
}

const labelStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 6,
  display: 'block',
}

const selectStyle: CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  fontSize: 13,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  outline: 'none',
  marginBottom: 12,
}

// Warning treatment for a module the config names but this system doesn't have.
const missingSelectStyle: CSSProperties = {
  border: '1px solid var(--accent-yellow, #ffb86c)',
  color: 'var(--accent-yellow, #ffb86c)',
  marginBottom: 6,
}

const missingNoticeStyle: CSSProperties = {
  margin: '0 0 12px 0',
  padding: '10px 12px',
  fontSize: 12,
  lineHeight: 1.5,
  color: 'var(--accent-yellow, #ffb86c)',
  backgroundColor: 'rgba(255, 184, 108, 0.10)',
  border: '1px solid var(--accent-yellow, #ffb86c)',
  borderRadius: 6,
}

const rawParamsStyle: CSSProperties = {
  marginTop: 8,
  paddingTop: 8,
  borderTop: '1px solid rgba(255, 184, 108, 0.35)',
  color: 'var(--text-secondary)',
  fontSize: 11,
}

function formatValue(v: unknown): string {
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

const docstringStyle: CSSProperties = {
  margin: '0 0 12px 0',
  padding: '10px 12px',
  fontSize: 12,
  color: 'var(--text-secondary)',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  lineHeight: 1.5,
  fontStyle: 'italic',
}

export function ModuleSlot({
  label,
  available,
  selectedName,
  values,
  onSelect,
  onParamChange,
  suggestions,
  placeholder = '-- select --',
  hideDocstring = false,
  hiddenFields,
}: ModuleSlotProps) {
  const selected = useMemo(
    () => available.find((m) => m.name === selectedName),
    [available, selectedName],
  )

  // The config names a module that isn't registered on this machine (e.g. a
  // config written elsewhere, or one pulled from the Hub whose module hasn't
  // been installed). Without this the <select> silently shows the placeholder
  // and no params render — it looks like "nothing happens".
  const missing = !!selectedName && !selected
  const configuredParams = useMemo(
    () => Object.entries(values ?? {}).filter(([, v]) => v !== undefined),
    [values],
  )

  const visibleSchema = useMemo(() => {
    if (!selected) return undefined
    if (!hiddenFields || hiddenFields.length === 0) return selected.params
    const filtered: typeof selected.params = {}
    for (const [k, v] of Object.entries(selected.params)) {
      if (!hiddenFields.includes(k)) filtered[k] = v
    }
    return filtered
  }, [selected, hiddenFields])

  return (
    <div style={wrapperStyle}>
      {label && <span style={labelStyle}>{label}</span>}
      <select
        style={missing ? { ...selectStyle, ...missingSelectStyle } : selectStyle}
        value={selectedName}
        onChange={(e) => onSelect(e.target.value)}
      >
        <option value="">{placeholder}</option>
        {/* Keep the configured name visible even when it isn't installed,
            otherwise the slot renders blank and the config looks empty. */}
        {missing && (
          <option value={selectedName}>{selectedName} — not installed</option>
        )}
        {available.map((m) => (
          <option key={m.name} value={m.name}>{m.name}</option>
        ))}
      </select>
      {missing && (
        <div style={missingNoticeStyle}>
          <strong>⚠ “{selectedName}” isn’t installed on this system.</strong>
          {' '}Without it there’s no parameter schema, so these settings can’t be
          edited here (any configured values are shown read-only below). Install it from the{' '}
          <a href="#hub" style={{ color: 'inherit', textDecoration: 'underline' }}>Hub</a>,
          add it in the module editor, or pick an available module above.
          {configuredParams.length > 0 && (
            <div style={rawParamsStyle}>
              Configured values (read-only):
              {configuredParams.map(([k, v]) => (
                <div key={k}><code>{k}</code>: <code>{formatValue(v)}</code></div>
              ))}
            </div>
          )}
        </div>
      )}
      {selected && !hideDocstring && selected.docstring && (
        <div style={docstringStyle}>{selected.docstring}</div>
      )}
      {selected && visibleSchema && (
        <ParamForm
          schema={visibleSchema}
          values={values}
          onChange={onParamChange}
          suggestions={suggestions}
        />
      )}
    </div>
  )
}
