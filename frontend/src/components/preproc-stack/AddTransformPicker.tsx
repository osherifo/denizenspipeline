/**
 * "+ Add transform" — dropdown that lists registered transforms and
 * adds the chosen one to the stack.
 *
 * Phase 6a is a plain <select>; Phase 6b can replace with a richer
 * picker (grouped by source, with descriptions) once we have more
 * than the identity placeholder shipped.
 */

import { useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'
import { CustomAddonModal } from './CustomAddonModal'


const wrapperStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  margin: '8px 0 16px 0',
}

const selectStyle: CSSProperties = {
  flex: 1,
  background: 'var(--bg-input)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '8px 10px',
  fontSize: 13,
  fontFamily: 'inherit',
  borderRadius: 4,
}

const buttonStyle: CSSProperties = {
  background: 'var(--accent-cyan)',
  color: 'var(--bg-primary)',
  border: 'none',
  padding: '8px 16px',
  fontSize: 13,
  fontWeight: 700,
  cursor: 'pointer',
  borderRadius: 4,
}


const CUSTOM_SENTINEL = '__custom__'


export function AddTransformPicker() {
  const transforms = usePreprocStackStore((s) => s.transforms)
  const addTransform = usePreprocStackStore((s) => s.addTransform)
  const [selected, setSelected] = useState('')
  const [customModalOpen, setCustomModalOpen] = useState(false)

  const handleAdd = () => {
    if (!selected) return
    if (selected === CUSTOM_SENTINEL) {
      setCustomModalOpen(true)
      setSelected('')
      return
    }
    addTransform(selected)
    setSelected('')
  }

  return (
    <>
      <div style={wrapperStyle}>
        <select
          style={selectStyle}
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">+ Add transform...</option>
          {transforms.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name} · {t.version} · {t.source}
            </option>
          ))}
          <option value={CUSTOM_SENTINEL}>
            ＋ Author custom transform...
          </option>
        </select>
        <button
          style={{
            ...buttonStyle,
            opacity: selected ? 1 : 0.5,
            cursor: selected ? 'pointer' : 'not-allowed',
          }}
          disabled={!selected}
          onClick={handleAdd}
        >
          Add
        </button>
      </div>

      <CustomAddonModal
        kind="transform"
        isOpen={customModalOpen}
        onClose={() => setCustomModalOpen(false)}
      />
    </>
  )
}
