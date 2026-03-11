/** Key-value editor for run_map (maps backend run names to pipeline run names). */
import { useState } from 'react'

interface Props {
  value: Record<string, string>
  onChange: (value: Record<string, string>) => void
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginBottom: 6,
}

const inputStyle: React.CSSProperties = {
  padding: '6px 10px',
  fontSize: 12,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  width: 140,
}

const smallBtn: React.CSSProperties = {
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 4,
  cursor: 'pointer',
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
}

export function RunMapEditor({ value, onChange }: Props) {
  const entries = Object.entries(value)

  const update = (oldKey: string, newKey: string, newVal: string) => {
    const next = { ...value }
    if (oldKey !== newKey) delete next[oldKey]
    next[newKey] = newVal
    onChange(next)
  }

  const remove = (key: string) => {
    const next = { ...value }
    delete next[key]
    onChange(next)
  }

  const add = () => {
    const key = `run-${String(entries.length + 1).padStart(2, '0')}`
    onChange({ ...value, [key]: '' })
  }

  return (
    <div>
      {entries.map(([k, v]) => (
        <div key={k} style={rowStyle}>
          <input
            style={inputStyle}
            value={k}
            onChange={(e) => update(k, e.target.value, v)}
            placeholder="run-01"
          />
          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{'\u2192'}</span>
          <input
            style={{ ...inputStyle, width: 180 }}
            value={v}
            onChange={(e) => update(k, k, e.target.value)}
            placeholder="pipeline_run_name"
          />
          <button style={smallBtn} onClick={() => remove(k)}>{'\u2717'}</button>
        </div>
      ))}
      <button style={smallBtn} onClick={add}>+ Add mapping</button>
    </div>
  )
}
