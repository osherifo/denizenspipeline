/** Side panel for the selected pipeline node: grouped parameters, input bindings,
 *  literal inputs, iteration and its manifest role. */
import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { ParamForm } from '../composer/ParamForm'
import { PathField } from '../common/PathPicker'
import { NodeChecksSection } from './checks/NodeChecksSection'
import { usePreprocPipelineStore } from '../../stores/preproc-pipeline-store'
import type { ParamSchema, PipelineNodeDoc, PreprocNodeInfo } from '../../api/types'
import { KIND_COLORS, KIND_LABELS } from './PipelineNodeCard'
import { formatIterLiteral, parseIterLiteral } from './iter-literal'

/** Port kinds that name something on disk (everything but scalars and `any`). */
const isPathKind = (kind: string) => !['str', 'int', 'float', 'bool', 'any', 'list'].includes(kind)

const panel: CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 12,
  fontSize: 12, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto',
}
const h: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', margin: '4px 0' }
const row: CSSProperties = { display: 'grid', gridTemplateColumns: '90px 1fr', gap: 8, alignItems: 'center', marginBottom: 6 }
const input: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit',
}
const groupBtn = (open: boolean): CSSProperties => ({
  width: '100%', textAlign: 'left', background: 'transparent', border: '1px solid var(--border)', borderRadius: 4,
  padding: '5px 8px', color: 'var(--text-primary)', fontSize: 11, fontWeight: 600, cursor: 'pointer', marginBottom: open ? 6 : 4,
})

function groupSchema(schema: ParamSchema & Record<string, { group?: string }>): Record<string, ParamSchema> {
  const groups: Record<string, ParamSchema> = {}
  for (const [k, f] of Object.entries(schema)) {
    const g = (f as { group?: string }).group ?? 'Parameters'
    ;(groups[g] ??= {})[k] = f
  }
  return groups
}

interface Props {
  node: PipelineNodeDoc
  info: PreprocNodeInfo | undefined
}

