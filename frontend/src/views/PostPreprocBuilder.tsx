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
import {
  fetchNipypeNodes,
  validateGraph,
  startRun,
  getRun,
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
} from '../api/types'

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

// Match the Workflows view's preproc-stage color so the eye carries through.
const NODE_COLOR = '#10b981'

function nodeStyle(): CSSProperties {
  return {
    background: `${NODE_COLOR}22`,
    border: `1px solid ${NODE_COLOR}aa`,
    color: 'var(--text-primary)',
    borderRadius: 6,
    padding: 8,
    fontSize: 12,
    fontWeight: 600,
    minWidth: 140,
  }
}

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

  useEffect(() => {
    fetchNipypeNodes().then(setPalette).catch((e) => console.error(e))
  }, [])

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
        type: 'default',
        data: {
          label: `${meta.name} (${id})`,
          nodeType: meta.name,
          params: defaultsForNode(meta),
        },
        position: { x: 80 + prev.length * 180, y: 120 },
        style: nodeStyle(),
      },
    ])
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
    return palette.find((p) => p.name === t) ?? null
  }, [selectedNode, palette])

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
                disabled={codeBusy}
              >
                {codeBusy ? 'Loading…' : 'View / edit code'}
              </button>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 8 }}>
                inputs: {selectedMeta.inputs.join(', ') || '—'} · outputs:{' '}
                {selectedMeta.outputs.join(', ') || '—'}
              </div>
              {Object.entries(selectedMeta.params).map(([key, schema]) => {
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
