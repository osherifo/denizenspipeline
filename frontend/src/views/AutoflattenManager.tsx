/** Autoflatten Manager — standalone view for cortical surface flattening. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { useAutoflattenStore } from '../stores/autoflatten-store'
import { AutoflattenProgress } from '../components/autoflatten/AutoflattenProgress'
import { FlatmapPreview } from '../components/autoflatten/FlatmapPreview'
import { AutoflattenConfigBrowser } from '../components/autoflatten/AutoflattenConfigBrowser'
import { fetchAutoflattenVisualizations } from '../api/client'

const tabBarStyle: CSSProperties = {
  display: 'flex', gap: 4, marginBottom: 16,
}
const tabStyle = (active: boolean): CSSProperties => ({
  padding: '8px 20px', fontSize: 12, fontWeight: 600,
  fontFamily: 'inherit',
  border: active ? '1px solid var(--accent-cyan)' : '1px solid var(--border)',
  borderRadius: 6, cursor: 'pointer',
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
  letterSpacing: 0.5, textTransform: 'uppercase',
})
const card: CSSProperties = {
  backgroundColor: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 8, padding: '20px 24px', marginBottom: 16,
}
const cardTitle: CSSProperties = {
  fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 16,
}
const fieldRow: CSSProperties = {
  display: 'flex', alignItems: 'center', marginBottom: 12, gap: 12,
}
const label: CSSProperties = {
  fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
  width: 130, textAlign: 'right', flexShrink: 0,
}
const input: CSSProperties = {
  padding: '8px 12px', fontSize: 12, fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)', border: '1px solid var(--border)',
  borderRadius: 5, color: 'var(--text-primary)', flex: 1, maxWidth: 400,
}
const select: CSSProperties = { ...input, appearance: 'auto' as const, maxWidth: 200 }
const checkRow: CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }
const checkLabel: CSSProperties = { fontSize: 12, color: 'var(--text-primary)' }
const btnPrimary: CSSProperties = {
  padding: '8px 24px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
  borderRadius: 6, cursor: 'pointer', border: 'none',
  backgroundColor: 'var(--accent-cyan)', color: '#000',
}
const btnSecondary: CSSProperties = {
  padding: '8px 24px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
  borderRadius: 6, cursor: 'pointer',
  border: '1px solid var(--border)', backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}
const statusDot = (ok: boolean): CSSProperties => ({
  display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
  backgroundColor: ok ? 'var(--accent-green)' : 'var(--accent-red)',
  marginRight: 8,
})
const resultBox: CSSProperties = {
  fontSize: 12, padding: '12px 16px', borderRadius: 6,
  backgroundColor: 'var(--bg-input)', border: '1px solid var(--border)',
  marginTop: 12,
}

const TABS = [
  { key: 'status' as const, label: 'Status' },
  { key: 'configs' as const, label: 'Configs' },
  { key: 'run' as const, label: 'Run / Flatten' },
  { key: 'import' as const, label: 'Import' },
]

/** Resolve flatmap PNGs: use the result's visualizations if present,
 *  otherwise scan the subject's surf/ dir on disk. */
function useResolvedVisualizations(
  runVisualizations: Record<string, string> | undefined,
  subjectsDir: string,
  subject: string,
): Record<string, string> {
  const [scanned, setScanned] = useState<Record<string, string>>({})

  useEffect(() => {
    const hasRunViz = runVisualizations && Object.keys(runVisualizations).length > 0
    if (hasRunViz || !subjectsDir || !subject) {
      setScanned({})
      return
    }
    fetchAutoflattenVisualizations(subjectsDir, subject)
      .then((r) => setScanned(r.images))
      .catch(() => setScanned({}))
  }, [runVisualizations, subjectsDir, subject])

  const hasRunViz = runVisualizations && Object.keys(runVisualizations).length > 0
  return hasRunViz ? runVisualizations! : scanned
}

