/** Import an existing nipype pipeline .py from a server-side path as a composite node. */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { importPipelineFile } from '../../api/preproc'
import { usePreprocPipelineStore } from '../../stores/preproc-pipeline-store'

const backdrop: CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }
const card: CSSProperties = { width: 'min(640px, 94vw)', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: 16, fontSize: 12 }
const input: CSSProperties = { width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit', marginBottom: 8 }
const btn: CSSProperties = { padding: '6px 12px', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-primary)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12 }

export function ImportPipelineModal({ onClose }: { onClose: () => void }) {
  const [path, setPath] = useState('')
  const [name, setName] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const loadLibrary = usePreprocPipelineStore((s) => s.loadLibrary)

  const run = async () => {
    setBusy(true); setResult(null)
    try {
      const r = await importPipelineFile(path, name || undefined)
      setResult(`Imported as composite node "${r.node}" (${r.shape}). Inputs: ${r.inputs.join(', ') || '—'}; outputs: ${r.outputs.join(', ') || '—'}.${r.warnings.length ? ' ' + r.warnings.join(' ') : ''}\n${r.path}`)
      await loadLibrary()
    } catch (e) {
      setResult((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <b style={{ fontSize: 13 }}>Import a nipype pipeline</b>
        <p style={{ color: 'var(--text-secondary)', margin: '6px 0 10px' }}>
          Give the path (on the server) to a <code>.py</code> file that either defines a <code>build(config)</code> function returning a
          nipype <code>Workflow</code>, exposes a module-level <code>Workflow</code>, or already registers a node. It becomes a
          <b> composite</b> node whose ports are the workflow's <code>inputnode</code> / <code>outputnode</code> fields.
        </p>
        <input style={input} placeholder="/path/to/my_pipeline.py" value={path} onChange={(e) => setPath(e.target.value)} />
        <input style={input} placeholder="node name (optional, default: file stem)" value={name} onChange={(e) => setName(e.target.value)} />
        {result && <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, color: 'var(--text-secondary)', margin: '0 0 10px' }}>{result}</pre>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button style={btn} onClick={onClose}>Close</button>
          <button style={{ ...btn, borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }} disabled={!path || busy} onClick={run}>{busy ? 'Importing…' : 'Import'}</button>
        </div>
      </div>
    </div>
  )
}
