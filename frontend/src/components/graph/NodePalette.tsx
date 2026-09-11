/** Searchable list of node types, grouped; click one to add it to the graph. */
import { useState } from 'react'
import type { CSSProperties } from 'react'

export interface PaletteItem {
  type: string
  label: string
  group: string
  color: string
  description?: string
  /** Second tooltip line, e.g. "inputs → outputs". */
  detail?: string
  badge?: string
}

interface Props {
  items: PaletteItem[]
  /** Groups listed first, in this order; the rest follow alphabetically. */
  groupOrder?: string[]
  onAdd: (type: string) => void
  height?: number | string
}

const input: CSSProperties = {
  width: '100%', boxSizing: 'border-box', marginBottom: 8, padding: '5px 8px', borderRadius: 4,
  border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit',
}
const small: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)' }

export function NodePalette({ items, groupOrder = [], onAdd, height = 480 }: Props) {
  const [filter, setFilter] = useState('')
  const q = filter.toLowerCase()
  const shown = items.filter((i) => !q || `${i.label} ${i.type} ${i.description ?? ''}`.toLowerCase().includes(q))
  const rank = (g: string) => (groupOrder.includes(g) ? groupOrder.indexOf(g) : groupOrder.length)
  const groups = [...new Set(shown.map((i) => i.group))].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 8, height, overflowY: 'auto', boxSizing: 'border-box' }}>
      <input style={input} placeholder="find a node…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      {groups.map((g) => {
        const members = shown.filter((i) => i.group === g)
        return (
          <div key={g} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color: members[0].color, marginBottom: 4 }}>{g}</div>
            {members.map((i) => (
              <div
                key={i.type}
                title={[i.description, i.detail, 'click to add'].filter(Boolean).join('\n')}
                onClick={() => onAdd(i.type)}
                style={{ padding: '4px 6px', borderLeft: `3px solid ${i.color}`, borderRadius: 4, marginBottom: 3, cursor: 'pointer', fontSize: 12, background: 'var(--bg-primary)' }}
              >
                <div style={{ fontWeight: 600 }}>{i.label}{i.badge ? <span style={{ ...small, marginLeft: 4 }}>{i.badge}</span> : null}</div>
                {i.description && <div style={{ ...small, fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{i.description}</div>}
              </div>
            ))}
          </div>
        )
      })}
      {shown.length === 0 && <div style={small}>no node matches</div>}
    </div>
  )
}