// ── Status Tab ──────────────────────────────────────────────────────────

function StatusTab() {
  const { tools, toolsLoading, loadTools, subjectStatus, statusLoading, statusError, checkStatus, clearStatus } = useAutoflattenStore()
  const [subjectsDir, setSubjectsDir] = useState('')
  const [subject, setSubject] = useState('')

  useEffect(() => { loadTools() }, [])

  const previewImages = useResolvedVisualizations(
    undefined,
    subjectStatus?.subject_dir_exists ? subjectsDir : '',
    subjectStatus?.subject ?? '',
  )

  const handleCheck = () => {
    if (subjectsDir && subject) checkStatus(subjectsDir, subject)
  }

  return (
    <>
      {/* Tool availability */}
      <div style={card}>
        <div style={cardTitle}>Tool Availability</div>
        {toolsLoading ? (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Loading...</div>
        ) : (
          tools.map((t) => (
            <div key={t.name} style={{ fontSize: 12, marginBottom: 6 }}>
              <span style={statusDot(t.available)} />
              <strong>{t.name}</strong> — {t.detail}
            </div>
          ))
        )}
      </div>

      {/* Subject check */}
      <div style={card}>
        <div style={cardTitle}>Subject Status</div>
        <div style={fieldRow}>
          <span style={label}>Subjects Dir</span>
          <input style={input} value={subjectsDir} onChange={(e) => setSubjectsDir(e.target.value)}
            placeholder="/data/derivatives/freesurfer" />
        </div>
        <div style={fieldRow}>
          <span style={label}>Subject</span>
          <input style={input} value={subject} onChange={(e) => setSubject(e.target.value)}
            placeholder="sub-sub01" />
        </div>
        <button style={btnPrimary} onClick={handleCheck} disabled={!subjectsDir || !subject || statusLoading}>
          {statusLoading ? 'Checking...' : 'Check'}
        </button>

        {statusError && (
          <div style={{ ...resultBox, color: 'var(--accent-red)' }}>{statusError}</div>
        )}

        {subjectStatus && (
          <div style={resultBox}>
            <div style={{ marginBottom: 8 }}>
              <span style={statusDot(subjectStatus.subject_dir_exists)} />
              Subject directory: {subjectStatus.subject_dir_exists ? 'exists' : 'NOT FOUND'}
            </div>
            <div style={{ marginBottom: 8 }}>
              <span style={statusDot(subjectStatus.has_surfaces)} />
              FreeSurfer surfaces: {subjectStatus.has_surfaces ? 'OK' : 'missing'}
            </div>
            <div style={{ marginBottom: 8 }}>
              <span style={statusDot(subjectStatus.has_flat_patches)} />
              Flat patches: {subjectStatus.has_flat_patches
                ? `found (${Object.values(subjectStatus.flat_patches).map((p) => p.split('/').pop()).join(', ')})`
                : 'not found'}
            </div>
            <div style={{ marginBottom: 8 }}>
              <span style={statusDot(subjectStatus.pycortex_surface !== null)} />
              pycortex surface: {subjectStatus.pycortex_surface || 'not registered'}
            </div>

            <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-secondary)' }}>
              {!subjectStatus.has_surfaces
                ? 'Run FreeSurfer reconall first (fmriflow preproc run --mode anat_only)'
                : !subjectStatus.has_flat_patches
                  ? 'Ready for flattening — switch to the "Run / Flatten" tab'
                  : !subjectStatus.pycortex_surface
                    ? 'Flat patches found — switch to "Import" to register in pycortex'
                    : 'All set — surfaces, flatmaps, and pycortex are configured'}
            </div>
          </div>
        )}

        {subjectStatus?.has_flat_patches && (
          <FlatmapPreview images={previewImages} patches={subjectStatus.flat_patches} />
        )}
      </div>
    </>
  )
}

// ── Run Tab ─────────────────────────────────────────────────────────────

