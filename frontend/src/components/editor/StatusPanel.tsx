import type { CSSProperties } from 'react'
/** Validation status display. */
import type { CodeValidationResult, ParamSchema } from '../../api/types'

interface StatusPanelProps {
  validation: CodeValidationResult | null
  validating: boolean
  saveError: string | null
  saveSuccess: boolean
  isDirty: boolean
  onValidate: () => void
  onSave: () => void
  onDelete: () => void
  hasPlugin: boolean
}

const panelStyle: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderTop: '1px solid var(--border)',
  padding: '12px 16px',
}

const statusRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  fontSize: 13,
  marginBottom: 4,
}

const btnStyle = (variant: 'primary' | 'danger' | 'default'): CSSProperties => ({
  padding: '8px 16px',
  fontSize: 13,
  fontFamily: 'inherit',
  fontWeight: 600,
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  backgroundColor:
    variant === 'primary' ? 'var(--accent-cyan)'
    : variant === 'danger' ? 'rgba(255, 23, 68, 0.15)'
    : 'var(--bg-input)',
  color:
    variant === 'primary' ? '#0a0a1a'
    : variant === 'danger' ? 'var(--accent-red)'
    : 'var(--text-primary)',
})

const actionBar: CSSProperties = {
  display: 'flex',
  gap: 8,
  marginTop: 12,
}

export function StatusPanel({
  validation,
  validating,
  saveError,
  saveSuccess,
  isDirty,
  onValidate,
  onSave,
  onDelete,
  hasPlugin,
}: StatusPanelProps) {
  const v = validation

  return (
    <div style={panelStyle}>
      {/* Status indicators */}
      {validating && (
        <div style={statusRow}>
          <span style={{ color: 'var(--accent-yellow)' }}>...</span>
          <span style={{ color: 'var(--text-secondary)' }}>Validating...</span>
        </div>
      )}

      {v && !validating && (
        <>
          {/* Syntax / overall */}
          <div style={statusRow}>
            <span style={{ color: v.valid ? 'var(--accent-green)' : 'var(--accent-red)' }}>
              {v.valid ? '\u2713' : '\u2717'}
            </span>
            <span>
              {v.valid ? 'Valid plugin' : `${v.errors.length} error(s)`}
            </span>
          </div>

          {/* Plugin name + category */}
          {v.plugin_name && (
            <div style={statusRow}>
              <span style={{ color: 'var(--accent-cyan)' }}>\u2713</span>
              <span>
                Registered as <strong>{v.category}</strong> / <strong>{v.plugin_name}</strong>
              </span>
            </div>
          )}

          {v.class_name && (
            <div style={statusRow}>
              <span style={{ color: 'var(--accent-cyan)' }}>\u2713</span>
              <span>Class: {v.class_name}</span>
            </div>
          )}

          {/* Errors */}
          {v.errors.map((err, i) => (
            <div key={i} style={{ ...statusRow, color: 'var(--accent-red)' }}>
              <span>\u2717</span>
              <span>{err}</span>
            </div>
          ))}

          {/* Warnings */}
          {v.warnings.map((w, i) => (
            <div key={i} style={{ ...statusRow, color: 'var(--accent-yellow)' }}>
              <span>!</span>
              <span>{w}</span>
            </div>
          ))}

          {/* Param preview */}
          {v.params && Object.keys(v.params).length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4, letterSpacing: 1 }}>
                PARAMETERS
              </div>
              {Object.entries(v.params).map(([name, field]) => (
                <div key={name} style={{ fontSize: 12, color: 'var(--text-primary)', paddingLeft: 8, marginBottom: 2 }}>
                  <span style={{ color: 'var(--accent-cyan)' }}>{name}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    : {field.type}
                    {field.default !== undefined && ` = ${JSON.stringify(field.default)}`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Save status */}
      {saveError && (
        <div style={{ ...statusRow, color: 'var(--accent-red)', marginTop: 8 }}>
          <span>\u2717</span>
          <span>{saveError}</span>
        </div>
      )}
      {saveSuccess && (
        <div style={{ ...statusRow, color: 'var(--accent-green)', marginTop: 8 }}>
          <span>\u2713</span>
          <span>Saved and registered</span>
        </div>
      )}

      {/* Action buttons */}
      <div style={actionBar}>
        <button style={btnStyle('default')} onClick={onValidate} disabled={validating}>
          Validate
        </button>
        <button style={btnStyle('primary')} onClick={onSave}>
          Save & Register
        </button>
        {hasPlugin && (
          <button style={btnStyle('danger')} onClick={onDelete}>
            Delete
          </button>
        )}
        {isDirty && (
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', alignSelf: 'center', marginLeft: 'auto' }}>
            unsaved changes
          </span>
        )}
      </div>
    </div>
  )
}
