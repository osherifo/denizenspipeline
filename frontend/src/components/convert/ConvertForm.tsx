/** Tab 5: Run DICOM-to-BIDS conversion — form + live progress. */
import { useState, useEffect } from 'react'
import { useConvertStore } from '../../stores/convert-store'
import { ConvertProgress } from './ConvertProgress'

const containerStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '20px 24px',
}

const titleStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 16,
}

const fieldRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  marginBottom: 12,
  gap: 12,
}

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  width: 110,
  textAlign: 'right',
  flexShrink: 0,
}

const inputStyle: React.CSSProperties = {
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

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  appearance: 'auto' as const,
  maxWidth: 250,
}

const checkRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  marginBottom: 8,
  gap: 8,
  marginLeft: 122,
}

const checkLabel: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  userSelect: 'none',
}

const checkboxStyle: React.CSSProperties = {
  width: 14,
  height: 14,
  cursor: 'pointer',
  accentColor: 'var(--accent-cyan)',
}

const sectionTitle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 16,
  marginBottom: 10,
}

const btnStyle: React.CSSProperties = {
  padding: '8px 24px',
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 6,
  cursor: 'pointer',
}

const primaryBtn: React.CSSProperties = {
  ...btnStyle,
  border: 'none',
  backgroundColor: 'var(--accent-cyan)',
  color: '#000',
}

const sectionLabelBorder: React.CSSProperties = {
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
    collectResult, collecting, collectError, collect, clearCollect,
    startRun, clearRun,
  } = useConvertStore()

  // Form state
  const [sourceDir, setSourceDir] = useState('')
  const [bidsDir, setBidsDir] = useState('')
  const [subject, setSubject] = useState('')
  const [heuristic, setHeuristic] = useState('')
  const [session, setSession] = useState('')
  const [datasetName, setDatasetName] = useState('')
  const [grouping, setGrouping] = useState('')
  const [minmeta, setMinmeta] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [validateBids, setValidateBids] = useState(true)

  // Load heuristics for dropdown
  useEffect(() => { loadHeuristics() }, [])

  const handleRun = () => {
    const params: Record<string, unknown> = {
      source_dir: sourceDir.trim(),
      bids_dir: bidsDir,
      subject,
      heuristic,
    }
    if (session.trim()) {
      params.sessions = [session.trim()]
    }
    if (datasetName.trim()) params.dataset_name = datasetName.trim()
    if (grouping.trim()) params.grouping = grouping.trim()
    if (minmeta) params.minmeta = true
    if (overwrite) params.overwrite = true
    if (!validateBids) params.validate_bids = false

    startRun(params as any)
  }

  const handleCollect = () => {
    const params: Record<string, unknown> = {
      bids_dir: bidsDir,
      subject,
    }
    if (sourceDir.trim()) params.source_dir = sourceDir.trim()
    if (heuristic) params.heuristic = heuristic
    if (session.trim()) {
      params.sessions = [session.trim()]
    }
    if (datasetName.trim()) params.dataset_name = datasetName.trim()

    collect(params as any)
  }

  const canRun = sourceDir.trim() && bidsDir && subject && heuristic && !running
  const canCollect = bidsDir && subject && !collecting

  const hasProgress = runEvents.length > 0 || running || runError

  return (
    <div>
      <div style={containerStyle}>
        <div style={titleStyle}>DICOM-to-BIDS Conversion</div>

        {/* Required fields */}
        <div style={fieldRow}>
          <span style={labelStyle}>Source Dir</span>
          <input style={inputStyle} value={sourceDir} onChange={(e) => setSourceDir(e.target.value)}
            placeholder="/data/dicom/sub-01/session1/" />
        </div>

        <div style={fieldRow}>
          <span style={labelStyle}>BIDS Dir</span>
          <input style={inputStyle} value={bidsDir} onChange={(e) => setBidsDir(e.target.value)}
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
          <button
            style={{ ...btnStyle, border: '1px solid var(--border)', backgroundColor: 'var(--bg-input)', color: 'var(--text-secondary)' }}
            onClick={handleCollect}
            disabled={!canCollect}
          >
            {collecting ? 'Collecting...' : 'Collect Existing'}
          </button>
        </div>

        {/* Collect error */}
        {collectError && (
          <div style={{ marginTop: 16, fontSize: 12, color: 'var(--accent-red)' }}>
            {collectError}
          </div>
        )}

        {/* Collect result */}
        {collectResult && (
          <>
            <div style={sectionLabelBorder}>Collect Result</div>
            <div style={{ fontSize: 12, color: 'var(--accent-green)', fontWeight: 600, marginBottom: 8 }}>
              {'\u2713'} Manifest created: {collectResult.manifest.runs.length} runs found
            </div>
            {collectResult.manifest.runs.map((run) => (
              <div key={run.run_name} style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>
                {run.run_name} &middot; {run.modality} &middot; {run.n_volumes} volumes
                {run.tr != null && <> &middot; TR={run.tr}s</>}
              </div>
            ))}
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 8 }}>
              Saved to: {collectResult.manifest_path}
            </div>
            <button
              style={{ ...btnStyle, backgroundColor: 'var(--bg-input)', color: 'var(--text-secondary)', border: '1px solid var(--border)', marginTop: 12, fontSize: 11 }}
              onClick={() => {
                useConvertStore.setState({ tab: 'manifests' })
                clearCollect()
              }}
            >
              View in Manifests tab
            </button>
          </>
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
