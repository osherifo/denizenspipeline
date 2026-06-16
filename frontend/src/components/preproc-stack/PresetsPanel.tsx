/**
 * PresetsPanel — list saved stack recipes + save-current / load /
 * delete actions.
 *
 * Presets live as YAML files under
 * ``$FMRIFLOW_HOME/addons/pipelines/``. Each preset is just the
 * stack recipe (bootstrap + transforms + their params) — no
 * subject binding, no output paths. Loading a preset overwrites
 * the current composition; the run-binding fields (subject /
 * output_dir / etc.) stay untouched.
 */

import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'


const panelStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: 12,
  marginTop: 16,
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: 8,
}

const headerLabelStyle: CSSProperties = {
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 1,
  color: 'var(--text-secondary)',
}

const saveBoxStyle: CSSProperties = {
  display: 'flex',
  gap: 8,
  marginBottom: 12,
  alignItems: 'center',
}

const smallInputStyle: CSSProperties = {
  flex: 1,
  background: 'var(--bg-input)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '6px 8px',
  fontSize: 12,
  fontFamily: 'inherit',
  borderRadius: 4,
}

const buttonStyle: CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '4px 10px',
  fontSize: 11,
  cursor: 'pointer',
  borderRadius: 4,
}


export function PresetsPanel() {
  const presets = usePreprocStackStore((s) => s.presets)
  const presetError = usePreprocStackStore((s) => s.presetError)
  const refreshPresets = usePreprocStackStore((s) => s.refreshPresets)
  const savePreset = usePreprocStackStore((s) => s.savePreset)
  const loadPreset = usePreprocStackStore((s) => s.loadPreset)
  const deletePreset = usePreprocStackStore((s) => s.deletePreset)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  useEffect(() => {
    void refreshPresets()
  }, [refreshPresets])

  function onSave() {
    const trimmed = name.trim()
    if (!trimmed) return
    void savePreset(trimmed, description.trim())
    setName('')
    setDescription('')
  }

  function onDelete(presetName: string) {
    const ok = window.confirm(`Delete preset "${presetName}"?`)
    if (!ok) return
    void deletePreset(presetName)
  }

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <span style={headerLabelStyle}>Presets ({presets.length})</span>
        <button style={buttonStyle} onClick={() => void refreshPresets()}>
          Refresh
        </button>
      </div>

      <div style={saveBoxStyle}>
        <input
          style={smallInputStyle}
          placeholder="preset name (a-z, 0-9, _, -)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          style={{ ...smallInputStyle, flex: 2 }}
          placeholder="description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button
          style={{
            ...buttonStyle,
            color: name.trim() ? 'var(--accent-green)' : 'var(--text-secondary)',
            borderColor: name.trim() ? 'var(--accent-green)' : 'var(--border)',
            opacity: name.trim() ? 1 : 0.5,
            cursor: name.trim() ? 'pointer' : 'not-allowed',
          }}
          disabled={!name.trim()}
          onClick={onSave}
        >
          Save current stack
        </button>
      </div>

      {presetError && (
        <div
          style={{
            color: 'var(--accent-red)',
            fontSize: 11,
            marginBottom: 8,
            padding: 6,
            background: 'var(--bg-input)',
            border: '1px solid var(--accent-red)',
            borderRadius: 4,
          }}
        >
          {presetError}
        </div>
      )}

      {presets.length === 0 && (
        <div
          style={{
            fontSize: 12,
            color: 'var(--text-secondary)',
            fontStyle: 'italic',
          }}
        >
          No saved presets yet. Save the current stack above.
        </div>
      )}

      {presets.map((p) => (
        <div
          key={p.name}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto auto',
            gap: 8,
            padding: '6px 8px',
            borderRadius: 4,
            fontSize: 12,
            alignItems: 'center',
            marginBottom: 4,
          }}
        >
          <div>
            <div style={{ fontWeight: 600 }}>{p.name}</div>
            {p.description && (
              <div
                style={{
                  fontSize: 11,
                  color: 'var(--text-secondary)',
                  fontStyle: 'italic',
                }}
              >
                {p.description}
              </div>
            )}
            <div
              style={{
                fontSize: 10,
                color: 'var(--text-secondary)',
                marginTop: 2,
              }}
            >
              bootstrap: {p.bootstrap_kind} · {p.n_transforms} transform{p.n_transforms === 1 ? '' : 's'}
            </div>
          </div>
          <button
            style={{
              ...buttonStyle,
              color: 'var(--accent-cyan)',
              borderColor: 'var(--accent-cyan)',
            }}
            onClick={() => void loadPreset(p.name)}
            title="Load this preset into the composer"
          >
            Load
          </button>
          <button
            style={{ ...buttonStyle, color: 'var(--accent-red)' }}
            onClick={() => onDelete(p.name)}
            title="Delete this preset"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
