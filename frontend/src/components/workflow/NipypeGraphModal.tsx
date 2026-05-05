/** Modal showing the live nipype DAG (tree-from-paths) for a Preproc run. */

import { memo, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  Position,
  Handle,
  useReactFlow,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react'
import dagre from 'dagre'

import { fetchPreprocRunLive } from '../../api/client'
import type { NipypeStatusBlock } from '../../api/types'
import { buildNipypeTree, type NipypeTreeNode } from './nipype_tree'
import { NodeOutputsPanel } from './NodeOutputsPanel'
import { NodeListPanel } from './NodeListPanel'

const STATUS_COLOR: Record<string, string> = {
  running: '#00e5ff',
  ok: '#00e676',
  failed: '#ff1744',
  completed_assumed: '#52c98f',
}
const NEUTRAL = 'var(--text-secondary)'


// ── Custom nodes ────────────────────────────────────────────────────────


type LeafData = NipypeTreeNode & { _kind: 'leaf' }
type WorkflowData = NipypeTreeNode & { _kind: 'workflow' }


function _LeafNodeInner({ data }: NodeProps & { data: LeafData }) {
  const color = STATUS_COLOR[data.status ?? ''] ?? NEUTRAL
  const elapsed = data.elapsed && data.elapsed > 0
    ? ` · ${data.elapsed.toFixed(1)}s`
    : ''
  return (
    <div
      style={{
        background: `${color}22`,
        border: `1px solid ${color}aa`,
        color: 'var(--text-primary)',
        borderRadius: 5,
        padding: '4px 8px',
        fontSize: 11,
        fontWeight: 600,
        minWidth: 110,
        textAlign: 'center',
        position: 'relative',
      }}
      title={`${data.full_node ?? data.id} — ${data.status ?? ''}${elapsed}`}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      <div>{data.label}</div>
      <div style={{ fontSize: 9, color }}>
        {data.status ?? ''}{elapsed}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  )
}
const LeafNode = memo(_LeafNodeInner)


function _WorkflowNodeInner({ data }: NodeProps & { data: WorkflowData }) {
  const c = data.counts ?? { running: 0, ok: 0, failed: 0, total: 0 }
  // Dominant color: failed > running > ok > completed_assumed > neutral.
  const color =
    c.failed > 0 ? STATUS_COLOR.failed
    : c.running > 0 ? STATUS_COLOR.running
    : c.ok > 0 ? STATUS_COLOR.ok
    : (c as { completed_assumed?: number }).completed_assumed
      ? STATUS_COLOR.completed_assumed
      : NEUTRAL
  return (
    <div
      style={{
        background: `${color}11`,
        border: `1px solid ${color}66`,
        color: 'var(--text-primary)',
        borderRadius: 6,
        padding: '6px 10px',
        fontSize: 11,
        fontWeight: 700,
        minWidth: 130,
        textAlign: 'center',
        position: 'relative',
      }}
      title={data.id}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      <div>{data.label}</div>
      <div
        style={{
          fontSize: 9,
          color,
          marginTop: 2,
          display: 'flex',
          gap: 4,
          justifyContent: 'center',
        }}
      >
        {c.running > 0 && <span>{c.running}▶</span>}
        {c.ok > 0 && <span style={{ color: STATUS_COLOR.ok }}>{c.ok}✓</span>}
        {c.failed > 0 && <span style={{ color: STATUS_COLOR.failed }}>{c.failed}✗</span>}
        {(() => {
          const ca = (c as { completed_assumed?: number }).completed_assumed ?? 0
          return ca > 0 ? (
            <span style={{ color: STATUS_COLOR.completed_assumed }}>{ca}?</span>
          ) : null
        })()}
        {c.total === 0 && <span>—</span>}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  )
}
const WorkflowNode = memo(_WorkflowNodeInner)


const nodeTypes = { nipype_leaf: LeafNode, nipype_workflow: WorkflowNode }


// ── Layout ──────────────────────────────────────────────────────────────


const NODE_WIDTH = 150
const NODE_HEIGHT = 56


function _layout(
  nodes: NipypeTreeNode[],
  edges: { id: string; source: string; target: string }[],
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 18, ranksep: 36 })
  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target)
  }
  dagre.layout(g)

  const flowNodes: Node[] = nodes.map((n) => {
    const pos = g.node(n.id) ?? { x: 0, y: 0 }
    return {
      id: n.id,
      type: n.kind === 'leaf' ? 'nipype_leaf' : 'nipype_workflow',
      data: { ...n, _kind: n.kind },
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    }
  })
  const flowEdges: Edge[] = edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    style: { stroke: 'var(--border)' },
  }))
  return { nodes: flowNodes, edges: flowEdges }
}


