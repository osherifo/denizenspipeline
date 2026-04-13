/** Pipeline Graph — visual node-based pipeline builder. */
import { useEffect, useCallback, useState } from 'react'
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

const canvasContainer: CSSProperties = {
  flex: 1,
  borderRadius: 8,
  border: '1px solid var(--border)',
  overflow: 'hidden',
  position: 'relative',
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
    selectNode, selectedNodeId,
    loadTemplate, relayout,
  } = useGraphStore()

  const [template, setTemplate] = useState('')

  // Load default template on first mount if graph is empty
  useEffect(() => {
    if (nodes.length === 0) {
      loadTemplate('Full Pipeline')
      setTemplate('Full Pipeline')
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

  return (
    <div style={pageStyle}>
      {/* Toolbar */}
      <div style={toolbar}>
        <span style={pageTitle}>Pipeline Graph</span>
        <div style={{ flex: 1 }} />
        <select style={selectStyle} value={template} onChange={(e) => handleTemplateChange(e.target.value)}>
          <option value="">Load template...</option>
          {TEMPLATES.map((t) => (
            <option key={t.name} value={t.name}>{t.name}</option>
          ))}
        </select>
        <button style={btnSecondary} onClick={relayout}>Re-layout</button>
        <button style={btnPrimary} disabled>Run All</button>
      </div>

      {/* Node palette */}
      <div style={paletteBar}>
        <div style={paletteLbl}>Add node</div>
        <NodePalette />
      </div>

      {/* Canvas */}
      <div style={canvasContainer}>
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

      {/* Detail panel */}
      <NodeDetailPanel />
    </div>
  )
}