function RunTab() {
  const { running, runResult, runError, runEvents, runStartTime, startRun, clearRun } = useAutoflattenStore()

  const [subjectsDir, setSubjectsDir] = useState('')
  const [subject, setSubject] = useState('')
  const [backend, setBackend] = useState('pyflatten')
  const [hemispheres, setHemispheres] = useState('both')
  const [overwrite, setOverwrite] = useState(false)
  const [importPycortex, setImportPycortex] = useState(true)
  const [pycortexSurface, setPycortexSurface] = useState('')

  const previewImages = useResolvedVisualizations(
    runResult?.visualizations,
    subjectsDir,
    runResult?.subject ?? subject,
  )

  const handleRun = () => {
    const params: Record<string, unknown> = {
      subjects_dir: subjectsDir,
      subject,
      backend,
      hemispheres,
      overwrite,
      import_to_pycortex: importPycortex,
    }
    if (pycortexSurface.trim()) params.pycortex_surface_name = pycortexSurface.trim()
    startRun(params as any)
  }

  return (
    <div style={card}>
      <div style={cardTitle}>Run Autoflatten</div>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 16 }}>
        Flatten FreeSurfer surfaces into flatmaps. Skips automatically if flat patches already exist (unless overwrite is checked).
      </div>
      <div style={fieldRow}>
        <span style={label}>Subjects Dir</span>
        <input style={input} value={subjectsDir} onChange={(e) => setSubjectsDir(e.target.value)}
          placeholder="/data/derivatives/freesurfer" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Subject</span>
        <input style={input} value={subject} onChange={(e) => setSubject(e.target.value)}
          placeholder="sub-sub01" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Backend</span>
        <select style={select} value={backend} onChange={(e) => setBackend(e.target.value)}>
          <option value="pyflatten">pyflatten (JAX)</option>
          <option value="freesurfer">freesurfer</option>
        </select>
      </div>
      <div style={fieldRow}>
        <span style={label}>Hemispheres</span>
        <select style={select} value={hemispheres} onChange={(e) => setHemispheres(e.target.value)}>
          <option value="both">both</option>
          <option value="lh">lh only</option>
          <option value="rh">rh only</option>
        </select>
      </div>
      <div style={checkRow}>
        <span style={label} />
        <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
        <span style={checkLabel}>Overwrite existing flat patches</span>
      </div>
      <div style={checkRow}>
        <span style={label} />
        <input type="checkbox" checked={importPycortex} onChange={(e) => setImportPycortex(e.target.checked)} />
        <span style={checkLabel}>Import into pycortex after flattening</span>
      </div>
      {importPycortex && (
        <div style={fieldRow}>
          <span style={label}>Surface name</span>
          <input style={input} value={pycortexSurface} onChange={(e) => setPycortexSurface(e.target.value)}
            placeholder={`${subject || 'sub-sub01'}fs (auto)`} />
        </div>
      )}

      <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
        <button style={btnPrimary} onClick={handleRun} disabled={!subjectsDir || !subject || running}>
          {running ? 'Running...' : 'Run'}
        </button>
      </div>

      {(running || runEvents.length > 0 || runError) && (
        <AutoflattenProgress
          events={runEvents}
          startTime={runStartTime}
          running={running}
          error={runError}
          onDismiss={clearRun}
        />
      )}

      {runResult && !running && (
        <>
          <div style={resultBox}>
            <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--accent-green)' }}>
              Summary
            </div>
            <div>Subject: {runResult.subject}</div>
            <div>Source: {runResult.source}</div>
            <div>Hemispheres: {runResult.hemispheres.join(', ')}</div>
            {Object.entries(runResult.flat_patches).map(([h, p]) => (
              <div key={h}>{h} patch: {p}</div>
            ))}
            {runResult.pycortex_surface && <div>pycortex: {runResult.pycortex_surface}</div>}
            <div>Elapsed: {runResult.elapsed_s.toFixed(1)}s</div>
          </div>
          <FlatmapPreview images={previewImages} patches={runResult.flat_patches} />
        </>
      )}
    </div>
  )
}

