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
import { fetchWorkTree } from '../../api/node-outputs'
import type { NipypeNodeStatus, NipypeStatusBlock } from '../../api/types'
import { buildNipypeTree, type NipypeTree, type NipypeTreeNode } from './nipype_tree'
import { allWorkflowIds, filterVisible } from './nipype_tree_filter'
import { partitionLanes, type NipypeLane } from './nipype_lanes'
import { NodeOutputsPanel } from './NodeOutputsPanel'
import { NodeListPanel } from './NodeListPanel'
import { fmriprepDocUrl } from './fmriprep_docs'
import { inferredName } from './fmriprep_labels'
import { useLabelMode, type LabelMode } from './use_label_mode'

const STATUS_COLOR: Record<string, string> = {
  running: '#00e5ff',
  ok: '#00e676',
  failed: '#ff1744',
  completed_assumed: '#52c98f',
  cached: '#888',
}
const NEUTRAL = 'var(--text-secondary)'


// ── Custom nodes ────────────────────────────────────────────────────────


type LeafData = NipypeTreeNode & { _kind: 'leaf' }
type WorkflowData = NipypeTreeNode & {
  _kind: 'workflow'
  /** True if at least one descendant of this workflow is hidden under
   *  the current collapse-by-depth filter. */
  hasHidden?: boolean
  /** True if the user has explicitly expanded this workflow (i.e.
   *  it's in the `expanded` Set). Drives the glyph: '−' if
   *  expanded, '+' if collapsed-and-hiding-something, nothing
   *  otherwise. */
  isExpanded?: boolean
  /** Friendly vs raw label rendering. Injected by the modal so the
   *  node renderer doesn't have to subscribe to the hook. */
  labelMode?: LabelMode
}


function _DocsLinkIcon({ label }: { label: string | undefined }) {
  // Per-node fmriprep docs link. stopPropagation so the click doesn't
  // bubble to the ReactFlow node and trigger the existing
  // open-NodeOutputsPanel handler — left-clicking the link should
  // ONLY open the docs.
  return (
    <a
      href={fmriprepDocUrl(label)}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      title="Open fMRIPrep docs for this node (new tab)"
      style={{
        position: 'absolute',
        top: 1,
        right: 3,
        fontSize: 10,
        fontWeight: 700,
        color: 'var(--text-secondary)',
        textDecoration: 'none',
        opacity: 0.55,
        lineHeight: '12px',
        padding: '0 3px',
        borderRadius: 3,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.opacity = '1'
        e.currentTarget.style.color = 'var(--accent-cyan)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.opacity = '0.55'
        e.currentTarget.style.color = 'var(--text-secondary)'
      }}
    >
      ?
    </a>
  )
}
const DocsLinkIcon = memo(_DocsLinkIcon)


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
      <DocsLinkIcon label={data.label} />
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
  const c = data.counts ?? { running: 0, ok: 0, failed: 0, completed_assumed: 0, cached: 0, total: 0 }
  // Dominant color: failed > running > ok > completed_assumed > cached > neutral.
  const color =
    c.failed > 0 ? STATUS_COLOR.failed
    : c.running > 0 ? STATUS_COLOR.running
    : c.ok > 0 ? STATUS_COLOR.ok
    : c.completed_assumed > 0 ? STATUS_COLOR.completed_assumed
    : c.cached > 0 ? STATUS_COLOR.cached
    : NEUTRAL
  const friendly = inferredName(data.label)
  const mode: LabelMode = data.labelMode ?? 'friendly'
  // Friendly mode promotes the conceptual fmriprep name to the
  // primary label and demotes the raw id to a small subtitle. If we
  // have no curated friendly name for this label, we fall back to
  // the raw id in both modes — we don't invent a name.
  const primary = mode === 'friendly' && friendly ? friendly : data.label
  const secondary = mode === 'friendly'
    ? (friendly ? data.label : null)
    : (friendly ? `[${friendly}]` : null)
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
        cursor: data.isExpanded || data.hasHidden ? 'pointer' : 'default',
      }}
      title={
        data.isExpanded
          ? `${data.id} — click to collapse`
          : data.hasHidden
          ? `${data.id} — click to expand`
          : data.id
      }
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      <DocsLinkIcon label={data.label} />
      {(data.isExpanded || data.hasHidden) && (
        <span
          aria-hidden
          style={{
            position: 'absolute',
            top: 1,
            left: 4,
            fontSize: 12,
            fontWeight: 700,
            color: 'var(--text-secondary)',
            lineHeight: '12px',
            opacity: 0.7,
          }}
        >
          {data.isExpanded ? '−' : '+'}
        </span>
      )}
      <div>
        {primary}
        {secondary && (
          <div
            style={{
              fontSize: 9,
              fontWeight: 500,
              color: 'var(--text-secondary)',
              marginTop: 1,
              fontStyle: mode === 'raw' ? 'italic' : 'normal',
              fontFamily: mode === 'friendly'
                ? "'JetBrains Mono', monospace"
                : undefined,
            }}
          >
            {secondary}
          </div>
        )}
      </div>
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
        {c.completed_assumed > 0 && (
          <span style={{ color: STATUS_COLOR.completed_assumed }}>{c.completed_assumed}?</span>
        )}
        {c.cached > 0 && (
          <span style={{ color: STATUS_COLOR.cached }}>{c.cached}◌</span>
        )}
        {c.total === 0 && <span>—</span>}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  )
}
const WorkflowNode = memo(_WorkflowNodeInner)


