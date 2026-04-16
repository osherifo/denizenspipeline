/** Pipeline Graph — visual node-based pipeline builder. */
import { useEffect, useCallback, useState, useRef } from 'react'
import type { CSSProperties } from 'react'
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  type Connection,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { useGraphStore, isValidConnection, TEMPLATES } from '../stores/graph-store'
import { nodeTypes } from '../components/graph/StageNode'
import { NodeDetailPanel } from '../components/graph/NodeDetailPanel'
import { NodePalette } from '../components/graph/NodePalette'

// ── Styles ──────────────────────────────────────────────────────────────

const pageStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  height: 'calc(100vh - 48px)',
}

const toolbar: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '12px 0',
  flexShrink: 0,
}

const pageTitle: CSSProperties = {
  fontSize: 18,
  fontWeight: 800,
  color: 'var(--text-primary)',
  letterSpacing: 1,
}

const btnPrimary: CSSProperties = {
  padding: '6px 16px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 5,
  cursor: 'pointer',
  border: 'none',
  backgroundColor: 'var(--accent-cyan)',
  color: '#000',
}

const btnSecondary: CSSProperties = {
  padding: '6px 16px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 5,
  cursor: 'pointer',
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}

const selectStyle: CSSProperties = {
  padding: '6px 10px',
  fontSize: 11,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  color: 'var(--text-primary)',
  appearance: 'auto' as const,
}

const workflowNameInput: CSSProperties = {
  padding: '6px 10px',
  fontSize: 12,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  color: 'var(--text-primary)',
  minWidth: 220,
}

const splitContainer: CSSProperties = {
  display: 'flex',
  gap: 10,
  flex: 1,
  minHeight: 0,
}

const canvasContainer = (flex: number): CSSProperties => ({
  flex,
  borderRadius: 8,
  border: '1px solid var(--border)',
  overflow: 'hidden',
  position: 'relative',
  minWidth: 0,
})

const yamlPanel: CSSProperties = {
  width: 440,
  display: 'flex',
  flexDirection: 'column',
  border: '1px solid var(--border)',
  borderRadius: 8,
  backgroundColor: 'var(--bg-card)',
  overflow: 'hidden',
}

const yamlHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '8px 12px',
  borderBottom: '1px solid var(--border)',
  backgroundColor: 'var(--bg-secondary)',
}

const yamlHeaderLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const yamlTextarea = (editing: boolean, hasError: boolean): CSSProperties => ({
  flex: 1,
  width: '100%',
  padding: '10px 12px',
  fontSize: 11,
  lineHeight: 1.5,
  fontFamily: '"JetBrains Mono", "Fira Code", monospace',
  backgroundColor: 'var(--bg-input)',
  border: 'none',
  borderLeft: `3px solid ${
    hasError ? 'var(--accent-red)' : editing ? 'var(--accent-cyan)' : 'transparent'
  }`,
  color: 'var(--text-primary)',
  resize: 'none',
  outline: 'none',
  tabSize: 2,
})

const yamlErrorBox: CSSProperties = {
  fontSize: 11,
  color: 'var(--accent-red)',
  padding: '8px 12px',
  borderTop: '1px solid var(--border)',
  backgroundColor: 'rgba(255, 23, 68, 0.08)',
  fontFamily: 'monospace',
  whiteSpace: 'pre-wrap',
  maxHeight: 100,
  overflowY: 'auto',
}

const applyBtn: CSSProperties = {
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 4,
  cursor: 'pointer',
  border: 'none',
  backgroundColor: 'var(--accent-cyan)',
  color: '#000',
}

const paletteBar: CSSProperties = {
  padding: '10px 0',
  flexShrink: 0,
}

const paletteLbl: CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginBottom: 6,
}

const emptyState: CSSProperties = {
  position: 'absolute',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  textAlign: 'center',
  color: 'var(--text-secondary)',
  fontSize: 13,
  zIndex: 1,
  pointerEvents: 'none',
}

// ── Component ───────────────────────────────────────────────────────────