// ── Import Tab ──────────────────────────────────────────────────────────

function ImportTab() {
  const { running, runResult, runError, runEvents, runStartTime, startRun, clearRun } = useAutoflattenStore()

  const [subjectsDir, setSubjectsDir] = useState('')
  const [subject, setSubject] = useState('')
  const [flatPatchLh, setFlatPatchLh] = useState('')
  const [flatPatchRh, setFlatPatchRh] = useState('')
  const [pycortexSurface, setPycortexSurface] = useState('')

  const previewImages = useResolvedVisualizations(
    runResult?.visualizations,
    subjectsDir,
    runResult?.subject ?? subject,
  )

  const handleImport = () => {
    startRun({
      subjects_dir: subjectsDir,
      subject,
      flat_patch_lh: flatPatchLh,
      flat_patch_rh: flatPatchRh,
      import_to_pycortex: true,
      pycortex_surface_name: pycortexSurface.trim() || undefined,
    })
  }

  return (
    <div style={card}>
      <div style={cardTitle}>Import Pre-computed Flat Patches</div>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 16 }}>
        Import existing flat patches (from manual flattening, a prior autoflatten run, or another tool) into pycortex.
        Skips the flattening step entirely.
      </div>
      <div style={fieldRow}>
        <span style={label}>Subjects Dir</span>
        <input style={input} value={subjectsDir} onChange={(e) => setSubjectsDir(e.target.value)}
          placeholder="/data/derivatives/freesurfer" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Subject</span>
        <input style={input} value={subject} onChange={(e) => setSubject(e.target.value)}
          placeholder="sub-sub01" />
      </div>
      <div style={fieldRow}>
        <span style={label}>LH Flat Patch</span>
        <input style={input} value={flatPatchLh} onChange={(e) => setFlatPatchLh(e.target.value)}
          placeholder="/path/to/lh.full.flat.patch.3d" />
      </div>
      <div style={fieldRow}>
        <span style={label}>RH Flat Patch</span>
        <input style={input} value={flatPatchRh} onChange={(e) => setFlatPatchRh(e.target.value)}
          placeholder="/path/to/rh.full.flat.patch.3d" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Surface name</span>
        <input style={input} value={pycortexSurface} onChange={(e) => setPycortexSurface(e.target.value)}
          placeholder={`${subject || 'sub-sub01'}fs (auto)`} />
      </div>

      <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
        <button style={btnPrimary} onClick={handleImport}
          disabled={!subjectsDir || !subject || !flatPatchLh || !flatPatchRh || running}>
          {running ? 'Importing...' : 'Import'}
        </button>
      </div>

      {(running || runEvents.length > 0 || runError) && (
        <AutoflattenProgress
          events={runEvents}
          startTime={runStartTime}
          running={running}
          error={runError}
          onDismiss={clearRun}
        />
      )}

      {runResult && !running && (
        <>
          <div style={resultBox}>
            <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--accent-green)' }}>
              Summary
            </div>
            <div>Source: {runResult.source}</div>
            {runResult.pycortex_surface && <div>pycortex surface: {runResult.pycortex_surface}</div>}
          </div>
          <FlatmapPreview images={previewImages} patches={runResult.flat_patches} />
        </>
      )}
    </div>
  )
}

// ── Main View ───────────────────────────────────────────────────────────

export function AutoflattenManager() {
  const { tab, setTab } = useAutoflattenStore()

  return (
    <div>
      <div style={tabBarStyle}>
        {TABS.map((t) => (
          <button key={t.key} style={tabStyle(tab === t.key)} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'status' && <StatusTab />}
      {tab === 'configs' && <AutoflattenConfigBrowser />}
      {tab === 'run' && <RunTab />}
      {tab === 'import' && <ImportTab />}
    </div>
  )
}
