/** Graph-level settings, shown when no node is selected: graph inputs and globals. */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { formatInputValue, useAnalysisGraphStore } from '../../stores/analysis-graph-store'
import { YamlField } from './YamlField'

const INPUT_KINDS = ['str', 'dir', 'file', 'list', 'int', 'float', 'bool']

const panel: CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 12,
  fontSize: 12, display: 'flex', flexDirection: 'column', gap: 8,
}
const h: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', margin: '4px 0 0' }
const small: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)' }
const input: CSSProperties = {
  minWidth: 0, boxSizing: 'border-box', padding: '4px 6px', borderRadius: 4, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit',
}
const btn: CSSProperties = { ...input, cursor: 'pointer' }

export function GraphSettingsPanel() {
  const graph = useAnalysisGraphStore((s) => s.graph)
  const setInput = useAnalysisGraphStore((s) => s.setInput)
  const setMeta = useAnalysisGraphStore((s) => s.setMeta)
  const [newName, setNewName] = useState('')
  const validName = /^[A-Za-z_][A-Za-z0-9_]*$/.test(newName) && !(newName in graph.inputs)

  return (
    <div style={panel}>
      <div style={small}>Select a node to edit it. Graph settings:</div>
      <div style={small}>scope {graph.scope} · {graph.nodes.length} nodes · {graph.edges.length} edges</div>

      <div style={h}>Inputs</div>
      <div style={small}>Values given at run time. Use one as <code>$inputs.name</code> in params or globals.</div>
      {Object.entries(graph.inputs).map(([name, spec]) => (
        <div key={name} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 6 }}>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <code style={{ flex: 1, overflowWrap: 'anywhere' }} title={spec.description}>{name}</code>
            <select style={input} value={spec.kind ?? 'str'} onChange={(e) => setInput(name, { ...spec, kind: e.target.value })}>
              {INPUT_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
            <button style={btn} title={`remove input ${name}`} onClick={() => setInput(name, null)}>✕</button>
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4 }}>
            <label style={{ ...small, display: 'flex', gap: 4, alignItems: 'center' }}>
              <input type="checkbox" checked={spec.required !== false} onChange={(e) => setInput(name, { ...spec, required: e.target.checked })} />
              required
            </label>
            <input style={{ ...input, flex: 1 }} placeholder="default" value={formatInputValue(spec.default)}
              onChange={(e) => setInput(name, { ...spec, default: e.target.value === '' ? undefined : e.target.value })} />
          </div>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 4 }}>
        <input style={{ ...input, flex: 1 }} placeholder="new input name" value={newName} onChange={(e) => setNewName(e.target.value)} />
        <button style={{ ...btn, opacity: validName ? 1 : 0.5 }} disabled={!validName}
          onClick={() => { setInput(newName, { kind: /dir$/.test(newName) ? 'dir' : 'str' }); setNewName('') }}>+ input</button>
      </div>

      <div style={h}>Globals</div>
      <div style={small}>Run-level config every node's config is built from: experiment, subject, subject_config, reporting.output_dir.</div>
      <YamlField value={graph.globals} rows={8} onChange={(v) => setMeta({ globals: v as Record<string, unknown> })} />
    </div>
  )
}
