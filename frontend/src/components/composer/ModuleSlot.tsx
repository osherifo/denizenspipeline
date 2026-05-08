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
}: ModuleSlotProps) {
  const selected = useMemo(
    () => available.find((m) => m.name === selectedName),
    [available, selectedName],
  )

  return (
    <div style={wrapperStyle}>
      {label && <span style={labelStyle}>{label}</span>}
      <select
        style={selectStyle}
        value={selectedName}
        onChange={(e) => onSelect(e.target.value)}
      >
        <option value="">{placeholder}</option>
        {available.map((m) => (
          <option key={m.name} value={m.name}>{m.name}</option>
        ))}
      </select>
      {selected && !hideDocstring && selected.docstring && (
        <div style={docstringStyle}>{selected.docstring}</div>
      )}
      {selected && (
        <ParamForm
          schema={selected.params}
          values={values}
          onChange={onParamChange}
          suggestions={suggestions}
        />
      )}
    </div>
  )
}
