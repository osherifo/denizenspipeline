/** The one ReactFlow renderer for a pipeline.
 *
 *  - ``editable``: drag nodes, connect ports (one feed per input), delete with
 *    Backspace; changes flow back through ``onChange``.
 *  - ``statusByNode`` / ``checkpointsByNode``: colour the nodes of a run.
 *
 *  Used by the Build tab (editable), the Runs tab and the Workflows view.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type OnConnect,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { PipelineDoc, PreprocNodeInfo } from '../../api/types'
import { PipelineNodeCard, type PipelineNodeCardData } from './PipelineNodeCard'
import { layoutPositions, needsLayout } from './layout'

const nodeTypes = { pipeline: PipelineNodeCard }

export interface NodeRunStatus {
  status: PipelineNodeCardData['status']
  durationS?: number | null
}

export interface NodeCheckpointStatus {
  worst: 'ok' | 'suspicious' | 'bad' | 'unknown'
  count: number
}

interface Props {
  pipeline: PipelineDoc
  library: PreprocNodeInfo[]
  editable?: boolean
  selectedNodeId?: string | null
  onSelect?: (id: string | null) => void
  onMove?: (id: string, position: { x: number; y: number }) => void
  onConnectPorts?: (edge: { source: string; target: string; sourceHandle: string; targetHandle: string }) => void
  onRemoveNodes?: (ids: string[]) => void
  onRemoveEdges?: (ids: string[]) => void
  statusByNode?: Record<string, NodeRunStatus>
  checkpointsByNode?: Record<string, NodeCheckpointStatus>
  height?: number | string
  fitViewKey?: string
}

const wrap = (height: number | string): CSSProperties => ({
  height, width: '100%', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', background: 'var(--bg-primary)',
})

function toFlow(
  pipeline: PipelineDoc, library: PreprocNodeInfo[],
  statusByNode?: Record<string, NodeRunStatus>, checkpointsByNode?: Record<string, NodeCheckpointStatus>,
): { nodes: Node[]; edges: Edge[] } {
  const byName = new Map(library.map((n) => [n.name, n]))
  const positions = needsLayout(pipeline)
    ? layoutPositions(pipeline, (t) => {
        const info = byName.get(t)
        return { inputs: Object.keys(info?.inputs ?? {}).length, outputs: Object.keys(info?.outputs ?? {}).length }
      })
    : {}
  const nodes: Node[] = pipeline.nodes.map((n) => {
    const info = byName.get(n.type)
    const st = statusByNode?.[n.id]
    const cp = checkpointsByNode?.[n.id]
    const data: PipelineNodeCardData = {
      label: n.id,
      nodeType: n.type,
      kind: n.kind ?? info?.kind ?? 'interface',
      inputs: Object.keys(info?.inputs ?? {}),
      outputs: Object.keys(info?.outputs ?? {}),
      iterating: Boolean(n.data?.iter),
      isBackend: pipeline.manifest?.backend_node === n.id,
      status: st?.status ?? null,
      durationS: st?.durationS ?? null,
      checkpointVerdict: cp?.worst ?? null,
      checkpointCount: cp?.count ?? 0,
    }
    return {
      id: n.id, type: 'pipeline', data,
      position: positions[n.id] ?? n.position ?? { x: 0, y: 0 },
    }
  })
  const edges: Edge[] = pipeline.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle,
    animated: statusByNode?.[e.target]?.status === 'running',
    style: { stroke: 'var(--text-secondary)' },
  }))
  return { nodes, edges }
}

function Inner({
  pipeline, library, editable = false, selectedNodeId, onSelect, onMove, onConnectPorts,
  onRemoveNodes, onRemoveEdges, statusByNode, checkpointsByNode, height = 420, fitViewKey,
}: Props) {
  const flow = useMemo(() => toFlow(pipeline, library, statusByNode, checkpointsByNode), [pipeline, library, statusByNode, checkpointsByNode])
  const [nodes, setNodes] = useState<Node[]>(flow.nodes)
  useEffect(() => {
    setNodes(flow.nodes.map((n) => ({ ...n, selected: n.id === selectedNodeId })))
  }, [flow.nodes, selectedNodeId])

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((prev) => applyNodeChanges(changes, prev))
    for (const c of changes) {
      if (c.type === 'position' && c.position && !c.dragging && onMove) onMove(c.id, c.position)
      if (c.type === 'remove' && onRemoveNodes) onRemoveNodes([c.id])
    }
  }, [onMove, onRemoveNodes])

  const onConnect: OnConnect = useCallback((c: Connection) => {
    if (!editable || !onConnectPorts || !c.source || !c.target) return
    onConnectPorts({ source: c.source, target: c.target, sourceHandle: c.sourceHandle ?? 'out_file', targetHandle: c.targetHandle ?? 'in_file' })
  }, [editable, onConnectPorts])

  return (
    <div style={wrap(height)}>
      <ReactFlow
        key={fitViewKey}
        nodes={nodes}
        edges={flow.edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onConnect={onConnect}
        onEdgesDelete={(deleted) => onRemoveEdges?.(deleted.map((e) => e.id))}
        onNodeClick={(_, n) => onSelect?.(n.id)}
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

export function PipelineGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  )
}
