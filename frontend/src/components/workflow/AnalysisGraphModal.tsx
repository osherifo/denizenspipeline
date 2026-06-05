/** Modal showing the analysis-pipeline graph for a finished run.
 *
 * Renders the 7-stage subject pipeline (or the group-stage chain) as a
 * left-to-right graph with one node per stage plus child plugin nodes.
 * Click a plugin node to open a side drawer with its source code and
 * any output files attributable to it.
 *
 * Group/study targets drill down side-by-side: clicking a subject node
 * in a group graph (or a group node in a study graph) opens a second
 * pane to the right rather than replacing the original graph.
 */

import { Fragment, memo, useEffect, useMemo, useState } from 'react'
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
  isLiveTarget,
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

const paneHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '6px 10px',
  background: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-primary)',
}

const paneDivider: CSSProperties = {
  width: 1,
  background: 'var(--border)',
  flexShrink: 0,
}


interface Props {
  target: GraphTarget
  title: string
  onClose: () => void
}


export function AnalysisGraphModal({ target, title, onClose }: Props) {
  // NB: no top-level ReactFlowProvider — each GraphPane wraps its own
  // ReactFlow in a provider so the two panes don't share viewport /
  // node-internals state (a single provider scopes that store to all
  // ReactFlows under it, which would make both panes mirror each other).
  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <Inner target={target} title={title} onClose={onClose} />
      </div>
    </div>
  )
}


function Inner({ target, title, onClose }: Props) {
  // Stack of drill-down panes appended after the primary. Each entry
  // is the target + label for one column. The primary is rendered
  // separately and never appears in this array. Drill events from
  // pane i truncate everything after index i and append the new pane,
  // so re-clicking inside an upstream pane forks the chain instead of
  // stacking forever.
  const [extras, setExtras] = useState<Array<{ target: GraphTarget; title: string }>>([])

  // Reset extras when the primary target changes.
  const externalKey = JSON.stringify(target)
  useEffect(() => {
    setExtras([])
  }, [externalKey])

  const drillFromPane = (paneIndex: number, next: GraphTarget, nextTitle: string) => {
    // paneIndex == 0 is the primary; extras index = paneIndex - 1.
    setExtras((prev) => [
      ...prev.slice(0, paneIndex),
      { target: next, title: nextTitle },
    ])
  }
  const closeFromExtra = (extraIndex: number) => {
    setExtras((prev) => prev.slice(0, extraIndex))
  }

  return (
    <>
      <div style={header}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>{title}</div>
        <div style={{ flex: 1 }} />
        <button style={closeBtn} onClick={onClose}>Close</button>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', borderRadius: 6 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={paneHeader}>
            <span>{title}</span>
          </div>
          <GraphPane
            target={target}
            onDrilldown={(next, nextTitle) => drillFromPane(0, next, nextTitle)}
          />
        </div>
        {extras.map((extra, i) => (
          <Fragment key={`extra-${i}`}>
            <div style={paneDivider} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <div style={paneHeader}>
                <span>{extra.title}</span>
                <div style={{ flex: 1 }} />
                <button
                  style={{ ...closeBtn, padding: '2px 8px', fontSize: 11 }}
                  onClick={() => closeFromExtra(i)}
                  title="Close this pane (and any panes opened from it)"
                >
                  ✕
                </button>
              </div>
              <GraphPane
                target={extra.target}
                onDrilldown={(next, nextTitle) => drillFromPane(i + 1, next, nextTitle)}
              />
            </div>
          </Fragment>
        ))}
      </div>
    </>
  )
}


// ── single graph pane ──────────────────────────────────────────────────


interface GraphPaneProps {
  target: GraphTarget
  /** Called when the user clicks a node that opens a sub-graph. */
  onDrilldown: (next: GraphTarget, title: string) => void
}


function GraphPane({ target, onDrilldown }: GraphPaneProps) {
  const [graph, setGraph] = useState<RunGraphResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openNode, setOpenNode] = useState<RunGraphNode | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | null = null
    setGraph(null)
    setError(null)
    setOpenNode(null)

    const live = isLiveTarget(target)

    async function load() {
      try {
        const g = await fetchRunGraph(target)
        if (cancelled) return
        setGraph(g)
        if (live) {
          const stillRunning = g.nodes.some((n) => n.status === 'running')
          if (stillRunning) {
            timer = window.setTimeout(load, 2000)
          }
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
    }
    load()

    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [JSON.stringify(target)])

  const flow = useMemo(() => graph ? _layout(graph) : { nodes: [], edges: [] }, [graph])

  const onNodeClick = (_: unknown, node: Node) => {
    if (!graph) return
    const found = graph.nodes.find((n) => n.id === node.id)
    if (!found) return

    if (found.kind === 'subject') {
      const sub = found.plugin_name ?? found.id.replace(/^subject:/, '')
      if (target.kind === 'group') {
        onDrilldown(
          {
            kind: 'group-subject',
            groupName: target.groupName,
            runId: target.runId,
            subject: sub,
          },
          `${target.groupName}/${target.runId} · ${sub}`,
        )
        return
      }
      if (target.kind === 'study-group') {
        onDrilldown(
          {
            kind: 'study-group-subject',
            studyName: target.studyName,
            runId: target.runId,
            groupLabel: target.groupLabel,
            subject: sub,
          },
          `${target.studyName}/${target.groupLabel} · ${sub}`,
        )
        return
      }
      if (target.kind === 'in-flight') {
        onDrilldown(
          { kind: 'in-flight-subject', runId: target.runId, subject: sub },
          `live · ${sub}`,
        )
        return
      }
      if (target.kind === 'in-flight-group') {
        onDrilldown(
          {
            kind: 'in-flight-group-subject',
            runId: target.runId,
            groupLabel: target.groupLabel,
            subject: sub,
          },
          `live · ${target.groupLabel} · ${sub}`,
        )
        return
      }
      if (target.kind === 'config') {
        onDrilldown(
          { kind: 'config-subject', filename: target.filename, subject: sub },
          `${target.filename} · ${sub} (preview)`,
        )
        return
      }
    }
    if (found.kind === 'group') {
      const grp = found.plugin_name ?? found.id.replace(/^group:/, '')
      if (target.kind === 'study') {
        onDrilldown(
          {
            kind: 'study-group',
            studyName: target.studyName,
            runId: target.runId,
            groupLabel: grp,
          },
          `${target.studyName}/${target.runId} · ${grp}`,
        )
        return
      }
      if (target.kind === 'in-flight') {
        onDrilldown(
          { kind: 'in-flight-group', runId: target.runId, groupLabel: grp },
          `live · ${grp}`,
        )
        return
      }
    }
    if (found.kind === 'stage') return  // not interactive
    setOpenNode(found)
  }

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
      <div style={{ flex: 1, position: 'relative', minWidth: 0 }}>
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
          // Each pane gets its own ReactFlowProvider so two split
          // panes can render independent graphs side-by-side. A
          // shared provider would cause the second ReactFlow to
          // overwrite the first's internal node store.
          <ReactFlowProvider>
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
          </ReactFlowProvider>
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
  )
}
