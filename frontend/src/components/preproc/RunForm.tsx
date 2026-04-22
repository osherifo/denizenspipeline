/** Tab 4: Run preprocessing — form + live progress. */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'
import { RunMapEditor } from './RunMapEditor'
import { PreprocProgress } from './PreprocProgress'

// ── Styles ──────────────────────────────────────────────────────────────

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
  width: 130,
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

const sectionHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  cursor: 'pointer',
  userSelect: 'none',
  marginTop: 16,
  marginBottom: 10,
}

const sectionTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const chevron: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  transition: 'transform 0.15s',
}

const sectionBody: CSSProperties = {
  paddingLeft: 4,
}

const modeCard: CSSProperties = {
  padding: '10px 14px',
  border: '1px solid var(--border)',
  borderRadius: 6,
  cursor: 'pointer',
  flex: 1,
  minWidth: 140,
}

const modeCardActive: CSSProperties = {
  ...modeCard,
  borderColor: 'var(--accent-cyan)',
  backgroundColor: 'color-mix(in srgb, var(--accent-cyan) 8%, transparent)',
}

const modeLabel: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-primary)',
  marginBottom: 2,
}

const modeDesc: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  lineHeight: 1.3,
}

const checkRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginBottom: 8,
}

const checkLabel: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-primary)',
}

