/** The one ReactFlow renderer for node graphs: preprocessing pipelines and analysis graphs.
 *
 *  - ``describeNode`` turns a document node into what its card shows (tag, ports, status,
 *    badges). Pass a memoised function: a new function on every render re-renders the canvas.
 *  - ``editable``: drag nodes, connect ports, delete selected nodes or edges with Backspace/Delete.
 *  - ``isValidConnection`` rejects a drag before it becomes an edge (e.g. mismatched port types).
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type OnConnect,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useThemeStore } from '../../stores/theme-store'
import { GraphNodeCard, type GraphNodeCardData } from './GraphNodeCard'
import { layoutPositions, needsLayout } from './layout'

const nodeTypes = { graph: GraphNodeCard }

export interface GraphDocNode { id: string; type: string; position?: { x: number; y: number } }
export interface GraphDocEdge { id: string; source: string; target: string; sourceHandle: string; targetHandle: string }
export interface GraphDocLike { nodes: GraphDocNode[]; edges: GraphDocEdge[] }
export type GraphConnection = Omit<GraphDocEdge, 'id'>

export interface GraphCanvasProps {
  doc: GraphDocLike
  describeNode: (node: GraphDocNode) => GraphNodeCardData
  editable?: boolean
  selectedNodeId?: string | null
  onSelect?: (id: string | null) => void
  /** Double-click on a node (run views open a node popup). */
  onOpen?: (id: string) => void
  onMove?: (id: string, position: { x: number; y: number }) => void
  onConnectPorts?: (edge: GraphConnection) => void
  onRemoveNodes?: (ids: string[]) => void
  onRemoveEdges?: (ids: string[]) => void
  isValidConnection?: (edge: GraphConnection) => boolean
  defaultSourceHandle?: string
  defaultTargetHandle?: string
  height?: number | string
  fitViewKey?: string
}

const wrap = (height: number | string): CSSProperties => ({
  height, width: '100%', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', background: 'var(--bg-primary)',
})

function toFlow(doc: GraphDocLike, describeNode: GraphCanvasProps['describeNode']): { nodes: Node[]; edges: Edge[] } {
  const described = new Map(doc.nodes.map((n) => [n.id, describeNode(n)]))
  const positions = needsLayout(doc)
    ? layoutPositions(doc, (n) => {
        const d = described.get(n.id)
        return { inputs: d?.inputs.length ?? 0, outputs: d?.outputs.length ?? 0 }
      })
    : {}
  const nodes: Node[] = doc.nodes.map((n) => ({
    id: n.id,
    type: 'graph',
    data: described.get(n.id) as GraphNodeCardData,
    position: positions[n.id] ?? n.position ?? { x: 0, y: 0 },
  }))
  const edges: Edge[] = doc.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle,
    animated: described.get(e.target)?.status === 'running',
    style: { stroke: 'var(--text-secondary)' },
  }))
  return { nodes, edges }
}

function Inner({
  doc, describeNode, editable = false, selectedNodeId, onSelect, onOpen, onMove, onConnectPorts,
  onRemoveNodes, onRemoveEdges, isValidConnection, defaultSourceHandle = 'out', defaultTargetHandle = 'in',
  height = 420, fitViewKey,
}: GraphCanvasProps) {
  const mode = useThemeStore((s) => s.mode)
  const flow = useMemo(() => toFlow(doc, describeNode), [doc, describeNode])
  const [nodes, setNodes] = useState<Node[]>(flow.nodes)
  const [edges, setEdges] = useState<Edge[]>(flow.edges)
  useEffect(() => {
    setNodes(flow.nodes.map((n) => ({ ...n, selected: n.id === selectedNodeId })))
  }, [flow.nodes, selectedNodeId])
  useEffect(() => { setEdges(flow.edges) }, [flow.edges])

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((prev) => applyNodeChanges(changes, prev))
    for (const c of changes) {
      if (c.type === 'position' && c.position && !c.dragging && onMove) onMove(c.id, c.position)
      if (c.type === 'remove' && onRemoveNodes) onRemoveNodes([c.id])
    }
  }, [onMove, onRemoveNodes])

  // Edges are controlled too: without applying selection changes an edge never becomes
  // selected, so Backspace could not delete it.
  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges((prev) => applyEdgeChanges(changes, prev))
  }, [])

  const toConnection = useCallback((c: Connection | Edge): GraphConnection => ({
    source: c.source, target: c.target,
    sourceHandle: c.sourceHandle ?? defaultSourceHandle, targetHandle: c.targetHandle ?? defaultTargetHandle,
  }), [defaultSourceHandle, defaultTargetHandle])

  const onConnect: OnConnect = useCallback((c: Connection) => {
    if (!editable || !onConnectPorts || !c.source || !c.target) return
    onConnectPorts(toConnection(c))
  }, [editable, onConnectPorts, toConnection])

  const checkConnection = useCallback((c: Connection | Edge) => (
    !isValidConnection || isValidConnection(toConnection(c))
  ), [isValidConnection, toConnection])

  return (
    <div style={wrap(height)}>
      <ReactFlow
        key={fitViewKey}
        colorMode={mode}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={checkConnection}
        onEdgesDelete={(deleted) => onRemoveEdges?.(deleted.map((e) => e.id))}
        onNodeClick={(_, n) => onSelect?.(n.id)}
        onNodeDoubleClick={(_, n) => onOpen?.(n.id)}
        zoomOnDoubleClick={false}
        onPaneClick={() => onSelect?.(null)}
        nodesDraggable={editable}
        nodesConnectable={editable}
        elementsSelectable
        deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
        fitView
        fitViewOptions={{ padding: 0.25, maxZoom: 1.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  )
}