// ── Modal ───────────────────────────────────────────────────────────────


const backdrop: CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.7)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 999,
}

const card: CSSProperties = {
  width: '92vw',
  height: '88vh',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  display: 'flex',
  flexDirection: 'column',
  padding: 12,
}

const header: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  marginBottom: 8,
}

const closeBtn: CSSProperties = {
  padding: '4px 12px',
  fontSize: 12,
  border: '1px solid var(--border)',
  borderRadius: 4,
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
  marginLeft: 'auto',
}


interface Props {
  runId: string
  isRunning: boolean
  onClose: () => void
}


export function NipypeGraphModal({ runId, isRunning, onClose }: Props) {
  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <ReactFlowProvider>
          <Inner runId={runId} isRunning={isRunning} onClose={onClose} />
        </ReactFlowProvider>
      </div>
    </div>
  )
}


function Inner({ runId, isRunning, onClose }: Props) {
  const [block, setBlock] = useState<NipypeStatusBlock | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openNode, setOpenNode] = useState<string | null>(null)
  const rf = useReactFlow()

  // Whenever the user picks a node (via list or graph click), pan + zoom
  // the canvas to centre that node. fitView with a single-node selector
  // does both at once and animates smoothly.
  useEffect(() => {
    if (!openNode) return
    // Defer one tick so the layout has the node by the time we pan.
    const t = setTimeout(() => {
      try {
        rf.fitView({
          nodes: [{ id: openNode }],
          duration: 400,
          padding: 0.4,
          maxZoom: 1.5,
        })
      } catch { /* node not in graph yet — ignore */ }
    }, 50)
    return () => clearTimeout(t)
  }, [openNode, rf])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const detail = await fetchPreprocRunLive(runId, 500)
        if (!cancelled) {
          setBlock(detail.nipype_status)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
    }
    load()
    if (!isRunning) return () => { cancelled = true }
    const id = setInterval(load, 2000)
    return () => { cancelled = true; clearInterval(id) }
  }, [runId, isRunning])

  const flow = useMemo(() => {
    if (!block) return { nodes: [] as Node[], edges: [] as Edge[] }
    const tree = buildNipypeTree(block.recent_nodes)
    return _layout(tree.nodes, tree.edges)
  }, [block])

  return (
    <>
      <div style={header}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>nipype DAG</div>
        <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{runId}</code>
        {block && (
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            {block.counts.running} running · {block.counts.ok} done · {block.counts.failed} failed{block.counts.completed_assumed ? ` · ${block.counts.completed_assumed} assumed` : ''} · {block.counts.total_seen} seen
          </span>
        )}
        {isRunning && (
          <span style={{
            fontSize: 10, color: STATUS_COLOR.running, fontWeight: 700,
            padding: '2px 6px', borderRadius: 8,
            background: `${STATUS_COLOR.running}22`,
            border: `1px solid ${STATUS_COLOR.running}55`,
          }}>
            LIVE
          </span>
        )}
        <button style={closeBtn} onClick={onClose}>Close</button>
      </div>
      <div style={{
        flex: 1, minHeight: 0, display: 'flex',
        border: '1px solid var(--border)',
        borderRadius: 4, background: 'var(--bg-secondary)',
        overflow: 'hidden',
      }}>
        <NodeListPanel
          nodes={block?.recent_nodes ?? []}
          selected={openNode}
          onSelect={setOpenNode}
        />
        <div style={{ flex: 1, minWidth: 0, position: 'relative' }}>
        {error && (
          <div style={{ padding: 12, color: 'var(--accent-red)', fontSize: 12 }}>
            {error}
          </div>
        )}
        {!error && flow.nodes.length === 0 && (
          <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 12 }}>
            No nipype nodes parsed yet — log lines may not have arrived.
          </div>
        )}
        {flow.nodes.length > 0 && (
          <ReactFlow
            nodes={flow.nodes}
            edges={flow.edges}
            nodeTypes={nodeTypes}
            fitView
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={true}
            onNodeClick={(_e, n) => {
              const data = n.data as unknown as NipypeTreeNode & { _kind?: string }
              const kind = data._kind ?? data.kind
              if (kind === 'leaf') {
                setOpenNode(data.full_node ?? data.id)
              }
            }}
          >
            <Background />
            <Controls />
          </ReactFlow>
        )}
        </div>
        {openNode && (
          <NodeOutputsPanel
            runId={runId}
            node={openNode}
            onClose={() => setOpenNode(null)}
          />
        )}
      </div>
    </>
  )
}
