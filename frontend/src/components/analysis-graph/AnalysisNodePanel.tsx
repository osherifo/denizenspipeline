/** Side panel for the selected analysis node: its ports and what feeds them, its params,
 *  and the editors some node types need (preparation steps, extra section keys). */
import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import { ParamForm } from '../composer/ParamForm'
import { useAnalysisGraphStore } from '../../stores/analysis-graph-store'
import { useModuleStore } from '../../stores/module-store'
import type { AnalysisGraphNodeDoc, AnalysisNodeInfo, ParamSchema } from '../../api/types'
import { CATEGORY_COLORS, CATEGORY_LABELS, PORT_TYPE_COLORS, categoryOf } from './describe'
import { YamlField } from './YamlField'

/** Reserved param holding section keys a module reads but does not declare. */
export const SECTION_PARAM = '_section'

const panel: CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 12,
  fontSize: 12, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto',
}
const h: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', margin: '4px 0' }
const small: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)' }
const iconBtn: CSSProperties = {
  background: 'transparent', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-secondary)',
  cursor: 'pointer', fontSize: 10, padding: '0 5px', fontFamily: 'inherit',
}
const input: CSSProperties = {
  flex: 1, minWidth: 0, boxSizing: 'border-box', padding: '4px 6px', borderRadius: 4, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit',
}
const dot = (color: string): CSSProperties => ({ width: 8, height: 8, borderRadius: 999, background: color, display: 'inline-block', flexShrink: 0 })

interface Step { name: string; params?: Record<string, unknown> }

function StepsEditor({ steps, onChange }: { steps: Step[]; onChange: (steps: Step[]) => void }) {
  const modules = useModuleStore((s) => s.modules)
  const names = useMemo(() => (modules['preparation_steps'] ?? []).map((m) => m.name), [modules])
  const update = (i: number, patch: Partial<Step>) => onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const move = (i: number, d: -1 | 1) => {
    const next = [...steps]
    if (i + d < 0 || i + d >= next.length) return
    ;[next[i], next[i + d]] = [next[i + d], next[i]]
    onChange(next)
  }
  return (
    <div>
      <div style={h}>Preparation steps</div>
      <datalist id="analysis-prep-steps">{names.map((n) => <option key={n} value={n} />)}</datalist>
      {steps.length === 0 && <div style={small}>no steps yet</div>}
      {steps.map((step, i) => (
        <div key={i} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 6, marginBottom: 6 }}>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 4 }}>
            <span style={small}>{i + 1}.</span>
            <input style={input} list="analysis-prep-steps" placeholder="step name" value={step.name}
              onChange={(e) => update(i, { name: e.target.value })} />
            <button style={iconBtn} title="move up" onClick={() => move(i, -1)}>▲</button>
            <button style={iconBtn} title="move down" onClick={() => move(i, 1)}>▼</button>
            <button style={iconBtn} title="remove step" onClick={() => onChange(steps.filter((_, j) => j !== i))}>✕</button>
          </div>
          <YamlField value={step.params ?? {}} rows={2} placeholder="params as YAML, e.g. delays: [1, 2, 3, 4]"
            onChange={(v) => update(i, { params: v as Record<string, unknown> })} />
        </div>
      ))}
      <button style={{ ...iconBtn, padding: '3px 8px', fontSize: 11 }} onClick={() => onChange([...steps, { name: '', params: {} }])}>+ step</button>
    </div>
  )
}

interface Props {
  node: AnalysisGraphNodeDoc
  info: AnalysisNodeInfo | undefined
}

