/** PostPreprocBuilder — compose a post-fmriprep nipype-style graph. */

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
} from '@xyflow/react'
import type {
  Edge,
  Node,
  NodeChange,
  EdgeChange,
  Connection,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import Editor from '@monaco-editor/react'
import { NipypeNode } from '../components/post_preproc/NipypeNode'
import {
  fetchNipypeNodes,
  validateGraph,
  startRun,
  getRun,
  fetchWorkflows,
  fetchWorkflow,
  saveWorkflow,
  deleteWorkflow,
} from '../api/post-preproc'
import {
  fetchModuleCode,
  saveModuleCode,
  reloadModule,
} from '../api/client'
import type {
  NipypeNodeMeta,
  PostPreprocGraph,
  PostPreprocRunHandle,
  PostPreprocWorkflowSummary,
  PostPreprocWorkflow,
} from '../api/types'

const nodeTypes = { nipype: NipypeNode }

const sectionLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginBottom: 8,
}

const btn: CSSProperties = {
  padding: '6px 12px',
  fontSize: 12,
  fontWeight: 600,
  borderRadius: 4,
  border: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
}

const primaryBtn: CSSProperties = {
  ...btn,
  background: 'var(--accent-cyan)',
  color: '#000',
  border: 'none',
}

const modalBackdrop: CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.6)',
  zIndex: 100,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}

const modalCard: CSSProperties = {
  width: 460,
  maxHeight: '70vh',
  overflowY: 'auto',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: 16,
}

const inputStyle: CSSProperties = {
  padding: '6px 8px',
  fontSize: 12,
  border: '1px solid var(--border)',
  borderRadius: 4,
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  width: '100%',
  boxSizing: 'border-box',
}

let nodeCounter = 1
const nextId = () => `n${nodeCounter++}`

// (legacy color helper removed; see components/post_preproc/NipypeNode.tsx)

function defaultsForNode(meta: NipypeNodeMeta): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(meta.params)) {
    if (v && typeof v === 'object' && 'default' in v) out[k] = v.default
  }
  return out
}

export function PostPreprocBuilder() {
  return (
    <ReactFlowProvider>
      <Inner />
    </ReactFlowProvider>
  )
}

