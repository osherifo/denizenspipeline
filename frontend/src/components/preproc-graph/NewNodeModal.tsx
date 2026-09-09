/** Author a new node in-app: pick a kind, edit the scaffold in Monaco, save to addons/nodes. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { CodeEditor } from '../editor/CodeEditor'
import { fetchNodeScaffold, saveNodeCode } from '../../api/preproc'
import { usePreprocPipelineStore } from '../../stores/preproc-pipeline-store'
import type { PreprocNodeKind } from '../../api/types'
import { KIND_LABELS } from './PipelineNodeCard'

const backdrop: CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }
const card: CSSProperties = { width: 'min(1000px, 94vw)', height: 'min(760px, 90vh)', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, display: 'flex', flexDirection: 'column', overflow: 'hidden' }
const input: CSSProperties = { padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit' }
const btn: CSSProperties = { ...input, cursor: 'pointer' }

interface Props {
  onClose: () => void
  initialCode?: string
  initialName?: string
}

export function NewNodeModal({ onClose, initialCode, initialName }: Props) {
  const [kind, setKind] = useState<PreprocNodeKind>('interface')
  const [name, setName] = useState(initialName ?? 'my_node')
  const [code, setCode] = useState(initialCode ?? '')
  const [status, setStatus] = useState<string | null>(null)
  const loadLibrary = usePreprocPipelineStore((s) => s.loadLibrary)

  useEffect(() => {
    if (initialCode) return
    fetchNodeScaffold(kind).then((r) => setCode(r.code)).catch((e) => setStatus((e as Error).message))
  }, [kind, initialCode])

  const save = async () => {
    setStatus('saving…')
    try {
      const r = await saveNodeCode(name, code.replace(/my_node|my_workflow|my_app/g, name))
      setStatus(`saved ${r.path}`)
      await loadLibrary()
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: 10, borderBottom: '1px solid var(--border)', fontSize: 12 }}>
          <b>New node</b>
          <select style={input} value={kind} onChange={(e) => setKind(e.target.value as PreprocNodeKind)} disabled={Boolean(initialCode)}>
            {(['interface', 'composite', 'container_app'] as PreprocNodeKind[]).map((k) => <option key={k} value={k}>{KIND_LABELS[k]} ({k})</option>)}
          </select>
          <input style={{ ...input, width: 200 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="node name" />
          <span style={{ color: 'var(--text-secondary)' }}>→ $FMRIFLOW_HOME/addons/nodes/{name}.py</span>
          <span style={{ flex: 1 }} />
          {status && <span style={{ color: 'var(--text-secondary)' }}>{status}</span>}
          <button style={btn} onClick={save}>Save + rescan</button>
          <button style={btn} onClick={onClose}>Close</button>
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <CodeEditor code={code} onChange={setCode} />
        </div>
      </div>
    </div>
  )
}
