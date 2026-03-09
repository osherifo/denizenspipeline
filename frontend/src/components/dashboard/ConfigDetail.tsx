/** Config summary + YAML viewer + action buttons. */
import { useState } from 'react'
import type { ConfigDetail as ConfigDetailType } from '../../api/types'

interface ConfigDetailProps {
  config: ConfigDetailType
  validationErrors: string[] | null
  validating: boolean
  onRun: () => void
  onValidate: () => void
  onEditInComposer: () => void
  isRunning: boolean
}

const cardStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '20px',
  marginBottom: 16,
}

const titleRow: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 16,
}

const titleStyle: React.CSSProperties = {
  fontSize: 18,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
}

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
  gap: 10,
  marginBottom: 16,
}

const fieldCard: React.CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '10px 12px',
}

const fieldLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 3,
}

const fieldValue: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
}

const yamlToggle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  fontSize: 12,
  cursor: 'pointer',
  fontFamily: 'inherit',
  padding: '4px 0',
  marginBottom: 8,
}

const yamlPre: React.CSSProperties = {
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
}

const actionBar: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  marginTop: 12,
}

const btnStyle = (variant: 'primary' | 'secondary' | 'default'): React.CSSProperties => ({
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

const validationStyle = (ok: boolean): React.CSSProperties => ({
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
  onEditInComposer,
  isRunning,
}: ConfigDetailProps) {
  const [showYaml, setShowYaml] = useState(false)
  const cfg = config.config as Record<string, any>

  const experiment = cfg.experiment || '-'
  const subject = cfg.subject || '-'
  const modelType = cfg.model?.type || '-'
  const features = (cfg.features || []).map((f: any) => f.name).join(', ') || '-'
  const prepType = cfg.preprocessing?.type || 'default'
  const outputDir = cfg.reporting?.output_dir || '-'
  const stimLoader = cfg.stimulus?.loader || '-'
  const respLoader = cfg.response?.loader || '-'
  const formats = (cfg.reporting?.formats || []).join(', ') || '-'

  // Preprocessing steps summary
  let prepSummary = prepType
  if (prepType === 'pipeline' && cfg.preprocessing?.steps) {
    prepSummary = cfg.preprocessing.steps.map((s: any) => s.name).join(' \u2192 ')
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
          <div style={fieldLabel}>Preprocessing</div>
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

      {/* YAML viewer */}
      <button style={yamlToggle} onClick={() => setShowYaml(!showYaml)}>
        {showYaml ? '\u25BC Hide YAML' : '\u25B6 Show YAML'}
      </button>
      {showYaml && <pre style={yamlPre}>{config.yaml_string}</pre>}

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
        <button style={btnStyle('default')} onClick={onEditInComposer}>
          Edit in Composer
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