const warningBox: CSSProperties = {
  fontSize: 11,
  color: 'var(--accent-yellow, #e2a832)',
  backgroundColor: 'color-mix(in srgb, var(--accent-yellow, #e2a832) 8%, transparent)',
  border: '1px solid color-mix(in srgb, var(--accent-yellow, #e2a832) 25%, transparent)',
  borderRadius: 5,
  padding: '8px 12px',
  marginTop: 8,
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

// ── Modes ───────────────────────────────────────────────────────────────

type PreprocMode = 'full' | 'anat_only' | 'func_only' | 'func_precomputed_anat'

const MODES: { value: PreprocMode; label: string; desc: string }[] = [
  { value: 'full', label: 'Full', desc: 'Structural + functional preprocessing' },
  { value: 'anat_only', label: 'Anat Only', desc: 'FreeSurfer reconall, skull stripping, segmentation — no BOLD' },
  { value: 'func_only', label: 'Func Only', desc: 'BOLD preprocessing without FreeSurfer reconall' },
  { value: 'func_precomputed_anat', label: 'Pre-computed Anat', desc: 'Functional using existing FreeSurfer outputs' },
]

// ── Collapsible Section ─────────────────────────────────────────────────

function Section({ title, open, onToggle, children }: {
  title: string
  open: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <>
      <div style={sectionHeader} onClick={onToggle}>
        <span style={{ ...chevron, transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}>&#9654;</span>
        <span style={sectionTitle}>{title}</span>
      </div>
      {open && <div style={sectionBody}>{children}</div>}
    </>
  )
}

// ── Output Space Tags ───────────────────────────────────────────────────

const COMMON_SPACES = [
  'T1w', 'MNI152NLin2009cAsym', 'MNI152NLin6Asym', 'MNI152NLin2009cAsym:res-2',
  'MNI152NLin6Asym:res-2', 'fsaverage', 'fsaverage5', 'fsaverage6', 'fsnative',
]

function SpaceTagInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [input, setInput] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)

  const add = (s: string) => {
    const trimmed = s.trim()
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed])
    }
    setInput('')
    setShowSuggestions(false)
  }

  const remove = (s: string) => onChange(value.filter((v) => v !== s))

  const filtered = COMMON_SPACES.filter(
    (s) => !value.includes(s) && s.toLowerCase().includes(input.toLowerCase()),
  )

  return (
    <div style={{ flex: 1, maxWidth: 420 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 4 }}>
        {value.map((s) => (
          <span
            key={s}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '3px 8px', fontSize: 11, borderRadius: 4,
              backgroundColor: 'var(--bg-input)', border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          >
            {s}
            <span onClick={() => remove(s)} style={{ cursor: 'pointer', opacity: 0.6, fontWeight: 700 }}>x</span>
          </span>
        ))}
      </div>
      <div style={{ position: 'relative' }}>
        <input
          style={{ ...inputStyle, maxWidth: '100%' }}
          value={input}
          onChange={(e) => { setInput(e.target.value); setShowSuggestions(true) }}
          onFocus={() => setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
          onKeyDown={(e) => { if (e.key === 'Enter' && input.trim()) { e.preventDefault(); add(input) } }}
          placeholder="Type a space name..."
        />
        {showSuggestions && filtered.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
            backgroundColor: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 5, maxHeight: 140, overflowY: 'auto',
          }}>
            {filtered.map((s) => (
              <div
                key={s}
                onMouseDown={() => add(s)}
                style={{
                  padding: '6px 12px', fontSize: 12, cursor: 'pointer',
                  color: 'var(--text-primary)',
                }}
              >
                {s}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main Component ──────────────────────────────────────────────────────

export function RunForm() {
  const {
    running, runEvents, runStartTime, runError, configErrors,
    startRun, validateConfig, clearRun,
  } = usePreprocStore()

  // Common
  const [backend, setBackend] = useState('fmriprep')
  const [bidsDir, setBidsDir] = useState('')
  const [rawDir, setRawDir] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [workDir, setWorkDir] = useState('')
  const [subject, setSubject] = useState('')
  const [task, setTask] = useState('')
  const [sessions, setSessions] = useState('')

  // Mode
  const [mode, setMode] = useState<PreprocMode>('full')

  // Container
  const [container, setContainer] = useState('')
  const [containerType, setContainerType] = useState('singularity')

  // Anatomical
  const [skullStrip, setSkullStrip] = useState('auto')
  const [skullStripTemplate, setSkullStripTemplate] = useState('')
  const [noSubmmRecon, setNoSubmmRecon] = useState(false)
  const [fsSubjectsDir, setFsSubjectsDir] = useState('')
  const [fsLicense, setFsLicense] = useState('')

  // Functional
  const [bold2t1wInit, setBold2t1wInit] = useState('')
  const [bold2t1wDof, setBold2t1wDof] = useState('')
  const [dummyScans, setDummyScans] = useState('')
  const [taskId, setTaskId] = useState('')
  const [ignoreFieldmaps, setIgnoreFieldmaps] = useState(false)
  const [ignoreSlicetiming, setIgnoreSlicetiming] = useState(false)
  const [ignoreSbref, setIgnoreSbref] = useState(false)

  // Fieldmaps
  const [useSynSdc, setUseSynSdc] = useState(false)
  const [forceSyn, setForceSyn] = useState(false)
  const [fmapBspline, setFmapBspline] = useState(false)
  const [fmapNoDemean, setFmapNoDemean] = useState(false)

  // Output
  const [outputSpaces, setOutputSpaces] = useState<string[]>(['T1w'])
  const [ciftiOutput, setCiftiOutput] = useState('')
  const [meOutputEchos, setMeOutputEchos] = useState(false)

  // Denoising
  const [useAroma, setUseAroma] = useState(false)
  const [aromaMelodicDim, setAromaMelodicDim] = useState('')
  const [returnAllComponents, setReturnAllComponents] = useState(false)

  // Resources
  const [nthreads, setNthreads] = useState('')
  const [ompNthreads, setOmpNthreads] = useState('')
  const [memMb, setMemMb] = useState('')
  const [lowMem, setLowMem] = useState(false)
  const [stopOnFirstCrash, setStopOnFirstCrash] = useState(false)
  const [skipBidsValidation, setSkipBidsValidation] = useState(false)

  // custom-specific
  const [command, setCommand] = useState('')

  // confounds
  const [confStrategy, setConfStrategy] = useState('')
  const [confHighPass, setConfHighPass] = useState('')

  // run map
  const [runMap, setRunMap] = useState<Record<string, string>>({})

  // extra args
  const [extraArgs, setExtraArgs] = useState('')

  // Section open state
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    paths: true,
    anat: false,
    func: false,
    fieldmaps: false,
    output: false,
    denoising: false,
    resources: false,
    confounds: false,
    runmap: false,
    advanced: false,
  })

  const toggle = (key: string) =>
    setOpenSections((s) => ({ ...s, [key]: !s[key] }))

  const isFmriprep = backend === 'fmriprep'
  const isAnatOnly = mode === 'anat_only'
  const showFunc = isFmriprep && !isAnatOnly
  const showAnat = isFmriprep && mode !== 'func_only'

  // AROMA space warning
  const aromaWarning = useAroma && !outputSpaces.some((s) => s.startsWith('MNI152NLin6Asym'))

  const buildParams = () => {
    const backendParams: Record<string, unknown> = {}

    if (isFmriprep) {
      backendParams.mode = mode

      // Container
      if (container) backendParams.container = container
      if (containerType) backendParams.container_type = containerType

      // Anat
      if (skullStrip !== 'auto') backendParams.skull_strip = skullStrip
      if (skullStripTemplate) backendParams.skull_strip_template = skullStripTemplate
      if (noSubmmRecon) backendParams.no_submm_recon = true
      if (fsSubjectsDir) backendParams.fs_subjects_dir = fsSubjectsDir
      if (fsLicense) backendParams.fs_license_file = fsLicense

      // Func
      if (bold2t1wInit) backendParams.bold2t1w_init = bold2t1wInit
      if (bold2t1wDof) backendParams.bold2t1w_dof = parseInt(bold2t1wDof, 10)
      if (dummyScans) backendParams.dummy_scans = parseInt(dummyScans, 10)
      if (taskId) backendParams.task_id = taskId
      const ignore: string[] = []
      if (ignoreFieldmaps) ignore.push('fieldmaps')
      if (ignoreSlicetiming) ignore.push('slicetiming')
      if (ignoreSbref) ignore.push('sbref')
      if (ignore.length > 0) backendParams.ignore = ignore

      // Fieldmaps
      if (useSynSdc) backendParams.use_syn_sdc = true
      if (forceSyn) backendParams.force_syn = true
      if (fmapBspline) backendParams.fmap_bspline = true
      if (fmapNoDemean) backendParams.fmap_no_demean = true

      // Output
      if (outputSpaces.length > 0) backendParams.output_spaces = outputSpaces
      if (ciftiOutput) backendParams.cifti_output = ciftiOutput
      if (meOutputEchos) backendParams.me_output_echos = true

      // Denoising
      if (useAroma) backendParams.use_aroma = true
      if (aromaMelodicDim) backendParams.aroma_melodic_dim = parseInt(aromaMelodicDim, 10)
      if (returnAllComponents) backendParams.return_all_components = true

      // Resources
      if (nthreads) backendParams.nthreads = parseInt(nthreads, 10)
      if (ompNthreads) backendParams.omp_nthreads = parseInt(ompNthreads, 10)
      if (memMb) backendParams.mem_mb = parseInt(memMb, 10)
      if (lowMem) backendParams.low_mem = true
      if (stopOnFirstCrash) backendParams.stop_on_first_crash = true
      if (skipBidsValidation) backendParams.skip_bids_validation = true

      // Extra args
      if (extraArgs.trim()) backendParams.extra_args = extraArgs.trim()
    } else if (backend === 'bids_app') {
      if (container) backendParams.container = container
      if (containerType) backendParams.container_type = containerType
    } else if (backend === 'custom') {
      if (command) backendParams.command = command
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

  const handleValidate = () => validateConfig(buildParams() as any)
  const handleRun = () => startRun(buildParams() as any)

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

        {/* Mode selector — fmriprep only */}
        {isFmriprep && (
          <>
            <div style={{ ...sectionTitle, marginTop: 12, marginBottom: 10 }}>Preprocessing Mode</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
              {MODES.map((m) => (
                <div
                  key={m.value}
                  style={mode === m.value ? modeCardActive : modeCard}
                  onClick={() => setMode(m.value)}
                >
                  <div style={modeLabel}>{m.label}</div>
                  <div style={modeDesc}>{m.desc}</div>
                </div>
              ))}
            </div>
          </>
        )}

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

        {/* ── Paths section (fmriprep / bids_app) ── */}
        {(isFmriprep || backend === 'bids_app') && (
          <Section title="Paths & Container" open={openSections.paths} onToggle={() => toggle('paths')}>
            <div style={fieldRow}>
              <span style={labelStyle}>BIDS Dir</span>
              <input style={inputStyle} value={bidsDir} onChange={(e) => setBidsDir(e.target.value)} placeholder="/data/bids/" />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Container</span>
              <input style={inputStyle} value={container} onChange={(e) => setContainer(e.target.value)} placeholder="/images/fmriprep-24.0.0.sif" />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Container Type</span>
              <select style={selectStyle} value={containerType} onChange={(e) => setContainerType(e.target.value)}>
                <option value="singularity">singularity</option>
                <option value="docker">docker</option>
                <option value="bare">bare</option>
              </select>
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Work Dir</span>
              <input style={inputStyle} value={workDir} onChange={(e) => setWorkDir(e.target.value)} placeholder="/tmp/work (optional)" />
            </div>
          </Section>
        )}

        {/* ── Custom backend fields ── */}
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

        {/* ── Anatomical options ── */}
        {showAnat && (
          <Section title="Anatomical" open={openSections.anat} onToggle={() => toggle('anat')}>
            <div style={fieldRow}>
              <span style={labelStyle}>Skull Strip</span>
              <select style={selectStyle} value={skullStrip} onChange={(e) => setSkullStrip(e.target.value)}>
                <option value="auto">auto</option>
                <option value="force">force</option>
                <option value="skip">skip</option>
              </select>
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Skull Strip Template</span>
              <input style={inputStyle} value={skullStripTemplate} onChange={(e) => setSkullStripTemplate(e.target.value)} placeholder="OASIS30ANTs (optional)" />
            </div>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={noSubmmRecon} onChange={(e) => setNoSubmmRecon(e.target.checked)} />
              <span style={checkLabel}>Disable sub-millimeter reconstruction</span>
            </div>
            {mode === 'func_precomputed_anat' && (
              <div style={fieldRow}>
                <span style={labelStyle}>FS Subjects Dir</span>
                <input style={inputStyle} value={fsSubjectsDir} onChange={(e) => setFsSubjectsDir(e.target.value)} placeholder="/data/derivatives/freesurfer/" />
              </div>
            )}
            <div style={fieldRow}>
              <span style={labelStyle}>FS License</span>
              <input style={inputStyle} value={fsLicense} onChange={(e) => setFsLicense(e.target.value)} placeholder="~/.freesurfer/license.txt" />
            </div>
          </Section>
        )}

        {/* ── Functional options ── */}
        {showFunc && (
          <Section title="Functional" open={openSections.func} onToggle={() => toggle('func')}>
            <div style={fieldRow}>
              <span style={labelStyle}>BOLD-to-T1w Init</span>
              <select style={selectStyle} value={bold2t1wInit} onChange={(e) => setBold2t1wInit(e.target.value)}>
                <option value="">default</option>
                <option value="register">register</option>
                <option value="header">header</option>
              </select>
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>BOLD-to-T1w DOF</span>
              <select style={selectStyle} value={bold2t1wDof} onChange={(e) => setBold2t1wDof(e.target.value)}>
                <option value="">default</option>
                <option value="6">6</option>
                <option value="9">9</option>
                <option value="12">12</option>
              </select>
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Dummy Scans</span>
              <input style={{ ...inputStyle, maxWidth: 100 }} type="number" min={0} value={dummyScans}
                onChange={(e) => setDummyScans(e.target.value)} placeholder="0" />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Task ID</span>
              <input style={inputStyle} value={taskId} onChange={(e) => setTaskId(e.target.value)} placeholder="Filter to task (optional)" />
            </div>
            <div style={{ marginTop: 8, marginBottom: 4 }}>
              <span style={{ ...labelStyle, width: 'auto', textAlign: 'left', display: 'block', marginBottom: 6 }}>Skip corrections:</span>
              <div style={{ display: 'flex', gap: 16, paddingLeft: 4 }}>
                <label style={checkRow}>
                  <input type="checkbox" checked={ignoreFieldmaps} onChange={(e) => setIgnoreFieldmaps(e.target.checked)} />
                  <span style={checkLabel}>fieldmaps</span>
                </label>
                <label style={checkRow}>
                  <input type="checkbox" checked={ignoreSlicetiming} onChange={(e) => setIgnoreSlicetiming(e.target.checked)} />
                  <span style={checkLabel}>slicetiming</span>
                </label>
                <label style={checkRow}>
                  <input type="checkbox" checked={ignoreSbref} onChange={(e) => setIgnoreSbref(e.target.checked)} />
                  <span style={checkLabel}>sbref</span>
                </label>
              </div>
            </div>
          </Section>
        )}

        {/* ── Fieldmaps ── */}
        {showFunc && (
          <Section title="Fieldmaps / SDC" open={openSections.fieldmaps} onToggle={() => toggle('fieldmaps')}>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={useSynSdc} onChange={(e) => setUseSynSdc(e.target.checked)} />
              <span style={checkLabel}>Use fieldmap-less SDC (SyN)</span>
            </div>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={forceSyn} onChange={(e) => setForceSyn(e.target.checked)} />
              <span style={checkLabel}>Force SyN even if fieldmaps exist</span>
            </div>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={fmapBspline} onChange={(e) => setFmapBspline(e.target.checked)} />
              <span style={checkLabel}>B-spline interpolation for fieldmaps</span>
            </div>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={fmapNoDemean} onChange={(e) => setFmapNoDemean(e.target.checked)} />
              <span style={checkLabel}>Skip demean of phase-diff fieldmap</span>
            </div>
          </Section>
        )}

        {/* ── Output ── */}
        {isFmriprep && (
          <Section title="Output" open={openSections.output} onToggle={() => toggle('output')}>
            <div style={fieldRow}>
              <span style={labelStyle}>Output Spaces</span>
              <SpaceTagInput value={outputSpaces} onChange={setOutputSpaces} />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>CIFTI Output</span>
              <select style={selectStyle} value={ciftiOutput} onChange={(e) => setCiftiOutput(e.target.value)}>
                <option value="">none</option>
                <option value="91k">91k</option>
                <option value="170k">170k</option>
              </select>
            </div>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={meOutputEchos} onChange={(e) => setMeOutputEchos(e.target.checked)} />
              <span style={checkLabel}>Write individual echo outputs (multi-echo)</span>
            </div>
          </Section>
        )}

        {/* ── Denoising ── */}
        {showFunc && (
          <Section title="Denoising (ICA-AROMA)" open={openSections.denoising} onToggle={() => toggle('denoising')}>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={useAroma} onChange={(e) => setUseAroma(e.target.checked)} />
              <span style={checkLabel}>Enable ICA-AROMA</span>
            </div>
            {aromaWarning && (
              <div style={warningBox}>
                ICA-AROMA requires <strong>MNI152NLin6Asym:res-2</strong> in output spaces. Add it to avoid a runtime error.
              </div>
            )}
            {useAroma && (
              <>
                <div style={fieldRow}>
                  <span style={labelStyle}>MELODIC dim</span>
                  <input style={{ ...inputStyle, maxWidth: 100 }} type="number" value={aromaMelodicDim}
                    onChange={(e) => setAromaMelodicDim(e.target.value)} placeholder="-200" />
                </div>
                <div style={checkRow}>
                  <span style={labelStyle} />
                  <input type="checkbox" checked={returnAllComponents} onChange={(e) => setReturnAllComponents(e.target.checked)} />
                  <span style={checkLabel}>Return all ICA components</span>
                </div>
              </>
            )}
          </Section>
        )}

        {/* ── Resources ── */}
        {isFmriprep && (
          <Section title="Resources" open={openSections.resources} onToggle={() => toggle('resources')}>
            <div style={fieldRow}>
              <span style={labelStyle}>Threads</span>
              <input style={{ ...inputStyle, maxWidth: 100 }} type="number" min={1} value={nthreads}
                onChange={(e) => setNthreads(e.target.value)} placeholder="auto" />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>OMP Threads</span>
              <input style={{ ...inputStyle, maxWidth: 100 }} type="number" min={1} value={ompNthreads}
                onChange={(e) => setOmpNthreads(e.target.value)} placeholder="auto" />
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Memory (MB)</span>
              <input style={{ ...inputStyle, maxWidth: 120 }} type="number" min={1} value={memMb}
                onChange={(e) => setMemMb(e.target.value)} placeholder="auto" />
            </div>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={lowMem} onChange={(e) => setLowMem(e.target.checked)} />
              <span style={checkLabel}>Low memory mode</span>
            </div>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={stopOnFirstCrash} onChange={(e) => setStopOnFirstCrash(e.target.checked)} />
              <span style={checkLabel}>Stop on first crash</span>
            </div>
          </Section>
        )}

        {/* ── Confounds (existing) ── */}
        {showFunc && (
          <Section title="Confounds" open={openSections.confounds} onToggle={() => toggle('confounds')}>
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
                <input style={{ ...inputStyle, maxWidth: 120 }} value={confHighPass}
                  onChange={(e) => setConfHighPass(e.target.value)} placeholder="0.01" />
              </div>
            )}
          </Section>
        )}

        {/* ── Run Map ── */}
        {showFunc && (
          <Section title="Run Map" open={openSections.runmap} onToggle={() => toggle('runmap')}>
            <RunMapEditor value={runMap} onChange={setRunMap} />
          </Section>
        )}

        {/* ── Advanced ── */}
        {isFmriprep && (
          <Section title="Advanced" open={openSections.advanced} onToggle={() => toggle('advanced')}>
            <div style={checkRow}>
              <span style={labelStyle} />
              <input type="checkbox" checked={skipBidsValidation}
                onChange={(e) => setSkipBidsValidation(e.target.checked)} />
              <span style={checkLabel}>Skip BIDS validation (--skip-bids-validation)</span>
            </div>
            <div style={fieldRow}>
              <span style={labelStyle}>Extra Args</span>
              <input style={{ ...inputStyle, maxWidth: 500 }} value={extraArgs}
                onChange={(e) => setExtraArgs(e.target.value)}
                placeholder="--flag1 --flag2 value (raw CLI flags)" />
            </div>
          </Section>
        )}

        {/* ── Actions ── */}
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
                <div key={i} style={{
                  fontSize: 12, marginBottom: 3,
                  color: e.startsWith('Warning:') ? 'var(--accent-yellow, #e2a832)' : 'var(--accent-red)',
                }}>
                  {e.startsWith('Warning:') ? '\u26A0' : '\u2717'} {e}
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
