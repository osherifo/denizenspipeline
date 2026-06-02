/** Modal showing the analysis-pipeline graph for a finished run.
 *
 * Renders the 7-stage subject pipeline (or the group-stage chain) as a
 * left-to-right graph with one node per stage plus child plugin nodes.
 * Click a plugin node to open a side drawer with its source code and
 * any output files attributable to it.
 *
 * Layout/look mirrors NipypeGraphModal so the two viewers feel of a
 * piece — ReactFlow + Dagre, status-coloured nodes, full-bleed canvas
 * with a fixed-width right drawer.
 */

import { memo, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  Position,
  Handle,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react'
import dagre from 'dagre'

import {
  fetchRunGraph,
  type GraphTarget,
  type RunGraphResponse,
  type RunGraphNode,
} from '../../api/run-graph'
import { AnalysisNodePanel } from './AnalysisNodePanel'


// ── status colours (kept in sync with NipypeGraphModal) ────────────────


const STATUS_COLOR: Record<string, string> = {
  ok: '#00e676',
  running: '#00e5ff',
  warning: '#ffd600',
  failed: '#ff1744',
  skipped: '#888',
  unknown: '#888',
}
const NEUTRAL = 'var(--text-secondary)'


// ── custom nodes ───────────────────────────────────────────────────────


type StageNodeData = RunGraphNode & { _kind: 'stage' }
type PluginNodeData = RunGraphNode & { _kind: 'plugin'; _hasSource: boolean }


function _StageInner({ data }: NodeProps & { data: StageNodeData }) {
  const color = STATUS_COLOR[data.status] ?? NEUTRAL
  return (
    <div style={{
      background: `${color}11`,
      border: `1px solid ${color}66`,
      color: 'var(--text-primary)',
      borderRadius: 6,
      padding: '8px 14px',
      fontSize: 12,
      fontWeight: 700,
      minWidth: 150,
      textAlign: 'center',
      textTransform: 'uppercase',
      letterSpacing: 0.5,
    }}>
      <Handle type="target" position={Position.Left} id="prev" style={{ background: color }} />
      {data.label}
      <div style={{ fontSize: 9, color, fontWeight: 600, marginTop: 2 }}>
        {data.status}
        {data.elapsed_s != null && ` · ${data.elapsed_s.toFixed(1)}s`}
      </div>
      <Handle type="source" position={Position.Right} id="next" style={{ background: color }} />
      {/* Bottom handle feeds the stack of plugin nodes below this stage. */}
      <Handle type="source" position={Position.Bottom} id="impl"
              style={{ background: color, opacity: 0.6 }} />
    </div>
  )
}
const StageNode = memo(_StageInner)


function _PluginInner({ data }: NodeProps & { data: PluginNodeData }) {
  const color = STATUS_COLOR[data.status] ?? NEUTRAL
  return (
    <div
      style={{
        background: `${color}22`,
        border: `1px solid ${color}aa`,
        color: 'var(--text-primary)',
        borderRadius: 5,
        padding: '5px 10px',
        fontSize: 11,
        fontWeight: 600,
        minWidth: 120,
        textAlign: 'center',
        cursor: 'pointer',
        position: 'relative',
      }}
      title={data._hasSource ? `${data.label} — click for source + outputs` : data.label}
    >
      {/* Top handle is fed from the parent stage. */}
      <Handle type="target" position={Position.Top} id="from-stage"
              style={{ background: color, opacity: 0.6 }} />
      <div>{data.label}</div>
      <div style={{ fontSize: 9, color: 'var(--text-secondary)', fontWeight: 500 }}>
        {data.kind.replace('_', ' ')}
      </div>
    </div>
  )
}
const PluginNode = memo(_PluginInner)


const nodeTypes = {
  analysis_stage: StageNode,
  analysis_plugin: PluginNode,
}


// ── layout ─────────────────────────────────────────────────────────────


const STAGE_W = 170
const STAGE_H = 60
const PLUGIN_W = 150
const PLUGIN_H = 50
const STAGE_TO_PLUGIN_GAP = 28
const PLUGIN_GAP = 10


function _layout(graph: RunGraphResponse): { nodes: Node[]; edges: Edge[] } {
  if (!graph.nodes.length) return { nodes: [], edges: [] }

  const stageNodes = graph.nodes.filter((n) => n.kind === 'stage')
  const pluginNodes = graph.nodes.filter((n) => n.kind !== 'stage')

  // Layout strategy: dagre lays out only the stage chain
  // (left-to-right). Each stage's plugin children are then stacked
  // vertically directly underneath that stage so the visual hierarchy
  // reads as "the stage is the concept, the boxes below are the
  // implementations chosen by this run". Plugins never sit next to
  // a sibling stage.
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  // Give dagre extra horizontal room so the stacked plugin columns
  // don't visually collide with adjacent stages.
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 120 })
  for (const n of stageNodes) g.setNode(n.id, { width: STAGE_W, height: STAGE_H })
  for (const e of graph.edges) g.setEdge(e.source, e.target)
  dagre.layout(g)

  // Index plugins by their parent stage id (the prefix before ':').
  const pluginsByStage = new Map<string, RunGraphNode[]>()
  for (const p of pluginNodes) {
    // Group runs include a `subject:` node under `subject_fanout`;
    // for those we still want them stacked under that stage.
    const parentId = `stage:${p.stage}`
    const arr = pluginsByStage.get(parentId) ?? []
    arr.push(p)
    pluginsByStage.set(parentId, arr)
  }

  const flowNodes: Node[] = []
  const stagePos = new Map<string, { x: number; y: number }>()
  for (const n of stageNodes) {
    const pos = g.node(n.id) ?? { x: 0, y: 0 }
    const x = pos.x - STAGE_W / 2
    const y = pos.y - STAGE_H / 2
    stagePos.set(n.id, { x, y })
    flowNodes.push({
      id: n.id,
      type: 'analysis_stage',
      data: { ...n, _kind: 'stage' },
      position: { x, y },
      width: STAGE_W,
      height: STAGE_H,
      draggable: false,
    })
  }
  for (const [parentId, plugins] of pluginsByStage) {
    const sp = stagePos.get(parentId)
    if (!sp) continue
    // Centre each plugin horizontally under its stage and stack
    // vertically with a uniform gap.
    const stageCenterX = sp.x + STAGE_W / 2
    const startY = sp.y + STAGE_H + STAGE_TO_PLUGIN_GAP
    plugins.forEach((p, i) => {
      flowNodes.push({
        id: p.id,
        type: 'analysis_plugin',
        data: { ...p, _kind: 'plugin', _hasSource: !!p.source_path },
        position: {
          x: stageCenterX - PLUGIN_W / 2,
          y: startY + i * (PLUGIN_H + PLUGIN_GAP),
        },
        width: PLUGIN_W,
        height: PLUGIN_H,
        draggable: true,
      })
    })
  }

  const flowEdges: Edge[] = []
  // Stage → stage (the main horizontal chain).
  for (const e of graph.edges) {
    flowEdges.push({
      id: `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      sourceHandle: 'next',
      targetHandle: 'prev',
      type: 'smoothstep',
      style: { stroke: 'var(--border)' },
    })
  }
  // One short dotted line from each stage to its first plugin. The
  // remaining plugins read as "also under this stage" purely from
  // vertical alignment — drawing an edge to every plugin would add
  // visual noise without adding information.
  for (const [parentId, plugins] of pluginsByStage) {
    if (plugins.length === 0) continue
    flowEdges.push({
      id: `${parentId}~${plugins[0].id}`,
      source: parentId,
      target: plugins[0].id,
      sourceHandle: 'impl',
      targetHandle: 'from-stage',
      type: 'smoothstep',
      style: { stroke: 'var(--border)', strokeDasharray: '3 3', opacity: 0.5 },
    })
  }
  return { nodes: flowNodes, edges: flowEdges }
}


// ── modal shell ────────────────────────────────────────────────────────


const backdrop: CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999,
}

const card: CSSProperties = {
  width: '94vw', height: '90vh',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  display: 'flex',
  flexDirection: 'column',
  padding: 12,
}

const header: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8,
}

const closeBtn: CSSProperties = {
  padding: '4px 12px',
  fontSize: 12,
  border: '1px solid var(--border)',
  borderRadius: 4,
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
}


interface Props {
  target: GraphTarget
  title: string
  onClose: () => void
  /** Optional callback when a subject node is clicked in a group graph.
   *  Used to drill into the per-subject graph. */
  onSubjectClick?: (subjectId: string) => void
  /** Optional callback when a group node is clicked in a study graph.
   *  Used to drill into the per-group graph. */
  onGroupClick?: (groupLabel: string) => void
}


export function AnalysisGraphModal({ target, title, onClose, onSubjectClick, onGroupClick }: Props) {
  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <ReactFlowProvider>
          <Inner
            target={target}
            title={title}
            onClose={onClose}
            onSubjectClick={onSubjectClick}
            onGroupClick={onGroupClick}
          />
        </ReactFlowProvider>
      </div>
    </div>
  )
}


function Inner({ target, title, onClose, onSubjectClick, onGroupClick }: Props) {
  const [graph, setGraph] = useState<RunGraphResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openNode, setOpenNode] = useState<RunGraphNode | null>(null)

  useEffect(() => {
    let cancelled = false
    setGraph(null)
    setError(null)
    setOpenNode(null)
    fetchRunGraph(target)
      .then((g) => { if (!cancelled) setGraph(g) })
      .catch((e) => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
    // Stringify target so we re-fetch when the target identity changes
    // even though the object literal does
  }, [JSON.stringify(target)])

  const flow = useMemo(() => graph ? _layout(graph) : { nodes: [], edges: [] }, [graph])

  const onNodeClick = (_: unknown, node: Node) => {
    if (!graph) return
    const found = graph.nodes.find((n) => n.id === node.id)
    if (!found) return
    if (found.kind === 'subject' && onSubjectClick) {
      onSubjectClick(found.plugin_name ?? found.id.replace(/^subject:/, ''))
      return
    }
    if (found.kind === 'group' && onGroupClick) {
      onGroupClick(found.plugin_name ?? found.id.replace(/^group:/, ''))
      return
    }
    if (found.kind === 'stage') return  // not interactive
    setOpenNode(found)
  }

  return (
    <>
      <div style={header}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>{title}</div>
        {graph && (
          <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            {graph.nodes.length} nodes · {graph.edges.length} edges
          </div>
        )}
        <div style={{ flex: 1 }} />
        <button style={closeBtn} onClick={onClose}>Close</button>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', borderRadius: 6 }}>
        <div style={{ flex: 1, position: 'relative' }}>
          {error && (
            <div style={{ padding: 16, color: 'var(--accent-red)', fontSize: 12 }}>
              Failed to load graph: {error}
            </div>
          )}
          {!error && !graph && (
            <div style={{ padding: 16, color: 'var(--text-secondary)', fontSize: 12 }}>
              Loading…
            </div>
          )}
          {graph && (
            <ReactFlow
              nodes={flow.nodes}
              edges={flow.edges}
              nodeTypes={nodeTypes}
              onNodeClick={onNodeClick}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              minZoom={0.2}
              maxZoom={2}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={20} color="var(--border)" />
              <Controls position="bottom-left" showInteractive={false} />
            </ReactFlow>
          )}
        </div>
        {openNode && (
          <AnalysisNodePanel
            target={target}
            node={openNode}
            onClose={() => setOpenNode(null)}
          />
        )}
      </div>
    </>
  )
}
