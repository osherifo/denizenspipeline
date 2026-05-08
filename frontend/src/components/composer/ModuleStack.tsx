/** ModuleStack — list of ModuleSlots with up/down reorder + remove.
 *
 * Used by stages that take a list of modules (features, analyze,
 * preparation pipeline-mode steps). The stack itself doesn't know
 * the schema for individual entries — it just renders them and
 * forwards the user's intent (add, remove, move, edit) through
 * callbacks. The caller maps each entry to a (name, values) pair
 * and back when constructing the per-entry ModuleSlot props.
 */

import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'

interface ModuleStackProps<T> {
  items: T[]
  /** Render a compact one-liner shown on the collapsed entry. */
  renderSummary: (item: T, index: number) => ReactNode
  /** Render the full editor (typically a ModuleSlot). */
  renderEditor: (item: T, index: number) => ReactNode
  /** Add an entry. The stack appends a default item provided here. */
  onAdd: () => void
  onRemove: (index: number) => void
  onMove: (from: number, to: number) => void
  /** Label for the add button. */
  addLabel: string
  /** Empty-state message shown when items.length === 0. */
  emptyMessage?: string
  /** Index that should start expanded (e.g. just-added entry). */
  initialOpenIndex?: number | null
  /** Max number of entries the stack will allow. The "+ Add" button
   * disappears once items.length reaches this value. Use 1 to model
   * single-pick stages (stimulus, response, model) with the same
   * "+ Add" affordance the multi-pick stages have. */
  maxItems?: number
  /** Hide the up/down reorder controls (pointless when maxItems === 1). */
  hideMove?: boolean
}

const itemStyle: CSSProperties = {
  border: '1px solid var(--border)',
  borderRadius: 6,
  marginBottom: 8,
  backgroundColor: 'var(--bg-input)',
  overflow: 'hidden',
}

const itemHeaderStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 12px',
  cursor: 'pointer',
  userSelect: 'none',
}

const summaryWrap: CSSProperties = {
  flex: 1,
  fontSize: 13,
  color: 'var(--text-primary)',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const buttonGroup: CSSProperties = {
  display: 'flex',
  gap: 4,
  flexShrink: 0,
}

const iconBtn = (disabled = false): CSSProperties => ({
  border: '1px solid var(--border)',
  borderRadius: 4,
  backgroundColor: 'transparent',
  color: disabled ? 'var(--text-secondary)' : 'var(--text-primary)',
  fontSize: 12,
  width: 24,
  height: 24,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.4 : 1,
  padding: 0,
})

const removeBtn: CSSProperties = {
  ...iconBtn(),
  color: 'var(--accent-red, #ef5350)',
  borderColor: 'var(--accent-red, #ef5350)',
}

const editorBody: CSSProperties = {
  padding: '12px',
  borderTop: '1px solid var(--border)',
  backgroundColor: 'var(--bg-card)',
}

const addBtnStyle: CSSProperties = {
  padding: '8px 16px',
  fontSize: 13,
  fontWeight: 600,
  border: '1px dashed var(--border)',
  borderRadius: 6,
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  width: '100%',
}

const emptyStyle: CSSProperties = {
  padding: '12px',
  fontSize: 12,
  color: 'var(--text-secondary)',
  fontStyle: 'italic',
  textAlign: 'center',
}

export function ModuleStack<T>({
  items,
  renderSummary,
  renderEditor,
  onAdd,
  onRemove,
  onMove,
  addLabel,
  emptyMessage,
  initialOpenIndex = null,
  maxItems,
  hideMove = false,
}: ModuleStackProps<T>) {
  const [openIndex, setOpenIndex] = useState<number | null>(initialOpenIndex)

  const handleAdd = () => {
    onAdd()
    setOpenIndex(items.length) // open the just-added entry
  }

  const stop = (e: React.MouseEvent) => e.stopPropagation()
  const canAdd = maxItems == null || items.length < maxItems

  return (
    <div>
      {items.length === 0 && emptyMessage && (
        <div style={emptyStyle}>{emptyMessage}</div>
      )}
      {items.map((item, i) => {
        const isOpen = openIndex === i
        return (
          <div key={i} style={itemStyle}>
            <div style={itemHeaderStyle} onClick={() => setOpenIndex(isOpen ? null : i)}>
              <div style={summaryWrap}>{renderSummary(item, i)}</div>
              <div style={buttonGroup} onClick={stop}>
                {!hideMove && (
                  <>
                    <button
                      type="button"
                      style={iconBtn(i === 0)}
                      onClick={() => i > 0 && onMove(i, i - 1)}
                      disabled={i === 0}
                      title="Move up"
                      aria-label="Move up"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      style={iconBtn(i === items.length - 1)}
                      onClick={() => i < items.length - 1 && onMove(i, i + 1)}
                      disabled={i === items.length - 1}
                      title="Move down"
                      aria-label="Move down"
                    >
                      ↓
                    </button>
                  </>
                )}
                <button
                  type="button"
                  style={removeBtn}
                  onClick={() => {
                    onRemove(i)
                    if (openIndex === i) setOpenIndex(null)
                  }}
                  title="Remove"
                  aria-label="Remove"
                >
                  ×
                </button>
              </div>
            </div>
            {isOpen && <div style={editorBody}>{renderEditor(item, i)}</div>}
          </div>
        )
      })}
      {canAdd && (
        <button type="button" style={addBtnStyle} onClick={handleAdd}>
          + {addLabel}
        </button>
      )}
    </div>
  )
}