export function AnalysisNodePanel({ node, info }: Props) {
  const graph = useAnalysisGraphStore((s) => s.graph)
  const updateNodeParams = useAnalysisGraphStore((s) => s.updateNodeParams)
  const removeNode = useAnalysisGraphStore((s) => s.removeNode)
  const removeEdge = useAnalysisGraphStore((s) => s.removeEdge)
  const moveEdge = useAnalysisGraphStore((s) => s.moveEdge)
  const category = categoryOf(node.type)
  const color = CATEGORY_COLORS[category] ?? '#9ca3af'
  const isPipelinePreparer = node.type === 'preparer:pipeline'
  const params = node.data.params ?? {}

  const schema = useMemo(() => {
    const out: ParamSchema = {}
    for (const [k, f] of Object.entries(info?.params_schema ?? {})) {
      if (k === SECTION_PARAM || (isPipelinePreparer && k === 'steps')) continue
      out[k] = f
    }
    return out
  }, [info, isPipelinePreparer])

  const setParam = (key: string, value: unknown) => updateNodeParams(node.id, { ...params, [key]: value })

  return (
    <div style={panel}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color }}>{CATEGORY_LABELS[category] ?? category}</span>
        <span style={{ fontWeight: 700, fontSize: 13, flex: 1, overflowWrap: 'anywhere' }}>{node.id}</span>
        <button onClick={() => removeNode(node.id)} title="remove node" style={{ ...iconBtn, padding: '3px 8px' }}>✕</button>
      </div>
      <div style={small}>{node.type}</div>
      {!info && <div style={{ color: 'var(--accent-red)' }}>This node type is not in the catalog. Check the module name or load its add-on.</div>}
      {info?.description && <div style={{ color: 'var(--text-secondary)' }}>{info.description}</div>}
      {info?.error_policy === 'isolate' && <div style={small}>A failure here is recorded and the run continues.</div>}

      {info && Object.keys(info.inputs).length > 0 && (
        <div>
          <div style={h}>Inputs</div>
          {Object.entries(info.inputs).map(([port, spec]) => {
            const feeds = graph.edges.filter((e) => e.target === node.id && e.targetHandle === port)
            return (
              <div key={port} style={{ marginBottom: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={dot(PORT_TYPE_COLORS[spec.type ?? 'any'] ?? '#9ca3af')} />
                  <b>{port}{spec.required ? ' *' : ''}</b>
                  <span style={small}>{spec.type ?? 'any'}{spec.multiple ? ' · several, in order' : ''}</span>
                </div>
                {feeds.length === 0 && (
                  <div style={{ ...small, marginLeft: 14, color: spec.required ? 'var(--accent-red)' : undefined }}>not connected</div>
                )}
                {feeds.map((e, i) => (
                  <div key={e.id} style={{ display: 'flex', gap: 4, alignItems: 'center', marginLeft: 14 }}>
                    <span style={{ flex: 1, overflowWrap: 'anywhere' }}>← {e.source}.{e.sourceHandle}</span>
                    {spec.multiple && feeds.length > 1 && (
                      <>
                        <button style={iconBtn} title="earlier" disabled={i === 0} onClick={() => moveEdge(e.id, -1)}>▲</button>
                        <button style={iconBtn} title="later" disabled={i === feeds.length - 1} onClick={() => moveEdge(e.id, 1)}>▼</button>
                      </>
                    )}
                    <button style={iconBtn} title="disconnect" onClick={() => removeEdge(e.id)}>✕</button>
                  </div>
                ))}
                {spec.multiple && feeds.length > 1 && node.type === 'utility:bundle_features' && (
                  <div style={{ ...small, marginLeft: 14 }}>feature matrix columns follow this order</div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {info && Object.keys(info.outputs).length > 0 && (
        <div>
          <div style={h}>Outputs</div>
          {Object.entries(info.outputs).map(([port, spec]) => {
            const n = graph.edges.filter((e) => e.source === node.id && e.sourceHandle === port).length
            return (
              <div key={port} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                <span style={dot(PORT_TYPE_COLORS[spec.type ?? 'any'] ?? '#9ca3af')} />
                <b>{port}</b>
                <span style={small}>{spec.type ?? 'any'} · {n} connection{n === 1 ? '' : 's'}</span>
              </div>
            )
          })}
        </div>
      )}

      <div>
        <div style={h}>Parameters</div>
        <ParamForm schema={schema} values={params} onChange={setParam} />
      </div>

      {isPipelinePreparer && (
        <StepsEditor steps={(params.steps as Step[] | undefined) ?? []} onChange={(steps) => setParam('steps', steps)} />
      )}

      <div>
        <div style={h}>Extra section keys</div>
        <div style={small}>Keys this module reads from its config section but does not declare, as YAML.</div>
        <YamlField value={params[SECTION_PARAM] ?? {}} rows={2}
          onChange={(v) => {
            const next = { ...params }
            if (Object.keys(v).length === 0) delete next[SECTION_PARAM]
            else next[SECTION_PARAM] = v
            updateNodeParams(node.id, next)
          }} />
      </div>
    </div>
  )
}
