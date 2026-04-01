/** Tab 4: Run preprocessing — form + live progress. */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'
import { RunMapEditor } from './RunMapEditor'
import { PreprocProgress } from './PreprocProgress'

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
  maxWidth: 200,
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
  color: '#000',
}

const secondaryBtn: CSSProperties = {
  ...btnStyle,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}

export function RunForm() {
  const {
    running, runEvents, runStartTime, runError, configErrors,
    startRun, validateConfig, clearRun,
  } = usePreprocStore()

  const [backend, setBackend] = useState('fmriprep')
  const [bidsDir, setBidsDir] = useState('')
  const [rawDir, setRawDir] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [workDir, setWorkDir] = useState('')
  const [subject, setSubject] = useState('')
  const [task, setTask] = useState('')
  const [sessions, setSessions] = useState('')

  // fmriprep-specific
  const [container, setContainer] = useState('')
  const [containerType, setContainerType] = useState('singularity')
  const [fsLicense, setFsLicense] = useState('')
  const [outputSpaces, setOutputSpaces] = useState('T1w')

  // custom-specific
  const [command, setCommand] = useState('')

  // confounds
  const [confStrategy, setConfStrategy] = useState('')
  const [confHighPass, setConfHighPass] = useState('')

  // run map
  const [runMap, setRunMap] = useState<Record<string, string>>({})

  const buildParams = () => {
    const backendParams: Record<string, unknown> = {}
    if (backend === 'fmriprep' || backend === 'bids_app') {
      if (container) backendParams.container = container
      if (containerType) backendParams.container_type = containerType
      if (fsLicense) backendParams.fs_license_file = fsLicense
      if (outputSpaces) backendParams.output_spaces = outputSpaces.split(',').map((s) => s.trim()).filter(Boolean)
    }
    if (backend === 'custom' && command) {
      backendParams.command = command
    }

    const params: Record<string, unknown> = {
      backend,
      output_dir: outputDir,
      subject,
    }
    if (bidsDir) params.bids_dir = bidsDir
    if (rawDir) params.raw_dir = rawDir
    if (workDir) params.work_dir = workDir
    if (task) params.task = task
    if (sessions) params.sessions = sessions.split(',').map((s) => s.trim()).filter(Boolean)
    if (Object.keys(backendParams).length > 0) params.backend_params = backendParams
    if (Object.keys(runMap).length > 0) params.run_map = runMap
    if (confStrategy) {
      const confounds: Record<string, unknown> = { strategy: confStrategy }
      if (confHighPass) confounds.high_pass = parseFloat(confHighPass)
      params.confounds = confounds
    }

    return params
  }

  const handleValidate = () => {
    validateConfig(buildParams() as any)
  }

  const handleRun = () => {
    startRun(buildParams() as any)
  }

  const canSubmit = backend && outputDir && subject && !running

  const hasProgress = runEvents.length > 0 || running || runError

  return (
    <div>
      <div style={containerStyle}>
        <div style={titleStyle}>Run Preprocessing</div>

        {/* Backend */}
        <div style={fieldRow}>
          <span style={labelStyle}>Backend</span>
          <select style={selectStyle} value={backend} onChange={(e) => setBackend(e.target.value)}>
            <option value="fmriprep">fmriprep</option>
            <option value="custom">custom</option>
            <option value="bids_app">bids_app</option>
          </select>
        </div>

        {/* Common fields */}
        <div style={fieldRow}>
          <span style={labelStyle}>Subject</span>
          <input style={inputStyle} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="sub01" />
        </div>
        <div style={fieldRow}>
          <span style={labelStyle}>Output Dir</span>
          <input style={inputStyle} value={outputDir} onChange={(e) => setOutputDir(e.target.value)} placeholder="/data/derivatives/fmriprep/" />
        </div>
        <div style={fieldRow}>
          <span style={labelStyle}>Task</span>
          <input style={inputStyle} value={task} onChange={(e) => setTask(e.target.value)} placeholder="reading (optional)" />
        </div>
        <div style={fieldRow}>
          <span style={labelStyle}>Sessions</span>
          <input style={inputStyle} value={sessions} onChange={(e) => setSessions(e.target.value)} placeholder="comma-separated (optional)" />
        </div>

        {/* fmriprep / bids_app fields */}
        {(backend === 'fmriprep' || backend === 'bids_app') && (
          <>
            <div style={fieldRow}>
              <span style={labelStyle}>BIDS Dir</span>
              <input style={inputStyle} value={bidsDir} onChange={(e) => setBidsDir(e.target.value)} placeholder="/data/bids/" />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Container</span>
              <input style={inputStyle} value={container} onChange={(e) => setContainer(e.target.value)} placeholder="/images/fmriprep-23.2.1.sif" />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Container Type</span>
              <select style={selectStyle} value={containerType} onChange={(e) => setContainerType(e.target.value)}>
                <option value="singularity">singularity</option>
                <option value="docker">docker</option>
                <option value="bare">bare</option>
              </select>
            </div>
            {backend === 'fmriprep' && (
              <>
                <div style={fieldRow}>
                  <span style={labelStyle}>FS License</span>
                  <input style={inputStyle} value={fsLicense} onChange={(e) => setFsLicense(e.target.value)} placeholder="~/.freesurfer/license.txt" />
                </div>
                <div style={fieldRow}>
                  <span style={labelStyle}>Output Spaces</span>
                  <input style={inputStyle} value={outputSpaces} onChange={(e) => setOutputSpaces(e.target.value)} placeholder="T1w, MNI152NLin2009cAsym" />
                </div>
              </>
            )}
            <div style={fieldRow}>
              <span style={labelStyle}>Work Dir</span>
              <input style={inputStyle} value={workDir} onChange={(e) => setWorkDir(e.target.value)} placeholder="/tmp/work (optional)" />
            </div>
          </>
        )}

        {/* custom fields */}
        {backend === 'custom' && (
          <>
            <div style={fieldRow}>
              <span style={labelStyle}>Raw Dir</span>
              <input style={inputStyle} value={rawDir} onChange={(e) => setRawDir(e.target.value)} placeholder="/data/raw/" />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Command</span>
              <input style={{ ...inputStyle, maxWidth: 500 }} value={command} onChange={(e) => setCommand(e.target.value)}
                placeholder="python preproc.py --subject {subject} --input {input_dir} --output {output_dir}" />
            </div>
          </>
        )}

        {/* Confounds */}
        <div style={sectionTitle}>Confounds (optional)</div>
        <div style={fieldRow}>
          <span style={labelStyle}>Strategy</span>
          <select style={selectStyle} value={confStrategy} onChange={(e) => setConfStrategy(e.target.value)}>
            <option value="">None</option>
            <option value="motion_24">motion_24</option>
            <option value="motion_6">motion_6</option>
            <option value="acompcor">acompcor</option>
          </select>
        </div>
        {confStrategy && (
          <div style={fieldRow}>
            <span style={labelStyle}>High-pass (Hz)</span>
            <input style={{ ...inputStyle, maxWidth: 120 }} value={confHighPass} onChange={(e) => setConfHighPass(e.target.value)} placeholder="0.01" />
          </div>
        )}

        {/* Run map */}
        <div style={sectionTitle}>Run Map (optional)</div>
        <div style={{ marginLeft: 122 }}>
          <RunMapEditor value={runMap} onChange={setRunMap} />
        </div>

        {/* Actions */}
        <div style={{ marginTop: 20, display: 'flex', gap: 12 }}>
          <button style={secondaryBtn} onClick={handleValidate} disabled={!canSubmit}>
            Validate
          </button>
          <button style={primaryBtn} onClick={handleRun} disabled={!canSubmit}>
            {running ? 'Running...' : 'Run'}
          </button>
        </div>

        {/* Validation errors */}
        {configErrors && (
          <div style={{ marginTop: 12 }}>
            {configErrors.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--accent-green)', fontWeight: 600 }}>
                {'\u2713'} Config is valid
              </div>
            ) : (
              configErrors.map((e, i) => (
                <div key={i} style={{ fontSize: 12, color: 'var(--accent-red)', marginBottom: 3 }}>
                  {'\u2717'} {e}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Live progress */}
      {hasProgress && (
        <PreprocProgress
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
