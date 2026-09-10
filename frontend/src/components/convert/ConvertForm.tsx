/** Tab 5: Run DICOM-to-BIDS conversion — form + live progress. */
import { useState, useEffect } from 'react'
import type { CSSProperties } from 'react'
import { useConvertStore, runFormParams, runFormYaml } from '../../stores/convert-store'
import { ConvertProgress } from './ConvertProgress'
import { PathField } from '../common/PathPicker'

const containerStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '20px 24px',
}

const titleStyle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 16,
}

const fieldRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  marginBottom: 12,
  gap: 12,
}

const labelStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  width: 110,
  textAlign: 'right',
  flexShrink: 0,
}

const inputStyle: CSSProperties = {
  padding: '8px 12px',
  fontSize: 12,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  color: 'var(--text-primary)',
  flex: 1,
  maxWidth: 400,
}

const selectStyle: CSSProperties = {
  ...inputStyle,
  appearance: 'auto' as const,
  maxWidth: 250,
}

const checkRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  marginBottom: 8,
  gap: 8,
  marginLeft: 122,
}

const checkLabel: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  userSelect: 'none',
}

const checkboxStyle: CSSProperties = {
  width: 14,
  height: 14,
  cursor: 'pointer',
  accentColor: 'var(--accent-cyan)',
}

const sectionTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 16,
  marginBottom: 10,
}

const btnStyle: CSSProperties = {
  padding: '8px 24px',
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 6,
  cursor: 'pointer',
}

const primaryBtn: CSSProperties = {
  ...btnStyle,
  border: 'none',
  backgroundColor: 'var(--accent-cyan)',
  color: 'var(--on-accent)',
}

const secondaryBtn: CSSProperties = {
  ...btnStyle,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}
const sectionLabelBorder: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 20,
  marginBottom: 10,
  borderTop: '1px solid var(--border)',
  paddingTop: 16,
}

