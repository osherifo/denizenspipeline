/** The graph as YAML: edit and apply it, or copy it out. */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { dump, load } from 'js-yaml'
import { useAnalysisGraphStore } from '../../stores/analysis-graph-store'
import type { AnalysisGraphDoc } from '../../api/types'

const area: CSSProperties = {
  width: '100%', height: 480, boxSizing: 'border-box', padding: 10, borderRadius: 8, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'monospace', resize: 'vertical',
}
const btn: CSSProperties = {
  padding: '5px 12px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)',
  color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer',
}

/** A parsed YAML document as a graph, or an error message. */
export function graphFromYaml(text: string): AnalysisGraphDoc | string {
  let raw: unknown
  try { raw = load(text) } catch (e) { return (e as Error).message.split('\n')[0] }
  if (raw && typeof raw === 'object' && 'graph' in raw && !('nodes' in raw)) raw = (raw as { graph: unknown }).graph
  const doc = raw as Partial<AnalysisGraphDoc> | null
  if (!doc || typeof doc !== 'object' || !Array.isArray(doc.nodes) || !Array.isArray(doc.edges)) {
    return 'a graph needs a nodes list and an edges list'
  }
  return {
    ...doc,
    name: doc.name ?? 'untitled',
    scope: doc.scope ?? 'subject',
    inputs: doc.inputs ?? {},
    globals: doc.globals ?? {},
    nodes: doc.nodes.map((n) => ({ ...n, data: { ...(n.data ?? {}), params: n.data?.params ?? {} }, position: n.position ?? { x: 0, y: 0 } })),
    edges: doc.edges,
  }
}

export function GraphYamlTab() {
  const graph = useAnalysisGraphStore((s) => s.graph)
  const setGraph = useAnalysisGraphStore((s) => s.setGraph)
  const current = useMemo(() => dump(graph, { noRefs: true, lineWidth: 120 }), [graph])
  const [text, setText] = useState(current)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { setText(current); setError(null) }, [current])

  const apply = () => {
    const doc = graphFromYaml(text)
    if (typeof doc === 'string') { setError(doc); return }
    setError(null)
    setGraph(doc)
  }

  return (
    <div>
      <textarea style={area} spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
        <button style={{ ...btn, borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }} onClick={apply} disabled={text === current}>Apply</button>
        <button style={btn} onClick={() => { setText(current); setError(null) }} disabled={text === current}>Revert</button>
        <button style={btn} onClick={() => void navigator.clipboard?.writeText(text)}>Copy</button>
        {error && <span style={{ color: 'var(--accent-red)', fontSize: 12 }}>{error}</span>}
      </div>
    </div>
  )
}