function Inner() {
  const [palette, setPalette] = useState<NipypeNodeMeta[]>([])
  const [nodes, setNodes] = useState<Node[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [subject, setSubject] = useState('')
  const [sourceManifest, setSourceManifest] = useState('')
  const [outputDir, setOutputDir] = useState('./testing/post_preproc')
  const [validation, setValidation] = useState<string[] | null>(null)
  const [run, setRun] = useState<PostPreprocRunHandle | null>(null)
  const [runErr, setRunErr] = useState<string | null>(null)
  const [codeOpen, setCodeOpen] = useState(false)
  const [codeText, setCodeText] = useState('')
  const [codePath, setCodePath] = useState('')
  const [codeStatus, setCodeStatus] = useState<string | null>(null)
  const [codeBusy, setCodeBusy] = useState(false)

  const [workflows, setWorkflows] = useState<PostPreprocWorkflowSummary[]>([])
  const [showSubworkflowPicker, setShowSubworkflowPicker] = useState(false)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [showLoadPicker, setShowLoadPicker] = useState(false)
  const [workflowName, setWorkflowName] = useState('')
  const [workflowDesc, setWorkflowDesc] = useState('')

  const refreshWorkflows = useCallback(() => {
    fetchWorkflows().then(setWorkflows).catch((e) => console.warn(e))
  }, [])

  useEffect(() => {
    fetchNipypeNodes().then(setPalette).catch((e) => console.error(e))
    refreshWorkflows()
  }, [refreshWorkflows])

  // Poll active run.
  useEffect(() => {
    if (!run || run.status === 'done' || run.status === 'failed') return
    const t = setInterval(async () => {
      try {
        const r = await getRun(run.run_id)
        setRun(r as PostPreprocRunHandle)
        if (r.status === 'failed' && r.error) setRunErr(r.error)
      } catch (e) {
        console.warn(e)
      }
    }, 1500)
    return () => clearInterval(t)
  }, [run])

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((n) => applyNodeChanges(changes, n)),
    [],
  )
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((e) => applyEdgeChanges(changes, e)),
    [],
  )
  const onConnect = useCallback(
    (c: Connection) =>
      setEdges((e) =>
        addEdge(
          {
            ...c,
            id: `e-${c.source}-${c.target}-${Date.now()}`,
            sourceHandle: c.sourceHandle ?? 'out_file',
            targetHandle: c.targetHandle ?? 'in_file',
          },
          e,
        ),
      ),
    [],
  )

  const addNode = (meta: NipypeNodeMeta) => {
    const id = nextId()
    setNodes((prev) => [
      ...prev,
      {
        id,
        type: 'nipype',
        data: {
          label: `${meta.name} (${id})`,
          nodeType: meta.name,
          inputs: meta.inputs,
          outputs: meta.outputs,
          params: defaultsForNode(meta),
          iterating: false,
        },
        position: { x: 80 + prev.length * 220, y: 120 },
      },
    ])
  }

  const addSubworkflowNode = (wf: PostPreprocWorkflow) => {
    const id = nextId()
    setNodes((prev) => [
      ...prev,
      {
        id,
        type: 'nipype',
        data: {
          label: `subworkflow:${wf.name} (${id})`,
          nodeType: 'subworkflow',
          inputs: Object.keys(wf.inputs ?? {}),
          outputs: Object.keys(wf.outputs ?? {}),
          params: { workflow_name: wf.name },
          iterating: false,
        },
        position: { x: 80 + prev.length * 220, y: 120 },
      },
    ])
  }

  const handleSaveWorkflow = async () => {
    if (!workflowName) return
    // Auto-derive inputs/outputs: any handle on a node that isn't wired and
    // has no _inputs literal becomes a workflow-level input. Any output handle
    // not consumed by a downstream edge becomes a workflow-level output.
    const inputs: Record<string, { from: string }> = {}
    const outputs: Record<string, { from: string }> = {}
    for (const n of nodes) {
      const meta = (n.data as { inputs?: string[]; outputs?: string[] })
      const params = (n.data as { params?: Record<string, unknown> }).params ?? {}
      const literal = (params._inputs as Record<string, string> | undefined) ?? {}
      for (const h of meta.inputs ?? []) {
        const wired = edges.some(
          (e) => e.target === n.id && (e.targetHandle ?? 'in_file') === h,
        )
        if (!wired && !literal[h]) {
          inputs[`${n.id}_${h}`] = { from: `${n.id}.${h}` }
        }
      }
      for (const h of meta.outputs ?? []) {
        const consumed = edges.some(
          (e) => e.source === n.id && (e.sourceHandle ?? 'out_file') === h,
        )
        if (!consumed) {
          outputs[`${n.id}_${h}`] = { from: `${n.id}.${h}` }
        }
      }
    }
    try {
      await saveWorkflow({
        name: workflowName,
        description: workflowDesc,
        graph: buildGraph(),
        inputs,
        outputs,
      })
      setShowSaveDialog(false)
      setWorkflowName('')
      setWorkflowDesc('')
      refreshWorkflows()
    } catch (e) {
      alert(`save failed: ${e}`)
    }
  }

  const handleLoadWorkflow = async (name: string) => {
    try {
      const wf = await fetchWorkflow(name)
      const g = wf.graph
      // Restore nodes with the right type and input/output handle metadata.
      const metaByType = new Map(palette.map((m) => [m.name, m]))
      const newNodes: Node[] = (g.nodes ?? []).map((n) => {
        const meta = metaByType.get(n.type)
        const isSubworkflow = n.type === 'subworkflow'
        const subInputs = isSubworkflow
          ? Object.keys(wf.inputs ?? {})
          : meta?.inputs ?? []
        const subOutputs = isSubworkflow
          ? Object.keys(wf.outputs ?? {})
          : meta?.outputs ?? []
        return {
          id: n.id,
          type: 'nipype',
          data: {
            label: `${n.type} (${n.id})`,
            nodeType: n.type,
            inputs: subInputs,
            outputs: subOutputs,
            params: n.data?.params ?? {},
            iterating: !!(n.data?.params as { _iter?: unknown })?._iter,
          },
          position: n.position ?? { x: 0, y: 0 },
        }
      })
      const newEdges: Edge[] = (g.edges ?? []).map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? 'out_file',
        targetHandle: e.targetHandle ?? 'in_file',
      }))
      setNodes(newNodes)
      setEdges(newEdges)
      setShowLoadPicker(false)
    } catch (e) {
      alert(`load failed: ${e}`)
    }
  }

  const handleAddSubworkflow = async (name: string) => {
    try {
      const wf = await fetchWorkflow(name)
      addSubworkflowNode(wf)
      setShowSubworkflowPicker(false)
    } catch (e) {
      alert(`add failed: ${e}`)
    }
  }

  const buildGraph = (): PostPreprocGraph => ({
    nodes: nodes.map((n) => ({
      id: n.id,
      type: (n.data as { nodeType?: string }).nodeType ?? 'unknown',
      data: { params: (n.data as { params?: Record<string, unknown> }).params ?? {} },
      position: n.position,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? 'out_file',
      targetHandle: e.targetHandle ?? 'in_file',
    })),
  })

  const handleValidate = async () => {
    try {
      const result = await validateGraph(buildGraph())
      setValidation(result.errors)
    } catch (e) {
      setValidation([String(e)])
    }
  }

  const handleRun = async () => {
    setRunErr(null)
    if (!subject || !sourceManifest) {
      setRunErr('subject and source_manifest_path are required')
      return
    }
    try {
      const handle = await startRun({
        subject,
        source_manifest_path: sourceManifest,
        graph: buildGraph(),
        output_dir: outputDir,
      })
      setRun(handle)
    } catch (e) {
      setRunErr(String(e))
    }
  }

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selected) ?? null,
    [nodes, selected],
  )
  const selectedMeta = useMemo(() => {
    if (!selectedNode) return null
    const t = (selectedNode.data as { nodeType?: string }).nodeType
    const fromPalette = palette.find((p) => p.name === t) ?? null
    if (!fromPalette) return null
    // Subworkflow nodes carry their own inputs/outputs in node.data — overlay them.
    const data = selectedNode.data as { inputs?: string[]; outputs?: string[] }
    if (data.inputs && data.outputs) {
      return { ...fromPalette, inputs: data.inputs, outputs: data.outputs }
    }
    return fromPalette
  }, [selectedNode, palette])

  const toggleIterate = () => {
    if (!selectedNode || !selectedMeta) return
    setNodes((prev) =>
      prev.map((n) => {
        if (n.id !== selectedNode.id) return n
        const params = ((n.data as { params?: Record<string, unknown> }).params ?? {}) as Record<string, unknown>
        const isOn = !!params._iter
        const next = { ...params }
        if (isOn) {
          delete next._iter
        } else {
          next._iter = {
            handle: selectedMeta.inputs[0] ?? 'in_file',
            from_source_manifest: true,
          }
        }
        return {
          ...n,
          data: { ...n.data, params: next, iterating: !isOn },
        }
      }),
    )
  }

  const openCode = async () => {
    if (!selectedMeta) return
    setCodeBusy(true)
    setCodeStatus(null)
    try {
      const r = await fetchModuleCode('nipype_nodes', selectedMeta.name)
      setCodeText(r.code)
      setCodePath(r.path)
      setCodeOpen(true)
    } catch (e) {
      setCodeStatus(`load failed: ${e}`)
    } finally {
      setCodeBusy(false)
    }
  }

  const saveCode = async () => {
    if (!selectedMeta) return
    setCodeBusy(true)
    setCodeStatus(null)
    try {
      await saveModuleCode('nipype_nodes', selectedMeta.name, codeText)
      const r = await reloadModule('nipype_nodes', selectedMeta.name)
      setCodeStatus(r.reloaded ? '✓ saved & reloaded' : '✓ saved')
      // Refresh palette so updated PARAM_SCHEMA / IO appears.
      try {
        const fresh = await fetchNipypeNodes()
        setPalette(fresh)
      } catch {
        /* ignore */
      }
    } catch (e) {
      setCodeStatus(`save failed: ${e}`)
    } finally {
      setCodeBusy(false)
    }
  }

  const updateSelectedParam = (key: string, value: unknown) => {
    if (!selectedNode) return
    setNodes((prev) =>
      prev.map((n) =>
        n.id === selectedNode.id
          ? {
              ...n,
              data: {
                ...n.data,
                params: {
                  ...((n.data as { params?: Record<string, unknown> }).params ?? {}),
                  [key]: value,
                },
              },
            }
          : n,
      ),
    )
  }

  const updateSelectedInput = (handle: string, value: string) => {
    if (!selectedNode) return
    setNodes((prev) =>
      prev.map((n) => {
        if (n.id !== selectedNode.id) return n
        const params = ((n.data as { params?: Record<string, unknown> }).params ?? {}) as Record<string, unknown>
        const existing = (params._inputs as Record<string, string> | undefined) ?? {}
        const next = { ...existing, [handle]: value }
        return {
          ...n,
          data: { ...n.data, params: { ...params, _inputs: next } },
        }
      }),
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 48px)' }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>
          Post-preprocessing (nipype)
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          Compose nipype-style nodes that consume a preproc manifest and emit
          new derivatives. Drag from the palette → connect → run.
        </div>
      </div>

      {/* Top bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 2fr 2fr auto auto',
          gap: 8,
          marginBottom: 8,
        }}
      >
        <input
          placeholder="subject (e.g. sub01)"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          style={inputStyle}
        />
        <input
          placeholder="source preproc_manifest.json path"
          value={sourceManifest}
          onChange={(e) => setSourceManifest(e.target.value)}
          style={inputStyle}
        />
        <input
          placeholder="output_dir"
          value={outputDir}
          onChange={(e) => setOutputDir(e.target.value)}
          style={inputStyle}
        />
        <button style={btn} onClick={handleValidate}>
          Validate
        </button>
        <button style={primaryBtn} onClick={handleRun}>
          Run
        </button>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <button style={btn} onClick={() => setShowSaveDialog(true)} disabled={nodes.length === 0}>
          Save workflow
        </button>
        <button style={btn} onClick={() => { refreshWorkflows(); setShowLoadPicker(true) }}>
          Load workflow
        </button>
        <button style={btn} onClick={() => { refreshWorkflows(); setShowSubworkflowPicker(true) }}>
          + Subworkflow
        </button>
      </div>

      {validation && (
        <div
          style={{
            padding: 8,
            marginBottom: 8,
            border: '1px solid var(--border)',
            borderRadius: 4,
            background: 'var(--bg-card)',
            fontSize: 12,
            color: validation.length === 0 ? 'var(--accent-green)' : 'var(--accent-red)',
          }}
        >
          {validation.length === 0
            ? '✓ Graph is valid'
            : validation.map((v, i) => <div key={i}>✗ {v}</div>)}
        </div>
      )}

      {run && (
        <div
          style={{
            padding: 8,
            marginBottom: 8,
            border: '1px solid var(--border)',
            borderRadius: 4,
            background: 'var(--bg-card)',
            fontSize: 12,
          }}
        >
          run <code>{run.run_id}</code> · status:{' '}
          <strong
            style={{
              color:
                run.status === 'done'
                  ? 'var(--accent-green)'
                  : run.status === 'failed'
                  ? 'var(--accent-red)'
                  : 'var(--accent-yellow)',
            }}
          >
            {run.status}
          </strong>
          {runErr && (
            <pre
              style={{
                marginTop: 6,
                fontSize: 11,
                whiteSpace: 'pre-wrap',
                color: 'var(--accent-red)',
              }}
            >
              {runErr}
            </pre>
          )}
        </div>
      )}

      {/* Save workflow modal */}
      {showSaveDialog && (
        <div style={modalBackdrop} onClick={() => setShowSaveDialog(false)}>
          <div style={modalCard} onClick={(e) => e.stopPropagation()}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Save workflow</div>
            <input
              style={{ ...inputStyle, marginBottom: 6 }}
              placeholder="name (e.g. smooth_then_mask)"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
            />
            <input
              style={{ ...inputStyle, marginBottom: 8 }}
              placeholder="description (optional)"
              value={workflowDesc}
              onChange={(e) => setWorkflowDesc(e.target.value)}
            />
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
              Free input/output handles will be auto-exposed as workflow inputs/outputs.
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button style={btn} onClick={() => setShowSaveDialog(false)}>Cancel</button>
              <button style={primaryBtn} onClick={handleSaveWorkflow} disabled={!workflowName}>Save</button>
            </div>
          </div>
        </div>
      )}

      {/* Load workflow picker */}
      {showLoadPicker && (
        <div style={modalBackdrop} onClick={() => setShowLoadPicker(false)}>
          <div style={modalCard} onClick={(e) => e.stopPropagation()}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Load workflow</div>
            {workflows.length === 0 && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>None saved yet.</div>
            )}
            {workflows.map((w) => (
              <button
                key={w.name}
                style={{ ...btn, width: '100%', textAlign: 'left', marginBottom: 4 }}
                onClick={() => handleLoadWorkflow(w.name)}
              >
                <strong>{w.name}</strong>
                <span style={{ marginLeft: 6, color: 'var(--text-secondary)', fontSize: 10 }}>
                  ({w.n_nodes} nodes · in: {w.inputs.length} · out: {w.outputs.length})
                </span>
                {w.description && (
                  <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{w.description}</div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Subworkflow picker */}
      {showSubworkflowPicker && (
        <div style={modalBackdrop} onClick={() => setShowSubworkflowPicker(false)}>
          <div style={modalCard} onClick={(e) => e.stopPropagation()}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Pick a saved workflow to embed</div>
            {workflows.length === 0 && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>None saved yet.</div>
            )}
            {workflows.map((w) => (
              <button
                key={w.name}
                style={{ ...btn, width: '100%', textAlign: 'left', marginBottom: 4 }}
                onClick={() => handleAddSubworkflow(w.name)}
              >
                <strong>{w.name}</strong>
                <span style={{ marginLeft: 6, color: 'var(--text-secondary)', fontSize: 10 }}>
                  in: {w.inputs.join(', ') || '—'} · out: {w.outputs.join(', ') || '—'}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Code editor modal */}
      {codeOpen && selectedMeta && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.65)',
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          onClick={() => setCodeOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '90vw',
              height: '85vh',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: 12,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 8,
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 700 }}>
                {selectedMeta.name}
              </div>
              <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                {codePath}
              </code>
              <div style={{ flex: 1 }} />
              {codeStatus && (
                <span
                  style={{
                    fontSize: 11,
                    color: codeStatus.startsWith('✓')
                      ? 'var(--accent-green)'
                      : 'var(--accent-red)',
                  }}
                >
                  {codeStatus}
                </span>
              )}
              <button style={primaryBtn} onClick={saveCode} disabled={codeBusy}>
                {codeBusy ? 'Saving…' : 'Save & reload'}
              </button>
              <button style={btn} onClick={() => setCodeOpen(false)}>
                Close
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 0, border: '1px solid var(--border)', borderRadius: 4 }}>
              <Editor
                language="python"
                theme="vs-dark"
                value={codeText}
                onChange={(v) => setCodeText(v ?? '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 12,
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Body: palette | canvas | params */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 280px', gap: 8, flex: 1, minHeight: 0 }}>
        {/* Palette */}
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 4,
            background: 'var(--bg-secondary)',
            padding: 8,
            overflowY: 'auto',
          }}
        >
          <div style={sectionLabel}>Palette</div>
          {palette.map((m) => (
            <button
              key={m.name}
              style={{ ...btn, width: '100%', marginBottom: 4, textAlign: 'left' }}
              onClick={() => addNode(m)}
              title={m.docstring}
            >
              {m.name}
            </button>
          ))}
        </div>

        {/* Canvas */}
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 4,
            background: 'var(--bg-secondary)',
            minHeight: 0,
          }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, n) => setSelected(n.id)}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>

        {/* Param editor */}
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 4,
            background: 'var(--bg-secondary)',
            padding: 8,
            overflowY: 'auto',
          }}
        >
          <div style={sectionLabel}>Parameters</div>
          {!selectedNode && (
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              Click a node on the canvas.
            </div>
          )}
          {selectedNode && selectedMeta && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>
                {selectedMeta.name} <code style={{ color: 'var(--text-secondary)' }}>{selectedNode.id}</code>
              </div>
              <button
                style={{ ...btn, marginBottom: 8, width: '100%' }}
                onClick={openCode}
                disabled={codeBusy || selectedMeta.name === 'subworkflow'}
                title={selectedMeta.name === 'subworkflow' ? 'Subworkflows are stored as YAML, not Python' : ''}
              >
                {codeBusy ? 'Loading…' : 'View / edit code'}
              </button>
              {selectedMeta.inputs.length > 0 && (
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    fontSize: 11,
                    color: 'var(--text-secondary)',
                    marginBottom: 8,
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={!!((selectedNode.data as { params?: Record<string, unknown> }).params?._iter)}
                    onChange={toggleIterate}
                  />
                  Iterate over runs from source manifest
                </label>
              )}
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 8 }}>
                outputs: {selectedMeta.outputs.join(', ') || '—'}
              </div>
              {selectedMeta.inputs.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      color: 'var(--text-secondary)',
                      textTransform: 'uppercase',
                      letterSpacing: 1,
                      marginBottom: 6,
                    }}
                  >
                    Inputs
                  </div>
                  {selectedMeta.inputs.map((handle) => {
                    const incomingEdge = edges.find(
                      (e) =>
                        e.target === selectedNode.id &&
                        (e.targetHandle ?? 'in_file') === handle,
                    )
                    const params = (selectedNode.data as { params?: Record<string, unknown> }).params ?? {}
                    const literal = ((params._inputs as Record<string, string> | undefined) ?? {})[handle] ?? ''
                    return (
                      <div key={handle} style={{ marginBottom: 6 }}>
                        <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 2 }}>
                          {handle}
                        </div>
                        {incomingEdge ? (
                          <div
                            style={{
                              ...inputStyle,
                              fontSize: 11,
                              color: 'var(--accent-cyan)',
                              background: 'var(--bg-card)',
                            }}
                          >
                            ← from <code>{incomingEdge.source}</code>
                            <span style={{ color: 'var(--text-secondary)', marginLeft: 6 }}>
                              ({incomingEdge.sourceHandle ?? 'out_file'})
                            </span>
                          </div>
                        ) : (
                          <input
                            style={inputStyle}
                            placeholder="path to file (e.g. /path/to/in.nii.gz)"
                            value={literal}
                            onChange={(e) => updateSelectedInput(handle, e.target.value)}
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
              {Object.entries(selectedMeta.params).map(([key, schema]) => {
                if (key === '_inputs') return null
                const params = (selectedNode.data as { params?: Record<string, unknown> }).params ?? {}
                const v = params[key]
                return (
                  <div key={key} style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 2 }}>
                      {key} <span style={{ opacity: 0.6 }}>({schema.type})</span>
                    </div>
                    <input
                      style={inputStyle}
                      value={v === undefined || v === null ? '' : String(v)}
                      onChange={(e) => {
                        const raw = e.target.value
                        const coerced =
                          schema.type === 'float' || schema.type === 'int'
                            ? raw === ''
                              ? ''
                              : Number(raw)
                            : raw
                        updateSelectedParam(key, coerced)
                      }}
                    />
                    {schema.description && (
                      <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                        {schema.description}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