// ── Lane group node ─────────────────────────────────────────────────────


type LaneData = { _kind: 'lane'; title: string; counts: NipypeLane['counts'] }


function _LaneNodeInner({ data }: NodeProps & { data: LaneData }) {
  const c = data.counts
  const titleColor =
    c.failed > 0 ? STATUS_COLOR.failed
    : c.running > 0 ? STATUS_COLOR.running
    : c.ok > 0 ? STATUS_COLOR.ok
    : c.completed_assumed > 0 ? STATUS_COLOR.completed_assumed
    : c.cached > 0 ? STATUS_COLOR.cached
    : NEUTRAL
  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        background: 'rgba(26, 26, 46, 0.4)',
        border: '1px dashed var(--border)',
        borderRadius: 8,
        position: 'relative',
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          position: 'absolute', top: 0, left: 0, right: 0,
          padding: '6px 12px',
          fontSize: 11, fontWeight: 700,
          color: titleColor,
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border)',
          borderTopLeftRadius: 7, borderTopRightRadius: 7,
          display: 'flex', justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span>{data.title}</span>
        <span style={{ fontSize: 10, fontWeight: 600, display: 'inline-flex', gap: 6 }}>
          {c.ok > 0 && <span style={{ color: STATUS_COLOR.ok }}>{c.ok}✓</span>}
          {c.running > 0 && <span style={{ color: STATUS_COLOR.running }}>{c.running}▶</span>}
          {c.failed > 0 && <span style={{ color: STATUS_COLOR.failed }}>{c.failed}✗</span>}
          {c.completed_assumed > 0 && (
            <span style={{ color: STATUS_COLOR.completed_assumed }}>{c.completed_assumed}?</span>
          )}
          {c.cached > 0 && (
            <span style={{ color: STATUS_COLOR.cached }}>{c.cached}◌</span>
          )}
        </span>
      </div>
    </div>
  )
}
const LaneNode = memo(_LaneNodeInner)


const nodeTypes = {
  nipype_leaf: LeafNode,
  nipype_workflow: WorkflowNode,
  nipype_lane: LaneNode,
}


// ── Layout ──────────────────────────────────────────────────────────────


const NODE_WIDTH = 150
const NODE_HEIGHT = 56
const LANE_PADDING_X = 24
const LANE_PADDING_TOP = 32
const LANE_PADDING_BOTTOM = 16
const LANE_GAP = 20


/** Lay out a filtered tree as a stack of lane group nodes, each
 *  containing its own dagre-laid-out subgraph.
 *
 *  Cross-lane edges (e.g. `anat_preproc_wf → bold_reg`) are kept but
 *  rendered dashed so they're clearly a shared dependency rather
 *  than a sibling connection.
 */