export function PipelineGraph() {
  const {
    nodes, edges,
    onNodesChange, onEdgesChange, onConnect,
    selectNode,
    loadTemplate, relayout,
    yamlString, yamlErrors, yamlEditing,
    workflowName, setWorkflowName,
    setYamlDirect, applyYaml,
    syncYamlFromGraph,
  } = useGraphStore()

  const [template, setTemplate] = useState('')
  const [showYaml, setShowYaml] = useState(true)
  const applyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load default template on first mount if graph is empty
  useEffect(() => {
    if (nodes.length === 0) {
      loadTemplate('Full Pipeline')
      setTemplate('Full Pipeline')
    } else {
      syncYamlFromGraph()
    }
  }, [])

  const handleTemplateChange = (name: string) => {
    setTemplate(name)
    if (name) loadTemplate(name)
  }

  const handleNodeClick = useCallback((_: unknown, node: { id: string }) => {
    selectNode(node.id)
  }, [selectNode])

  const handlePaneClick = useCallback(() => {
    selectNode(null)
  }, [selectNode])

  const handleConnect = useCallback((connection: Connection) => {
    onConnect(connection)
  }, [onConnect])

  const validateConnection = useCallback((connection: Connection | Edge) => {
    return isValidConnection(connection, nodes)
  }, [nodes])

  const handleYamlChange = useCallback((value: string) => {
    setYamlDirect(value)
    if (applyTimer.current) clearTimeout(applyTimer.current)
    applyTimer.current = setTimeout(() => applyYaml(), 800)
  }, [setYamlDirect, applyYaml])

  const handleYamlBlur = useCallback(() => {
    if (applyTimer.current) {
      clearTimeout(applyTimer.current)
      applyTimer.current = null
    }
    if (yamlEditing) applyYaml()
  }, [yamlEditing, applyYaml])

  return (
    <div style={pageStyle}>
      {/* Toolbar */}
      <div style={toolbar}>
        <span style={pageTitle}>Pipeline Graph</span>
        <input
          style={workflowNameInput}
          value={workflowName}
          onChange={(e) => setWorkflowName(e.target.value)}
          placeholder="workflow name (optional)"
        />
        <div style={{ flex: 1 }} />
        <select style={selectStyle} value={template} onChange={(e) => handleTemplateChange(e.target.value)}>
          <option value="">Load template...</option>
          {TEMPLATES.map((t) => (
            <option key={t.name} value={t.name}>{t.name}</option>
          ))}
        </select>
        <button style={btnSecondary} onClick={relayout}>Re-layout</button>
        <button style={btnSecondary} onClick={() => setShowYaml((v) => !v)}>
          {showYaml ? 'Hide YAML' : 'Show YAML'}
        </button>
        <button style={btnPrimary} disabled>Run All</button>
      </div>

      {/* Node palette */}
      <div style={paletteBar}>
        <div style={paletteLbl}>Add node</div>
        <NodePalette />
      </div>

      {/* Split: canvas + YAML */}
      <div style={splitContainer}>
        {/* Canvas */}
        <div style={canvasContainer(1)}>
          {nodes.length === 0 && (
            <div style={emptyState}>
              Select a template above or add nodes to get started
            </div>
          )}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={handleConnect}
            isValidConnection={validateConnection}
            onNodeClick={handleNodeClick}
            onPaneClick={handlePaneClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            proOptions={{ hideAttribution: true }}
            deleteKeyCode={['Backspace', 'Delete']}
            style={{ backgroundColor: '#0a0a1a' }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1a1a2e" />
            <Controls
              showInteractive={false}
              style={{ backgroundColor: '#111128', border: '1px solid #2a2a4a', borderRadius: 6 }}
            />
            <MiniMap
              nodeColor={(n) => {
                const data = n.data as { status?: string } | undefined
                if (data?.status === 'done') return '#10b981'
                if (data?.status === 'running') return '#3b82f6'
                if (data?.status === 'error') return '#ef4444'
                return '#4a4a6a'
              }}
              style={{ backgroundColor: '#111128', border: '1px solid #2a2a4a', borderRadius: 6 }}
              maskColor="rgba(10, 10, 26, 0.7)"
            />
          </ReactFlow>
        </div>

        {/* YAML panel */}
        {showYaml && (
          <div style={yamlPanel}>
            <div style={yamlHeader}>
              <span style={yamlHeaderLabel}>
                Workflow YAML {yamlEditing ? '(editing)' : ''}
              </span>
              {yamlEditing && (
                <button style={applyBtn} onClick={applyYaml}>Apply</button>
              )}
            </div>
            <textarea
              style={yamlTextarea(yamlEditing, yamlErrors.length > 0)}
              value={yamlString}
              onChange={(e) => handleYamlChange(e.target.value)}
              onBlur={handleYamlBlur}
              spellCheck={false}
            />
            {yamlErrors.length > 0 && (
              <div style={yamlErrorBox}>
                {yamlErrors.map((e, i) => <div key={i}>{e}</div>)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Detail panel */}
      <NodeDetailPanel />
    </div>
  )
}