export function ConvertForm() {
  const {
    running, runEvents, runStartTime, runError,
    heuristics, heuristicsLoading, loadHeuristics,
    startRun, clearRun,
    runForm, updateRunForm, runFormError,
    savedConfigs, savedConfigsLoading, loadSavedConfigs, saveCurrentRunConfig, loadSavedConfig, deleteSavedConfig,
  } = useConvertStore()

  // Form state lives in the store (a saved config can load back into it).
  const { sourceDir, bidsDir, subject, heuristic, session, datasetName, grouping, minmeta, overwrite, validateBids } = runForm
  const setSourceDir = (v: string) => updateRunForm({ sourceDir: v })
  const setBidsDir = (v: string) => updateRunForm({ bidsDir: v })
  const setSubject = (v: string) => updateRunForm({ subject: v })
  const setHeuristic = (v: string) => updateRunForm({ heuristic: v })
  const setSession = (v: string) => updateRunForm({ session: v })
  const setDatasetName = (v: string) => updateRunForm({ datasetName: v })
  const setGrouping = (v: string) => updateRunForm({ grouping: v })
  const setMinmeta = (v: boolean) => updateRunForm({ minmeta: v })
  const setOverwrite = (v: boolean) => updateRunForm({ overwrite: v })
  const setValidateBids = (v: boolean) => updateRunForm({ validateBids: v })
  const [showSave, setShowSave] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saveDesc, setSaveDesc] = useState('')
  const [showSaved, setShowSaved] = useState(false)
  const [saveStatus, setSaveStatus] = useState<string | null>(null)

  const handleSave = async () => {
    const name = saveName.trim() || `convert_${subject || 'subject'}_${heuristic || 'heuristic'}`
    try {
      await saveCurrentRunConfig(name, saveDesc.trim() || undefined)
      setSaveStatus(`Saved as ${name}`)
      setShowSave(false); setSaveName(''); setSaveDesc('')
    } catch (e) {
      setSaveStatus(String(e))
    }
  }

  const handleExportYaml = () => {
    const blob = new Blob([runFormYaml(runForm)], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `convert_${subject || 'subject'}.yaml`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Load heuristics for dropdown
  useEffect(() => { loadHeuristics() }, [])

  const handleRun = () => {
    startRun(runFormParams(runForm) as any)
  }

  const canRun = sourceDir.trim() && bidsDir && subject && heuristic && !running

  const hasProgress = runEvents.length > 0 || running || runError

  return (
    <div>
      <div style={containerStyle}>
        <div style={titleStyle}>DICOM-to-BIDS Conversion</div>

        {/* Required fields */}
        <div style={fieldRow}>
          <span style={labelStyle}>Source Dir</span>
          <PathField style={inputStyle} value={sourceDir} onChange={setSourceDir}
            placeholder="/data/dicom/sub-01/session1/" />
        </div>

        <div style={fieldRow}>
          <span style={labelStyle}>BIDS Dir</span>
          <PathField style={inputStyle} value={bidsDir} onChange={setBidsDir}
            placeholder="/data/bids/" />
        </div>

        <div style={fieldRow}>
          <span style={labelStyle}>Subject</span>
          <input style={inputStyle} value={subject} onChange={(e) => setSubject(e.target.value)}
            placeholder="01" />
        </div>

        <div style={fieldRow}>
          <span style={labelStyle}>Heuristic</span>
          <select style={selectStyle} value={heuristic} onChange={(e) => setHeuristic(e.target.value)}>
            <option value="">Select heuristic...</option>
            {heuristics.map((h) => (
              <option key={h.name} value={h.name}>
                {h.name}{h.scanner_pattern ? ` (${h.scanner_pattern})` : ''}
              </option>
            ))}
          </select>
          {heuristicsLoading && (
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>loading...</span>
          )}
        </div>

        {/* Optional fields */}
        <div style={sectionTitle}>Optional</div>

        <div style={fieldRow}>
          <span style={labelStyle}>Session</span>
          <input style={inputStyle} value={session} onChange={(e) => setSession(e.target.value)}
            placeholder="01 (optional)" />
        </div>

        <div style={fieldRow}>
          <span style={labelStyle}>Dataset Name</span>
          <input style={inputStyle} value={datasetName} onChange={(e) => setDatasetName(e.target.value)}
            placeholder="MyDataset (optional)" />
        </div>

        <div style={fieldRow}>
          <span style={labelStyle}>Grouping</span>
          <input style={inputStyle} value={grouping} onChange={(e) => setGrouping(e.target.value)}
            placeholder="studyUID (optional)" />
        </div>

        {/* Checkboxes */}
        <div style={sectionTitle}>Options</div>

        <div style={checkRow}>
          <input
            type="checkbox"
            id="convert-minmeta"
            checked={minmeta}
            onChange={(e) => setMinmeta(e.target.checked)}
            style={checkboxStyle}
          />
          <label htmlFor="convert-minmeta" style={checkLabel}>Minimal metadata (minmeta)</label>
        </div>

        <div style={checkRow}>
          <input
            type="checkbox"
            id="convert-overwrite"
            checked={overwrite}
            onChange={(e) => setOverwrite(e.target.checked)}
            style={checkboxStyle}
          />
          <label htmlFor="convert-overwrite" style={checkLabel}>Overwrite existing outputs</label>
        </div>

        <div style={checkRow}>
          <input
            type="checkbox"
            id="convert-validate"
            checked={validateBids}
            onChange={(e) => setValidateBids(e.target.checked)}
            style={checkboxStyle}
          />
          <label htmlFor="convert-validate" style={checkLabel}>Validate BIDS after conversion</label>
        </div>

        {/* Actions */}
        <div style={{ marginTop: 20, display: 'flex', gap: 12 }}>
          <button style={primaryBtn} onClick={handleRun} disabled={!canRun}>
            {running ? 'Running...' : 'Run Conversion'}
          </button>
          <button style={secondaryBtn} onClick={() => { setShowSave(!showSave); setSaveStatus(null) }}>Save Config</button>
          <button style={secondaryBtn} onClick={() => { setShowSaved(!showSaved); if (!showSaved) loadSavedConfigs() }}>Saved Configs</button>
          <button style={secondaryBtn} onClick={handleExportYaml} disabled={!bidsDir && !sourceDir}>Export YAML</button>
        </div>
        {saveStatus && <div style={{ marginTop: 8, fontSize: 12, color: runFormError ? 'var(--accent-red)' : 'var(--accent-green)' }}>{saveStatus}</div>}
        {showSave && (
          <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              style={{ ...inputStyle, maxWidth: 240 }}
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder={`convert_${subject || 'subject'}_${heuristic || 'heuristic'}`}
              onKeyDown={(e) => { if (e.key === 'Enter') void handleSave() }}
            />
            <input
              style={{ ...inputStyle, maxWidth: 320 }}
              value={saveDesc}
              onChange={(e) => setSaveDesc(e.target.value)}
              placeholder="description (optional)"
            />
            <button style={secondaryBtn} onClick={() => void handleSave()}>Save</button>
            <button style={secondaryBtn} onClick={() => setShowSave(false)}>Cancel</button>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>→ $FMRIFLOW_HOME/configs/convert/</span>
          </div>
        )}
        {showSaved && (
          <div style={{ marginTop: 12, border: '1px solid var(--border)', borderRadius: 6, padding: 12, backgroundColor: 'var(--bg-secondary)' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
              Saved single-run configs {savedConfigsLoading && '(loading...)'}
            </div>
            {savedConfigs.filter((c) => c.type === 'single').length === 0 && !savedConfigsLoading && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>No saved configs yet.</div>
            )}
            {savedConfigs.filter((c) => c.type === 'single').map((c) => (
              <div key={c.filename} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, fontSize: 12 }}>
                <button style={{ ...secondaryBtn, fontSize: 11, padding: '4px 12px' }} onClick={() => { loadSavedConfig(c.filename); setShowSaved(false) }}>Load</button>
                <span style={{ flex: 1 }}>{c.name}{c.description ? <span style={{ color: 'var(--text-secondary)' }}> — {c.description}</span> : null}</span>
                <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{c.subject ? `sub-${c.subject} · ` : ''}{c.heuristic}</span>
                <button style={{ ...secondaryBtn, fontSize: 11, padding: '4px 8px' }} onClick={() => { if (confirm(`Delete ${c.name}?`)) deleteSavedConfig(c.filename) }}>✕</button>
              </div>
            ))}
          </div>
        )}

      </div>

      {/* Live progress */}
      {hasProgress && (
        <ConvertProgress
          events={runEvents}
          startTime={runStartTime}
          running={running}
          error={runError}
          onDismiss={clearRun}
        />
      )}
    </div>
  )
}
