/** Config summary + inline YAML viewer/editor + action buttons. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { ConfigDetail as ConfigDetailType } from '../../api/types'
import { saveConfigFile, copyConfigFile } from '../../api/client'

interface ConfigDetailProps {
  config: ConfigDetailType
  validationErrors: string[] | null
  validating: boolean
  onRun: () => void
  onValidate: () => void
  onSaved?: () => void
  onCopied?: (newFilename: string) => void
  isRunning: boolean
}

const cardStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '20px',
  marginBottom: 16,
}

const titleRow: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 16,
}

const titleStyle: CSSProperties = {
  fontSize: 18,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
}

const gridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
  gap: 10,
  marginBottom: 16,
}

const fieldCard: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
}

const fieldLabel: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 3,
}

const fieldValue: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
}

const yamlToggle: CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  fontSize: 12,
  cursor: 'pointer',
  fontFamily: 'inherit',
  padding: '4px 0',
  marginBottom: 8,
}

const yamlPre: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  padding: '12px 14px',
  borderRadius: 6,
  fontSize: 11,
  lineHeight: 1.6,
  color: 'var(--text-primary)',
  overflow: 'auto',
  maxHeight: 300,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  margin: 0,
}

const yamlTextarea = (hasError: boolean): CSSProperties => ({
  width: '100%',
  minHeight: 280,
  maxHeight: 520,
  padding: '12px 14px',
  borderRadius: 6,
  fontSize: 11,
  lineHeight: 1.6,
  fontFamily: '"JetBrains Mono", "Fira Code", monospace',
  backgroundColor: 'var(--bg-secondary)',
  border: `1px solid ${hasError ? 'var(--accent-red)' : 'var(--accent-cyan)'}`,
  color: 'var(--text-primary)',
  outline: 'none',
  resize: 'vertical',
  tabSize: 2,
})

const editBar: CSSProperties = {
  display: 'flex',
  gap: 8,
  marginTop: 8,
  alignItems: 'center',
}

const saveError: CSSProperties = {
  fontSize: 11,
  color: 'var(--accent-red)',
  fontFamily: 'monospace',
}

const actionBar: CSSProperties = {
  display: 'flex',
  gap: 8,
  marginTop: 12,
}

const btnStyle = (variant: 'primary' | 'secondary' | 'default'): CSSProperties => ({
  padding: '8px 20px',
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: variant === 'primary' ? 'none' : '1px solid var(--border)',
  borderRadius: 6,
  cursor: 'pointer',
  backgroundColor:
    variant === 'primary' ? 'var(--accent-cyan)'
    : variant === 'secondary' ? 'rgba(0, 229, 255, 0.08)'
    : 'var(--bg-input)',
  color: variant === 'primary' ? '#0a0a1a' : variant === 'secondary' ? 'var(--accent-cyan)' : 'var(--text-primary)',
  letterSpacing: 0.5,
})

const validationStyle = (ok: boolean): CSSProperties => ({
  marginTop: 12,
  padding: '8px 12px',
  borderRadius: 6,
  fontSize: 12,
  backgroundColor: ok ? 'rgba(0, 230, 118, 0.08)' : 'rgba(255, 23, 68, 0.08)',
  color: ok ? 'var(--accent-green)' : 'var(--accent-red)',
})

export function ConfigDetail({
  config,
  validationErrors,
  validating,
  onRun,
  onValidate,
  onSaved,
  onCopied,
  isRunning,
}: ConfigDetailProps) {
  const [showYaml, setShowYaml] = useState(false)
  const [editing, setEditing] = useState(false)
  const [yamlDraft, setYamlDraft] = useState(config.yaml_string)
  const [saving, setSaving] = useState(false)
  const [saveErr, setSaveErr] = useState<string | null>(null)
  const [copying, setCopying] = useState(false)

  // Reset the draft whenever a different config is selected or reloaded.
  useEffect(() => {
    setYamlDraft(config.yaml_string)
    setEditing(false)
    setSaveErr(null)
  }, [config.filename, config.yaml_string])

  const handleSave = async () => {
    setSaving(true)
    setSaveErr(null)
    try {
      await saveConfigFile(config.filename, yamlDraft)
      setEditing(false)
      onSaved?.()
    } catch (e) {
      setSaveErr(String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setYamlDraft(config.yaml_string)
    setEditing(false)
    setSaveErr(null)
  }

  const handleCopy = async () => {
    const base = config.filename.replace(/\.(yaml|yml)$/, '')
    const ext = config.filename.match(/\.(yaml|yml)$/)?.[0] ?? '.yaml'
    const suggested = `${base}_copy${ext}`
    const name = window.prompt('New filename:', suggested)
    if (!name) return

    setCopying(true)
    try {
      const result = await copyConfigFile(config.filename, name)
      if (result.saved) onCopied?.(result.filename)
    } catch (e) {
      window.alert(`Copy failed: ${e}`)
    } finally {
      setCopying(false)
    }
  }

  const cfg = config.config as Record<string, any>

  const experiment = cfg.experiment || '-'
  const subject = cfg.subject || '-'
  const modelType = cfg.model?.type || '-'
  const features = (cfg.features || []).map((f: any) => f.name).join(', ') || '-'
  const prepCfg = cfg.preparation
  const prepType = prepCfg?.type || 'default'
  const outputDir = cfg.reporting?.output_dir || '-'
  const stimLoader = cfg.stimulus?.loader || '-'
  const respLoader = cfg.response?.loader || '-'
  const formats = (cfg.reporting?.formats || []).join(', ') || '-'

  // Preparation steps summary
  let prepSummary = prepType
  if (prepType === 'pipeline' && prepCfg?.steps) {
    prepSummary = prepCfg.steps.map((s: any) => s.name).join(' \u2192 ')
  }

  return (
    <div style={cardStyle}>
      <div style={titleRow}>
        <div style={titleStyle}>{config.filename.replace('.yaml', '')}</div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{config.path}</div>
      </div>

      <div style={gridStyle}>
        <div style={fieldCard}>
          <div style={fieldLabel}>Experiment</div>
          <div style={fieldValue}>{experiment}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Subject</div>
          <div style={fieldValue}>{subject}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Model</div>
          <div style={fieldValue}>{modelType}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Features</div>
          <div style={{ ...fieldValue, fontSize: 11 }}>{features}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Preparation</div>
          <div style={{ ...fieldValue, fontSize: 11 }}>{prepSummary}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Output</div>
          <div style={{ ...fieldValue, fontSize: 10, fontFamily: 'monospace' }}>{outputDir}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Stimulus</div>
          <div style={fieldValue}>{stimLoader}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Response</div>
          <div style={fieldValue}>{respLoader}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Reporters</div>
          <div style={{ ...fieldValue, fontSize: 11 }}>{formats}</div>
        </div>
      </div>

      {/* YAML viewer / editor */}
      <button style={yamlToggle} onClick={() => setShowYaml(!showYaml)}>
        {showYaml ? '\u25BC Hide YAML' : '\u25B6 Show YAML'}
      </button>
      {showYaml && (
        editing ? (
          <>
            <textarea
              style={yamlTextarea(saveErr !== null)}
              value={yamlDraft}
              onChange={(e) => setYamlDraft(e.target.value)}
              spellCheck={false}
            />
            <div style={editBar}>
              <button
                style={btnStyle('primary')}
                onClick={handleSave}
                disabled={saving || yamlDraft === config.yaml_string}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button style={btnStyle('default')} onClick={handleCancel} disabled={saving}>
                Cancel
              </button>
              {saveErr && <span style={saveError}>{saveErr}</span>}
            </div>
          </>
        ) : (
          <pre style={yamlPre}>{config.yaml_string}</pre>
        )
      )}

      {/* Action buttons */}
      <div style={actionBar}>
        <button
          style={btnStyle('primary')}
          onClick={onRun}
          disabled={isRunning}
        >
          {isRunning ? 'Running...' : '\u25B6 Run'}
        </button>
        <button style={btnStyle('secondary')} onClick={onValidate} disabled={validating}>
          {validating ? 'Validating...' : 'Validate'}
        </button>
        {showYaml && !editing && (
          <button style={btnStyle('default')} onClick={() => setEditing(true)}>
            Edit YAML
          </button>
        )}
        <button style={btnStyle('default')} onClick={handleCopy} disabled={copying || editing}>
          {copying ? 'Copying...' : 'Duplicate'}
        </button>
      </div>

      {/* Validation results */}
      {validationErrors !== null && (
        <div style={validationStyle(validationErrors.length === 0)}>
          {validationErrors.length === 0
            ? '\u2713 Config is valid'
            : validationErrors.map((err, i) => <div key={i}>\u2717 {err}</div>)}
        </div>
      )}
    </div>
  )
}