function _layout(tree: NipypeTree): { nodes: Node[]; edges: Edge[] } {
  const lanes = partitionLanes(tree)
  if (lanes.length === 0) return { nodes: [], edges: [] }

  // Index for O(1) lookups + edge filtering.
  const visibleIds = new Set(tree.nodes.map((n) => n.id))
  const visibleEdges = tree.edges.filter(
    (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
  )
  const nodeById = new Map(tree.nodes.map((n) => [n.id, n]))
  const memberToLane = new Map<string, string>()

  const outNodes: Node[] = []
  let yOffset = 0

  for (const lane of lanes) {
    const memberSet = new Set(lane.memberIds)
    for (const id of lane.memberIds) memberToLane.set(id, lane.id)

    // Per-lane dagre layout in lane-local coordinates.
    const g = new dagre.graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({ rankdir: 'TB', nodesep: 18, ranksep: 36 })
    for (const id of lane.memberIds) {
      g.setNode(id, { width: NODE_WIDTH, height: NODE_HEIGHT })
    }
    for (const e of visibleEdges) {
      if (memberSet.has(e.source) && memberSet.has(e.target)) g.setEdge(e.source, e.target)
    }
    dagre.layout(g)

    // Compute the lane's interior bounding box.
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const id of lane.memberIds) {
      const pos = g.node(id)
      if (!pos) continue
      minX = Math.min(minX, pos.x - NODE_WIDTH / 2)
      maxX = Math.max(maxX, pos.x + NODE_WIDTH / 2)
      minY = Math.min(minY, pos.y - NODE_HEIGHT / 2)
      maxY = Math.max(maxY, pos.y + NODE_HEIGHT / 2)
    }
    if (!isFinite(minX)) { minX = 0; maxX = NODE_WIDTH; minY = 0; maxY = NODE_HEIGHT }
    const innerWidth = Math.max(maxX - minX, NODE_WIDTH)
    const innerHeight = Math.max(maxY - minY, NODE_HEIGHT)
    const laneWidth = innerWidth + LANE_PADDING_X * 2
    const laneHeight = innerHeight + LANE_PADDING_TOP + LANE_PADDING_BOTTOM

    // Emit the lane wrapper FIRST so ReactFlow has it available as
    // the parent when children are added.
    outNodes.push({
      id: lane.id,
      type: 'nipype_lane',
      data: { _kind: 'lane', title: lane.title, counts: lane.counts } as LaneData,
      position: { x: 0, y: yOffset },
      style: { width: laneWidth, height: laneHeight },
      draggable: false,
      selectable: false,
      // Keep the lane behind its children for z-ordering.
      zIndex: 0,
    })

    // Member nodes (workflows + expanded leaves) as children.
    for (const id of lane.memberIds) {
      const node = nodeById.get(id)
      if (!node) continue
      const pos = g.node(id)
      if (!pos) continue
      const localX = pos.x - minX - NODE_WIDTH / 2 + LANE_PADDING_X
      const localY = pos.y - minY - NODE_HEIGHT / 2 + LANE_PADDING_TOP
      outNodes.push({
        id: node.id,
        type: node.kind === 'leaf' ? 'nipype_leaf' : 'nipype_workflow',
        data: { ...node, _kind: node.kind },
        position: { x: localX, y: localY },
        parentId: lane.id,
        extent: 'parent',
        zIndex: 1,
      })
    }

    yOffset += laneHeight + LANE_GAP
  }

  const flowEdges: Edge[] = visibleEdges.map((e) => {
    const sLane = memberToLane.get(e.source)
    const tLane = memberToLane.get(e.target)
    const crossLane = sLane !== tLane
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      style: crossLane
        ? { stroke: 'var(--border)', strokeDasharray: '4 4', opacity: 0.5 }
        : { stroke: 'var(--border)' },
    }
  })

  return { nodes: outNodes, edges: flowEdges }
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

