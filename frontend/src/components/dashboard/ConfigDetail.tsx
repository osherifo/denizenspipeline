/** Config summary + inline YAML viewer/editor + action buttons. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import Editor from '@monaco-editor/react'
import type { ConfigDetail as ConfigDetailType } from '../../api/types'
import { saveConfigFile, copyConfigFile } from '../../api/client'
import { useDialog } from '../common/Dialog'
import { AnalysisGraphModal } from '../workflow/AnalysisGraphModal'

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

const yamlBox = (hasError: boolean): CSSProperties => ({
  border: `1px solid ${hasError ? 'var(--accent-red)' : 'var(--border)'}`,
  borderRadius: 6,
  height: 360,
  overflow: 'hidden',
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
  const [graphOpen, setGraphOpen] = useState(false)
  const dlg = useDialog()

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
    const name = await dlg.prompt('New filename:', { defaultValue: suggested })
    if (!name) return

    setCopying(true)
    try {
      const result = await copyConfigFile(config.filename, name)
      if (result.saved) onCopied?.(result.filename)
    } catch (e) {
      await dlg.alert(`Copy failed: ${e}`)
    } finally {
      setCopying(false)
    }
  }

  const cfg = config.config as Record<string, any>

  // YAML shape detection. Mirrors the same logic the server uses to
  // route a config to the subject / group / study orchestrator.
  const isStudy =
    typeof cfg.study === 'string' && Array.isArray(cfg.groups)
  const isGroup =
    !isStudy && typeof cfg.group === 'string' && Array.isArray(cfg.subjects)
  const scope: 'subject' | 'group' | 'study' =
    isStudy ? 'study' : isGroup ? 'group' : 'subject'

  // Comma-joined names with "+N more" suffix once the list gets long.
  const summariseList = (items: any[] | undefined, max = 4): string => {
    if (!items || items.length === 0) return '-'
    if (items.length <= max) return items.join(', ')
    return `${items.slice(0, max).join(', ')} +${items.length - max} more`
  }

  // Full untruncated list for the tooltip — newline-separated so the
  // browser's native title popup renders one item per line.
  const fullList = (items: any[] | undefined): string | undefined => {
    if (!items || items.length === 0) return undefined
    return items.join('\n')
  }

  // Field tuples [label, value, valueStyle?, tooltip?]. ``tooltip`` (if
  // set) is shown as the browser's native hover title — used for
  // truncated lists so the user can see every item without expanding.
  // Each scope assembles its own list so we don't end up showing
  // "Subject: -" for a group config.
  const fields: [string, string, CSSProperties?, string?][] = []

  if (scope === 'subject') {
    const experiment = cfg.experiment || '-'
    const subject = cfg.subject || '-'
    const modelType = cfg.model?.type || '-'
    const featureNames =
      (cfg.features || []).map((f: any) => f.name) as string[]
    const features =
      featureNames.length > 0
        ? summariseList(featureNames, 5)
        : '-'
    const prepCfg = cfg.preparation
    const prepType = prepCfg?.type || 'default'
    const outputDir = cfg.reporting?.output_dir || '-'
    const stimLoader = cfg.stimulus?.loader || '-'
    const respLoader = cfg.response?.loader || '-'
    const formatNames = (cfg.reporting?.formats || []) as string[]
    const formats =
      formatNames.length > 0 ? summariseList(formatNames, 5) : '-'
    let prepSummary = prepType
    if (prepType === 'pipeline' && prepCfg?.steps) {
      prepSummary = prepCfg.steps.map((s: any) => s.name).join(' \u2192 ')
    }
    fields.push(
      ['Experiment', experiment],
      ['Subject', subject],
      ['Model', modelType],
      ['Features', features, { fontSize: 11 }, fullList(featureNames)],
      ['Preparation', prepSummary, { fontSize: 11 }],
      ['Output', outputDir, { fontSize: 10, fontFamily: 'monospace' }],
      ['Stimulus', stimLoader],
      ['Response', respLoader],
      ['Reporters', formats, { fontSize: 11 }, fullList(formatNames)],
    )
  } else if (scope === 'group') {
    const tmpl = cfg.subject_template || {}
    const groupName = cfg.group || '-'
    const subjects = (cfg.subjects || []) as string[]
    const modelType = tmpl.model?.type || '-'
    const featureNames =
      (tmpl.features || []).map((f: any) => f.name) as string[]
    const stimLoader = tmpl.stimulus?.loader || '-'
    const respLoader = tmpl.response?.loader || '-'
    const outputDir = cfg.output_dir || '-'
    const analyzers =
      (cfg.group_analyze || []).map((g: any) => g.name) as string[]
    const reporters =
      (cfg.group_report || []).map((r: any) => r.name) as string[]
    const workers = cfg.parallel?.max_workers
    fields.push(
      ['Group', groupName],
      [
        'Subjects',
        subjects.length > 0
          ? `${summariseList(subjects, 6)} (${subjects.length})`
          : '-',
        { fontSize: 11 },
        fullList(subjects),
      ],
      ['Model', modelType],
      ['Features', summariseList(featureNames, 5), { fontSize: 11 }, fullList(featureNames)],
      ['Stimulus', stimLoader],
      ['Response', respLoader],
      ['Output', outputDir, { fontSize: 10, fontFamily: 'monospace' }],
      ['Group Analyze', summariseList(analyzers, 4), { fontSize: 11 }, fullList(analyzers)],
      ['Group Report', summariseList(reporters, 4), { fontSize: 11 }, fullList(reporters)],
      ['Parallel workers', workers != null ? String(workers) : '-'],
    )
  } else {
    // study
    const studyName = cfg.study || '-'
    const groups =
      (cfg.groups || []) as Array<{ name?: string; config?: string }>
    const groupNames = groups.map((g) => g.name || '?')
    const outputDir = cfg.output_dir || '-'
    const studyAnalyze =
      (cfg.study_analyze || []).map((a: any) => a.name) as string[]
    const studyReport =
      (cfg.study_report || []).map((r: any) => r.name) as string[]
    const workers = cfg.parallel?.max_workers
    fields.push(
      ['Study', studyName],
      [
        'Groups',
        groupNames.length > 0
          ? `${summariseList(groupNames, 6)} (${groupNames.length})`
          : '-',
        { fontSize: 11 },
        fullList(groupNames),
      ],
      ['Output', outputDir, { fontSize: 10, fontFamily: 'monospace' }],
      ['Study Analyze', summariseList(studyAnalyze, 4), { fontSize: 11 }, fullList(studyAnalyze)],
      ['Study Report', summariseList(studyReport, 4), { fontSize: 11 }, fullList(studyReport)],
      ['Parallel workers', workers != null ? String(workers) : '-'],
    )
  }

  return (
    <div style={cardStyle}>
      <div style={titleRow}>
        <div style={titleStyle}>{config.filename.replace('.yaml', '')}</div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{config.path}</div>
      </div>

      <div style={gridStyle}>
        {fields.map(([label, value, valueStyle, tooltip]) => (
          <div key={label} style={fieldCard}>
            <div style={fieldLabel}>{label}</div>
            <div
              style={{
                ...fieldValue,
                ...(valueStyle || {}),
                ...(tooltip ? { cursor: 'help', textDecoration: 'underline dotted var(--text-secondary)' } : {}),
              }}
              title={tooltip}
            >
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* YAML viewer / editor */}
      <button style={yamlToggle} onClick={() => setShowYaml(!showYaml)}>
        {showYaml ? '\u25BC Hide YAML' : '\u25B6 Show YAML'}
      </button>
      {showYaml && (
        <>
          <div style={yamlBox(saveErr !== null)}>
            <Editor
              height="100%"
              language="yaml"
              theme="vs-dark"
              value={editing ? yamlDraft : config.yaml_string}
              onChange={editing ? (v) => setYamlDraft(v ?? '') : undefined}
              options={{
                readOnly: !editing,
                domReadOnly: !editing,
                minimap: { enabled: false },
                fontSize: 12,
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
                tabSize: 2,
                insertSpaces: true,
                renderLineHighlight: editing ? 'line' : 'none',
                contextmenu: editing,
                padding: { top: 8 },
              }}
            />
          </div>
          {editing && (
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
          )}
        </>
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
        <button style={btnStyle('secondary')} onClick={() => setGraphOpen(true)}>
          View graph
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

      {graphOpen && (
        <AnalysisGraphModal
          target={{ kind: 'config', filename: config.filename }}
          title={`${config.filename} \u2014 preview graph`}
          onClose={() => setGraphOpen(false)}
        />
      )}
    </div>
  )
}