export function NodeParamPanel({ node, info }: Props) {
  const pipeline = usePreprocPipelineStore((s) => s.pipeline)
  const updateNodeParams = usePreprocPipelineStore((s) => s.updateNodeParams)
  const updateNodeData = usePreprocPipelineStore((s) => s.updateNodeData)
  const setPipelineMeta = usePreprocPipelineStore((s) => s.setPipelineMeta)
  const removeNode = usePreprocPipelineStore((s) => s.removeNode)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})

  const groups = useMemo(() => groupSchema((info?.params_schema ?? {}) as ParamSchema), [info])
  const groupNames = Object.keys(groups)
  const inputs = Object.entries(info?.inputs ?? {})
  const outputs = Object.keys(info?.outputs ?? {})
  const fedByEdge = new Set(pipeline.edges.filter((e) => e.target === node.id).map((e) => e.targetHandle))
  const pipelineInputs = Object.keys(pipeline.inputs ?? {})
  const isBackend = pipeline.manifest?.backend_node === node.id
  const iterHandles = node.data.iter?.handles ?? (node.data.iter?.handle ? [node.data.iter.handle] : [])
  const kind = node.kind ?? info?.kind ?? 'interface'

  const onParam = (key: string, value: unknown) => updateNodeParams(node.id, { ...node.data.params, [key]: value })

  const setBinding = (port: string, value: string) => {
    const bindings = { ...(node.data.bindings ?? {}) }
    const literal = { ...(node.data.literal_inputs ?? {}) }
    if (value.startsWith('$inputs.')) { bindings[port] = value; delete literal[port] }
    else if (value === '') { delete bindings[port]; delete literal[port] }
    // On an iterated port the literal is the list to iterate over, one item per iteration.
    else { literal[port] = iterHandles.includes(port) ? parseIterLiteral(value) : value; delete bindings[port] }
    updateNodeData(node.id, { bindings, literal_inputs: literal })
  }

  const toggleIter = (port: string) => {
    const on = !iterHandles.includes(port)
    const next = on ? [...iterHandles, port] : iterHandles.filter((h) => h !== port)
    const literal = { ...(node.data.literal_inputs ?? {}) }
    // A literal on the port changes shape with the toggle: list while iterated, text otherwise.
    if (port in literal && !fedByEdge.has(port)) {
      literal[port] = on ? parseIterLiteral(formatIterLiteral(literal[port])) : formatIterLiteral(literal[port])
    }
    updateNodeData(node.id, { iter: next.length ? (next.length === 1 ? { handle: next[0] } : { handles: next }) : null, literal_inputs: literal })
  }

  return (
    <div style={panel}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color: KIND_COLORS[kind] }}>{KIND_LABELS[kind]}</span>
        <span style={{ fontWeight: 700, fontSize: 13, flex: 1 }}>{node.id}</span>
        <span style={{ color: 'var(--text-secondary)' }}>{node.type}</span>
        <button onClick={() => removeNode(node.id)} title="remove node" style={{ ...input, width: 'auto', cursor: 'pointer', padding: '3px 8px' }}>✕</button>
      </div>
      {info?.description && <div style={{ color: 'var(--text-secondary)' }}>{info.description}</div>}

      {inputs.length > 0 && (
        <div>
          <div style={h}>Inputs</div>
          {inputs.map(([port, spec]) => {
            const edge = fedByEdge.has(port)
            const iterated = iterHandles.includes(port)
            const value = node.data.bindings?.[port] ?? formatIterLiteral(node.data.literal_inputs?.[port])
            return (
              <div key={port} style={row}>
                <label title={spec.description} style={{ color: 'var(--text-primary)' }}>
                  {port}{spec.required ? ' *' : ''}
                </label>
                {edge ? (
                  <span style={{ color: 'var(--text-secondary)' }}>← connected</span>
                ) : (
                  <div style={{ display: 'flex', gap: 4 }}>
                    {isPathKind(spec.kind) ? (
                      <PathField
                        list={`inputs-${node.id}-${port}`}
                        style={input}
                        compact
                        mode={spec.kind === 'dir' ? 'dir' : 'file'}
                        checkExists={!String(value).startsWith('$inputs.')}
                        placeholder="path, or $inputs.<name>"
                        value={String(value)}
                        onChange={(v) => setBinding(port, v)}
                      />
                    ) : (
                      <input
                        list={`inputs-${node.id}-${port}`}
                        style={input}
                        placeholder={iterated ? 'one item per iteration: 0, 1, 2' : `${spec.kind}, or $inputs.<name>`}
                        title={iterated ? 'a list to iterate over, comma-separated or JSON' : undefined}
                        value={String(value)}
                        onChange={(e) => setBinding(port, e.target.value)}
                      />
                    )}
                    <datalist id={`inputs-${node.id}-${port}`}>
                      {pipelineInputs.map((n) => <option key={n} value={`$inputs.${n}`} />)}
                    </datalist>
                    {spec.kind !== 'str' && spec.kind !== 'int' && spec.kind !== 'float' && spec.kind !== 'bool' && kind !== 'composite' && (
                      <button
                        title="iterate over a list arriving on this port"
                        onClick={() => toggleIter(port)}
                        style={{ ...input, width: 'auto', cursor: 'pointer', padding: '3px 6px', color: iterHandles.includes(port) ? 'var(--accent-cyan)' : 'var(--text-secondary)' }}
                      >×N</button>
                    )}
                  </div>
                )}
              </div>
            )
          })}
          {inputs.some(([p]) => fedByEdge.has(p)) && kind !== 'composite' && (
            <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
              Iterate (×N) over: {inputs.filter(([p]) => fedByEdge.has(p)).map(([p]) => (
                <button key={p} onClick={() => toggleIter(p)} style={{ ...input, width: 'auto', display: 'inline-block', marginRight: 4, padding: '2px 6px', cursor: 'pointer', color: iterHandles.includes(p) ? 'var(--accent-cyan)' : 'var(--text-secondary)' }}>{p}</button>
              ))}
            </div>
          )}
        </div>
      )}

      {groupNames.length > 0 && (
        <div>
          <div style={h}>Parameters</div>
          {groupNames.length === 1 ? (
            <ParamForm schema={groups[groupNames[0]]} values={node.data.params} onChange={onParam} />
          ) : groupNames.map((g, i) => {
            const open = openGroups[g] ?? i === 0
            return (
              <div key={g}>
                <button style={groupBtn(open)} onClick={() => setOpenGroups({ ...openGroups, [g]: !open })}>
                  {open ? '▾' : '▸'} {g}
                </button>
                {open && <ParamForm schema={groups[g]} values={node.data.params} onChange={onParam} />}
              </div>
            )
          })}
        </div>
      )}

      <NodeChecksSection node={node} />

      <div>
        <div style={h}>Manifest role</div>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 4 }}>
          <input type="checkbox" checked={isBackend} onChange={(e) => setPipelineMeta({ manifest: { ...pipeline.manifest, backend_node: e.target.checked ? node.id : undefined } })} />
          backend node (its outputs define the manifest)
        </label>
        {outputs.length > 0 && (
          <div style={row}>
            <label>bold from</label>
            <select style={input} value={pipeline.manifest?.bold_from?.startsWith(`${node.id}.`) ? pipeline.manifest.bold_from : ''}
              onChange={(e) => setPipelineMeta({ manifest: { ...pipeline.manifest, bold_from: e.target.value || undefined } })}>
              <option value="">—</option>
              {outputs.map((o) => <option key={o} value={`${node.id}.${o}`}>{`${node.id}.${o}`}</option>)}
            </select>
          </div>
        )}
      </div>

      {info && (info.required_tools.length > 0 || info.required_env.length > 0 || info.container_bound) && (
        <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
          needs {[...info.required_tools, ...info.required_env.map((e) => `$${e}`)].join(', ') || 'a container runtime'}
        </div>
      )}
    </div>
  )
}
