/** Input values for a run, the Run button, and the live node status of the last run. */
import type { CSSProperties } from 'react'
import { PathField } from '../common/PathPicker'
import { useAnalysisGraphStore } from '../../stores/analysis-graph-store'

const panel: CSSProperties = { border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 12, fontSize: 12 }
const row: CSSProperties = { display: 'grid', gridTemplateColumns: '110px 1fr', gap: 8, alignItems: 'center', marginBottom: 6 }
const input: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit',
}
const primary: CSSProperties = {
  padding: '8px 18px', borderRadius: 6, border: 'none', background: 'var(--accent-cyan)', color: 'var(--on-accent)',
  fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
}
const note: CSSProperties = { fontSize: 10, color: 'var(--text-secondary)', marginBottom: 8 }

export function AnalysisRunPanel() {
  const graph = useAnalysisGraphStore((s) => s.graph)
  const inputValues = useAnalysisGraphStore((s) => s.inputValues)
  const setInputValue = useAnalysisGraphStore((s) => s.setInputValue)
  const launch = useAnalysisGraphStore((s) => s.launch)
  const launching = useAnalysisGraphStore((s) => s.launching)
  const lastRunId = useAnalysisGraphStore((s) => s.lastRunId)
  const runState = useAnalysisGraphStore((s) => s.runState)
  const runStatus = useAnalysisGraphStore((s) => s.runStatus)
  const subjectStatus = useAnalysisGraphStore((s) => s.subjectStatus)
  const validation = useAnalysisGraphStore((s) => s.validation)
  const error = useAnalysisGraphStore((s) => s.error)

  const names = Object.keys(graph.inputs)
  const needsValue = (name: string) => {
    const spec = graph.inputs[name]
    return spec.required !== false && spec.default === undefined
  }
  const missing = names.filter((n) => needsValue(n) && !(inputValues[n] ?? '').trim())
  const runnable = graph.nodes.length > 0 && !launching && missing.length === 0
  const subjectCounts: Record<string, number> = {}
  for (const st of Object.values(subjectStatus)) subjectCounts[st] = (subjectCounts[st] ?? 0) + 1
  const counts: Record<string, number> = {}
  for (const st of Object.values(runStatus)) counts[st.status ?? 'pending'] = (counts[st.status ?? 'pending'] ?? 0) + 1

  return (
    <div style={panel}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 2 }}>Run</div>
      <div style={note}>input values are saved with the graph (Save above)</div>
      {names.length === 0 && <div style={note}>this graph declares no inputs</div>}
      {names.map((name) => {
        const spec = graph.inputs[name]
        const kind = spec.kind ?? 'str'
        const value = inputValues[name] ?? ''
        return (
          <div key={name} style={row}>
            <label title={spec.description} style={{ overflowWrap: 'anywhere' }}>{name}{needsValue(name) ? ' *' : ''}</label>
            {kind === 'dir' || kind === 'file' ? (
              <PathField style={input} compact mode={kind === 'dir' ? 'dir' : 'file'} placeholder={spec.description ?? kind}
                value={value} onChange={(v) => setInputValue(name, v)} />
            ) : (
              <input style={input} placeholder={kind === 'list' ? '[run01, run02]' : (spec.description ?? kind)}
                value={value} onChange={(e) => setInputValue(name, e.target.value)} />
            )}
          </div>
        )
      })}
      {missing.length > 0 && <div style={note}>needs a value: {missing.join(', ')}</div>}
      {validation && !validation.ok && (
        <div style={{ color: 'var(--accent-red)', marginBottom: 8 }}>
          {validation.errors.map((e, i) => <div key={i}>• {e}</div>)}
        </div>
      )}
      {error && <div style={{ color: 'var(--accent-red)', marginBottom: 8 }}>{error}</div>}
      <button style={{ ...primary, opacity: runnable ? 1 : 0.5 }} disabled={!runnable} onClick={() => void launch()}>
        {launching ? 'Launching…' : `▶ Run ${graph.scope} graph`}
      </button>
      {lastRunId && (
        <div style={{ marginTop: 10, fontSize: 11 }}>
          run <code>{lastRunId}</code> · {runState}
          {Object.entries(counts).map(([k, v]) => <span key={k} style={{ marginLeft: 8 }}>{k} {v}</span>)}
          {Object.keys(subjectCounts).length > 0 && (
            <div style={{ marginTop: 4 }}>subjects: {Object.entries(subjectCounts).map(([k, v]) => `${v} ${k}`).join(', ')}</div>
          )}
          <a href={graph.scope === 'subject' ? '#runs' : `#${graph.scope}-runs`} style={{ marginLeft: 8, color: 'var(--accent-cyan)' }}>open in {graph.scope === 'subject' ? 'Runs' : `${graph.scope[0].toUpperCase()}${graph.scope.slice(1)} Runs`}</a>
        </div>
      )}
    </div>
  )
}