const toolBtn: CSSProperties = {
  padding: '4px 10px',
  fontSize: 11,
  border: '1px solid var(--border)',
  borderRadius: 4,
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
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


function _segmentBtn(active: boolean): CSSProperties {
  return {
    padding: '3px 10px',
    fontSize: 11,
    fontWeight: active ? 700 : 500,
    border: 'none',
    background: active ? 'var(--accent-cyan)' : 'transparent',
    color: active ? 'var(--bg-primary)' : 'var(--text-secondary)',
    cursor: 'pointer',
    transition: 'background 0.12s ease, color 0.12s ease',
  }
}


function LabelModeToggle({ mode, onChange }: { mode: LabelMode; onChange: (m: LabelMode) => void }) {
  return (
    <span
      role="group"
      aria-label="Workflow label mode"
      style={{
        display: 'inline-flex',
        border: '1px solid var(--border)',
        borderRadius: 4,
        overflow: 'hidden',
        background: 'var(--bg-secondary)',
      }}
    >
      <button
        style={_segmentBtn(mode === 'friendly')}
        onClick={() => onChange('friendly')}
        title="Show conceptual fmriprep stage names as the primary label"
        aria-pressed={mode === 'friendly'}
      >
        Friendly
      </button>
      <button
        style={_segmentBtn(mode === 'raw')}
        onClick={() => onChange('raw')}
        title="Show raw nipype workflow ids as the primary label"
        aria-pressed={mode === 'raw'}
      >
        Raw
      </button>
    </span>
  )
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


// Conceptual-view depth: at this depth the visible nodes are fmriprep_wf,
// single_subject_*_wf, and the major named sub-workflows
// (anat_preproc_wf, func_preproc_*_wf, sdc_estimate_wf, ...). User can
// expand individual workflow nodes deeper.
const DEFAULT_VISIBLE_DEPTH = 3


function Inner({ runId, isRunning, onClose }: Props) {
  const [block, setBlock] = useState<NipypeStatusBlock | null>(null)
  const [cachedLeaves, setCachedLeaves] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [openNode, setOpenNode] = useState<string | null>(null)
  // Workflow ids the user has explicitly expanded beyond
  // DEFAULT_VISIBLE_DEPTH. Click on a workflow node toggles
  // membership.
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [labelMode, setLabelMode] = useLabelMode()
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

  // One-shot work_dir walk so cached nodes (no events emitted) still
  // show up in the tree.
  useEffect(() => {
    let cancelled = false
    fetchWorkTree(runId)
      .then((t) => { if (!cancelled) setCachedLeaves(t.leaves) })
      .catch(() => { /* non-fatal */ })
    return () => { cancelled = true }
  }, [runId])

  const mergedNodes = useMemo<NipypeNodeStatus[]>(() => {
    const live = block?.recent_nodes ?? []
    const seen = new Set(live.map((n) => n.node))
    const synthetic: NipypeNodeStatus[] = []
    for (const path of cachedLeaves) {
      if (seen.has(path)) continue
      const segs = path.split('.')
      synthetic.push({
        node: path,
        leaf: segs[segs.length - 1] ?? path,
        workflow: segs.slice(0, -1).join('.'),
        status: 'cached',
        started_at: 0,
        finished_at: 0,
        elapsed: 0,
        crash_file: null,
        level: 'INFO',
      })
    }
    return [...live, ...synthetic]
  }, [block, cachedLeaves])

  // Build the full tree once per data change, then apply the
  // collapse-by-depth filter. Keeping the full tree around lets
  // "Expand all" instantly restore everything without rebuilding.
  const fullTree = useMemo(() => {
    if (mergedNodes.length === 0) return null
    return buildNipypeTree(mergedNodes)
  }, [mergedNodes])

  const flow = useMemo(() => {
    if (!fullTree) return { nodes: [] as Node[], edges: [] as Edge[] }
    const { tree, hasHidden } = filterVisible(fullTree, DEFAULT_VISIBLE_DEPTH, expanded)
    const laid = _layout(tree)
    // Inject hasHidden + isExpanded into the workflow nodes' data
    // payload so the WorkflowNode renderer can show the +/− glyph
    // without re-deriving the state.
    const nodes = laid.nodes.map((n) => {
      if (n.type !== 'nipype_workflow') return n
      return {
        ...n,
        data: {
          ...(n.data as object),
          hasHidden: hasHidden.get(n.id) ?? false,
          isExpanded: expanded.has(n.id),
          labelMode,
        },
      }
    })
    return { nodes, edges: laid.edges }
  }, [fullTree, expanded, labelMode])

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
        {fullTree && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <LabelModeToggle mode={labelMode} onChange={setLabelMode} />
            <button
              style={toolBtn}
              onClick={() => setExpanded(new Set(allWorkflowIds(fullTree)))}
              title={`Show every nipype node (default depth ${DEFAULT_VISIBLE_DEPTH} = conceptual workflows only)`}
            >
              Expand all
            </button>
            <button
              style={{ ...toolBtn, opacity: expanded.size === 0 ? 0.5 : 1 }}
              onClick={() => setExpanded(new Set())}
              disabled={expanded.size === 0}
              title={`Collapse back to the conceptual view (depth ${DEFAULT_VISIBLE_DEPTH})`}
            >
              Collapse all
            </button>
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
          nodes={mergedNodes}
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
              const data = n.data as unknown as NipypeTreeNode & {
                _kind?: string
                hasHidden?: boolean
                isExpanded?: boolean
              }
              const kind = data._kind ?? data.kind
              if (kind === 'leaf') {
                setOpenNode(data.full_node ?? data.id)
                return
              }
              if (kind === 'workflow') {
                // Toggle expansion. No-op if there's nothing hidden
                // below AND the node isn't currently expanded (the
                // user's click would have no visible effect either way).
                if (!data.hasHidden && !data.isExpanded) return
                setExpanded((prev) => {
                  const next = new Set(prev)
                  if (next.has(n.id)) next.delete(n.id)
                  else next.add(n.id)
                  return next
                })
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
