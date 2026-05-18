/** SingleModuleSlot — "+ Add module" affordance for single-pick stages.
 *
 * Stimulus, response (loader), and model each have one slot that
 * holds at most one module. Without this wrapper, the composer
 * shows a bare dropdown with the placeholder "-- select … --" by
 * default. That's inconsistent with features / analyze, which start
 * empty and show a "+ Add …" button until the user explicitly picks
 * a module.
 *
 * SingleModuleSlot adapts ModuleStack with maxItems=1 over a single
 * config object. The "selector key" (e.g. `loader` for stimulus,
 * `type` for model) tells the wrapper which field on the config
 * holds the picked module's name.
 *
 *   - When the selector key is missing on `value`, items=[] and the
 *     stack renders a "+ Add …" button.
 *   - When the user clicks Add, we set `value = { [selectorKey]: '' }`
 *     so a single entry exists with the dropdown showing
 *     "-- select … --".
 *   - Picking a module fills `value[selectorKey]` and renders the
 *     module's ParamForm.
 *   - Removing clears the slot (back to "+ Add …").
 *
 * The on-disk schema is unchanged — config.stimulus is still a
 * single object. Only the UI treats it as a list-of-one.
 */

import type { ReactNode } from 'react'
import { ModuleSlot } from './ModuleSlot'
import { ModuleStack } from './ModuleStack'
import type { ModuleInfo } from '../../api/types'

interface SingleModuleSlotProps {
  /** Modules the user can pick from. */
  available: ModuleInfo[]
  /** The whole stage object — e.g. config.stimulus, config.model. */
  value: Record<string, unknown>
  /** Field on `value` that holds the picked module's name. */
  selectorKey: string
  /** Called with the next full object. Empty {} means "no module". */
  onChange: (next: Record<string, unknown>) => void
  /** "+ Add …" label. */
  addLabel: string
  /** Optional autocomplete suggestions for ParamForm. */
  suggestions?: Record<string, string[]>
  /** Schema fields to hide from the inner ParamForm (rendered
   * separately by the caller, e.g. `steps` on the pipeline preparer). */
  hiddenFields?: string[]
  /** Optional override for the entry's collapsed summary; defaults to
   * the picked module's name. */
  renderSummary?: (item: Record<string, unknown>) => ReactNode
}

const summaryDefault = (item: Record<string, unknown>, selectorKey: string): ReactNode => {
  const name = (item[selectorKey] as string) || ''
  return <strong>{name || '<pick>'}</strong>
}

export function SingleModuleSlot({
  available,
  value,
  selectorKey,
  onChange,
  addLabel,
  suggestions,
  hiddenFields,
  renderSummary,
}: SingleModuleSlotProps) {
  // The slot is "filled" when the selector key is present on the
  // value object — even if its value is an empty string (an entry
  // mid-pick). Use Object.prototype.hasOwnProperty to avoid
  // tripping on prototype keys.
  const isFilled =
    value && typeof value === 'object' &&
    Object.prototype.hasOwnProperty.call(value, selectorKey)
  const items = isFilled ? [value] : []

  return (
    <ModuleStack<Record<string, unknown>>
      items={items}
      maxItems={1}
      hideMove
      hideRemove
      addLabel={addLabel}
      onAdd={() => onChange({ [selectorKey]: '' })}
      onRemove={() => onChange({})}
      onMove={() => {
        /* no-op */
      }}
      renderSummary={(item) =>
        renderSummary ? renderSummary(item) : summaryDefault(item, selectorKey)
      }
      renderEditor={(item) => (
        <ModuleSlot
          available={available}
          selectedName={(item[selectorKey] as string) || ''}
          values={item}
          onSelect={(name) => onChange({ ...item, [selectorKey]: name })}
          onParamChange={(k, v) => onChange({ ...item, [k]: v })}
          suggestions={suggestions}
          hiddenFields={hiddenFields}
        />
      )}
    />
  )
}

