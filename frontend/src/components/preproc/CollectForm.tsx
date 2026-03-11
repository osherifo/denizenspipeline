/** Tab 3: Collect — build manifest from existing preprocessing outputs. */
import { useState } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'
import { RunMapEditor } from './RunMapEditor'
import { QcBadge } from './QcBadge'

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
  width: 100,
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
  maxWidth: 200,
}

const btnStyle: React.CSSProperties = {
  padding: '8px 24px',
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  backgroundColor: 'var(--accent-cyan)',
  color: '#000',
}

const sectionLabel: React.CSSProperties = {
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

export function CollectForm() {
  const { collecting, collectResult, collectError, collect, clearCollect } = usePreprocStore()

  const [backend, setBackend] = useState('fmriprep')
  const [outputDir, setOutputDir] = useState('')
  const [subject, setSubject] = useState('')
  const [task, setTask] = useState('')
  const [sessions, setSessions] = useState('')
  const [bidsDir, setBidsDir] = useState('')
  const [filePattern, setFilePattern] = useState('')
  const [runMap, setRunMap] = useState<Record<string, string>>({})

  const handleCollect = () => {
    const params: Parameters<typeof collect>[0] = {
      backend,
      output_dir: outputDir,
      subject,
    }
    if (task) params.task = task
    if (sessions) params.sessions = sessions.split(',').map((s) => s.trim()).filter(Boolean)
    if (bidsDir) params.bids_dir = bidsDir
    if (Object.keys(runMap).length > 0) params.run_map = runMap
    if (filePattern) params.backend_params = { file_pattern: filePattern }

    collect(params)
  }

  const canSubmit = backend && outputDir && subject && !collecting

  return (
    <div style={containerStyle}>
      <div style={titleStyle}>Collect Outputs into Manifest</div>

      <div style={fieldRow}>
        <span style={labelStyle}>Backend</span>
        <select style={selectStyle} value={backend} onChange={(e) => setBackend(e.target.value)}>
          <option value="fmriprep">fmriprep</option>
          <option value="custom">custom</option>
          <option value="bids_app">bids_app</option>
        </select>
      </div>

      <div style={fieldRow}>
        <span style={labelStyle}>Output Dir</span>
        <input style={inputStyle} value={outputDir} onChange={(e) => setOutputDir(e.target.value)}
          placeholder="/data/derivatives/fmriprep/" />
      </div>

      <div style={fieldRow}>
        <span style={labelStyle}>Subject</span>
        <input style={inputStyle} value={subject} onChange={(e) => setSubject(e.target.value)}
          placeholder="sub01" />
      </div>

      <div style={fieldRow}>
        <span style={labelStyle}>Task</span>
        <input style={inputStyle} value={task} onChange={(e) => setTask(e.target.value)}
          placeholder="reading (optional)" />
      </div>

      <div style={fieldRow}>
        <span style={labelStyle}>Sessions</span>
        <input style={inputStyle} value={sessions} onChange={(e) => setSessions(e.target.value)}
          placeholder="comma-separated (optional)" />
      </div>

      {backend === 'fmriprep' && (
        <div style={fieldRow}>
          <span style={labelStyle}>BIDS Dir</span>
          <input style={inputStyle} value={bidsDir} onChange={(e) => setBidsDir(e.target.value)}
            placeholder="/data/bids/ (optional)" />
        </div>
      )}

      {backend === 'custom' && (
        <div style={fieldRow}>
          <span style={labelStyle}>File Pattern</span>
          <input style={inputStyle} value={filePattern} onChange={(e) => setFilePattern(e.target.value)}
            placeholder="*.nii.gz" />
        </div>
      )}

      <div style={fieldRow}>
        <span style={labelStyle}>Run Map</span>
        <div style={{ flex: 1 }}>
          <RunMapEditor value={runMap} onChange={setRunMap} />
        </div>
      </div>

      <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
        <button style={btnStyle} onClick={handleCollect} disabled={!canSubmit}>
          {collecting ? 'Collecting...' : 'Collect'}
        </button>
      </div>

      {/* Error */}
      {collectError && (
        <div style={{ marginTop: 16, fontSize: 12, color: 'var(--accent-red)' }}>
          {collectError}
        </div>
      )}

      {/* Result */}
      {collectResult && (
        <>
          <div style={sectionLabel}>Result</div>
          <div style={{ fontSize: 12, color: 'var(--accent-green)', fontWeight: 600, marginBottom: 8 }}>
            {'\u2713'} Manifest created: {collectResult.manifest.runs.length} runs found
          </div>
          {collectResult.manifest.runs.map((run) => (
            <div key={run.run_name} style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>
              {run.run_name}
              {' '}{run.n_trs} TRs
              {' '}<QcBadge label="FD" value={run.qc?.mean_fd ?? null} thresholds={[0.3, 0.5]} suffix="mm" />
            </div>
          ))}
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 8 }}>
            Saved to: {collectResult.manifest_path}
          </div>
          <button
            style={{ ...btnStyle, backgroundColor: 'var(--bg-input)', color: 'var(--text-secondary)', border: '1px solid var(--border)', marginTop: 12, fontSize: 11 }}
            onClick={() => {
              usePreprocStore.setState({ tab: 'manifests' })
              clearCollect()
            }}
          >
            View in Manifests tab
          </button>
        </>
      )}
    </div>
  )
}
