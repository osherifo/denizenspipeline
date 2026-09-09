/** Modal showing the live nipype DAG (tree-from-paths) for a Preproc run. */

import { memo, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  Position,
  Handle,
  useReactFlow,
  useNodesState,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react'
import dagre from 'dagre'

import { fetchPreprocRunLive, fetchLabelMap } from '../../api/client'
import { fetchRunNodeInner } from '../../api/preproc'
import { fetchWorkTree } from '../../api/node-outputs'
import { formatDuration } from '../../utils/format'
import type { NipypeNodeStatus, NipypeStatusBlock } from '../../api/types'
import { buildNipypeTree, type NipypeTree, type NipypeTreeNode } from './nipype_tree'
import { allWorkflowIds, filterVisible } from './nipype_tree_filter'
import { partitionLanes, type NipypeLane } from './nipype_lanes'
import { NodeOutputsPanel } from './NodeOutputsPanel'
import { NodeListPanel } from './NodeListPanel'
import { fmriprepDocUrl } from './fmriprep_docs'
import { inferredName, setRuntimeMap } from './fmriprep_labels'
import { useLabelMode, type LabelMode } from './use_label_mode'
import { nodeColors, statusPalette, runningNodeStyle } from '../../utils/status-colors'
import { useThemeStore } from '../../stores/theme-store'

// Status colours come from the shared theme-aware palette so light mode
// gets legible equivalents; called per paint to track theme switches.
const STATUS = () => statusPalette()
const NEUTRAL = 'var(--text-secondary)'


// ── Custom nodes ────────────────────────────────────────────────────────


type LeafData = NipypeTreeNode & { _kind: 'leaf'; showDocs?: boolean }
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
  /** Docs link icon only when the label family has docs (fmriprep). */
  showDocs?: boolean
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
  // `mode` doubles as the theme subscription that repaints this memoised node.
  const mode = useThemeStore((s) => s.mode)
  // `completed_assumed`/`cached` aren't in the shared table; fall back to the
  // local neon map in dark, and to the shared neutral in light.
  const themed = nodeColors(mode, data.status ?? '')
  const color = mode === 'light' ? themed.color : (STATUS()[data.status ?? ''] ?? NEUTRAL)
  const elapsed = data.elapsed && data.elapsed > 0
    ? ` · ${formatDuration(data.elapsed)}`
    : ''
  const w = (data as Record<string, unknown>)._allocatedWidth as number | undefined
  return (
    <div
      style={{
        background: themed.bg,
        border: `${themed.borderWidth}px solid ${themed.border}`,
        ...runningNodeStyle(themed),
        color: 'var(--text-primary)',
        borderRadius: 5,
        padding: '4px 8px',
        fontSize: 11,
        fontWeight: 600,
        width: w ? w - 2 : undefined,
        minWidth: 110,
        textAlign: 'center',
        position: 'relative',
        overflow: 'hidden',
        boxSizing: 'border-box',
      }}
      title={`${data.full_node ?? data.id} — ${data.status ?? ''}${elapsed}`}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      {data.showDocs !== false && <DocsLinkIcon label={data.label} />}
      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{data.label}</div>
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
    c.failed > 0 ? STATUS().failed
    : c.running > 0 ? STATUS().running
    : c.ok > 0 ? STATUS().ok
    : c.completed_assumed > 0 ? STATUS().completed_assumed
    : c.cached > 0 ? STATUS().cached
    : NEUTRAL
  const friendly = inferredName(data.label)
  const mode: LabelMode = data.labelMode ?? 'friendly'
  const primary = mode === 'friendly' && friendly ? friendly : data.label
  const secondary = mode === 'friendly'
    ? (friendly ? data.label : null)
    : (friendly ? `[${friendly}]` : null)
  const w = (data as Record<string, unknown>)._allocatedWidth as number | undefined
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
        width: w ? w - 2 : undefined,
        minWidth: 130,
        textAlign: 'center',
        position: 'relative',
        overflow: 'hidden',
        boxSizing: 'border-box',
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
      {data.showDocs !== false && <DocsLinkIcon label={data.label} />}
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
      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {primary}
      </div>
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
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {secondary}
        </div>
      )}
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
        {c.ok > 0 && <span style={{ color: STATUS().ok }}>{c.ok}✓</span>}
        {c.failed > 0 && <span style={{ color: STATUS().failed }}>{c.failed}✗</span>}
        {c.completed_assumed > 0 && (
          <span style={{ color: STATUS().completed_assumed }}>{c.completed_assumed}?</span>
        )}
        {c.cached > 0 && (
          <span style={{ color: STATUS().cached }}>{c.cached}◌</span>
        )}
        {c.total === 0 && <span>—</span>}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  )
}
const WorkflowNode = memo(_WorkflowNodeInner)


const nodeTypes = {
  nipype_leaf: LeafNode,
  nipype_workflow: WorkflowNode,
}


// ── Layout ──────────────────────────────────────────────────────────────


const NODE_MIN_WIDTH = 140
const NODE_HEIGHT = 56
const CHAR_WIDTH = 7.5
const NODE_H_PAD = 40

function _estimateNodeWidth(node: NipypeTreeNode): number {
  const friendly = inferredName(node.label)
  const primary = friendly ?? node.label
  const secondary = friendly ? node.label : ''
  const longest = Math.max(primary.length, secondary.length)
  return Math.max(NODE_MIN_WIDTH, longest * CHAR_WIDTH + NODE_H_PAD)
}


/** Iterative AABB push-apart collision resolver (ReactFlow pattern).
 *  Mutates node positions in place. */
const COLLISION_MARGIN = 20
const COLLISION_MAX_ITER = 50

function _resolveCollisions(nodes: Node[]): void {
  for (let iter = 0; iter < COLLISION_MAX_ITER; iter++) {
    let moved = false
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]
        const b = nodes[j]
        const aw = (a.width ?? NODE_MIN_WIDTH) + COLLISION_MARGIN
        const ah = (a.height ?? NODE_HEIGHT) + COLLISION_MARGIN
        const bw = (b.width ?? NODE_MIN_WIDTH) + COLLISION_MARGIN
        const bh = (b.height ?? NODE_HEIGHT) + COLLISION_MARGIN

        const acx = a.position.x + aw / 2
        const acy = a.position.y + ah / 2
        const bcx = b.position.x + bw / 2
        const bcy = b.position.y + bh / 2

        const dx = bcx - acx
        const dy = bcy - acy
        const overlapX = (aw + bw) / 2 - Math.abs(dx)
        const overlapY = (ah + bh) / 2 - Math.abs(dy)

        if (overlapX > 0.5 && overlapY > 0.5) {
          moved = true
          if (overlapX < overlapY) {
            const shift = overlapX / 2
            const sign = dx >= 0 ? 1 : -1
            a.position.x -= shift * sign
            b.position.x += shift * sign
          } else {
            const shift = overlapY / 2
            const sign = dy >= 0 ? 1 : -1
            a.position.y -= shift * sign
            b.position.y += shift * sign
          }
        }
      }
    }
    if (!moved) break
  }
}


/** Lane id sentinel for the "show all lanes" selector option. */
export const SHOW_ALL_LANES = 'all'


/** Walk up the dotted-path hierarchy and add every ancestor id (down
 *  to but excluding the root segment, since the root IS the top).
 *  Used to keep `fmriprep_wf` and `single_subject_*_wf` always
 *  visible at the top of the canvas even when the user has focused
 *  on a single run/lane below them. */
function _addAncestors(id: string, out: Set<string>): void {
  const segs = id.split('.')
  for (let i = 1; i < segs.length; i++) {
    out.add(segs.slice(0, i).join('.'))
  }
}


/** Lay out a filtered tree as a single dagre TB graph. When
 *  `selectedLane` is set to a real lane id, only that lane's
 *  members (plus the always-visible ancestor chain) are kept. When
 *  it's `SHOW_ALL_LANES`, every visible node is laid out together.
 *
 *  No ReactFlow parent/child group nodes are used — the lane
 *  selector handles separation by FILTERING rather than visually
 *  wrapping.
 */
function _layout(
  tree: NipypeTree,
  lanes: NipypeLane[],
  selectedLane: string,
): { nodes: Node[]; edges: Edge[] } {
  if (tree.nodes.length === 0) return { nodes: [], edges: [] }

  const focusLanes = selectedLane === SHOW_ALL_LANES
    ? lanes
    : lanes.filter((l) => l.id === selectedLane)

  // Build the visible-id set: every focus-lane member + every
  // ancestor up the dotted path (fmriprep_wf, single_subject_*_wf).
  const includeIds = new Set<string>()
  for (const lane of focusLanes) {
    for (const id of lane.memberIds) {
      includeIds.add(id)
      _addAncestors(id, includeIds)
    }
  }
  // If the focus is "all" but no lanes exist (empty / non-fmriprep
  // edge), fall back to every visible node so we still render
  // something.
  if (includeIds.size === 0) {
    for (const n of tree.nodes) includeIds.add(n.id)
  }

  const nodeById = new Map(tree.nodes.map((n) => [n.id, n]))
  const visibleNodes = Array.from(includeIds)
    .map((id) => nodeById.get(id))
    .filter((n): n is NipypeTreeNode => !!n)
  const visibleIdSet = new Set(visibleNodes.map((n) => n.id))
  const visibleEdges = tree.edges.filter(
    (e) => visibleIdSet.has(e.source) && visibleIdSet.has(e.target),
  )

  const nodeWidths = new Map<string, number>()
  for (const nd of visibleNodes) nodeWidths.set(nd.id, _estimateNodeWidth(nd))

  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60 })
  for (const nd of visibleNodes) g.setNode(nd.id, { width: nodeWidths.get(nd.id)!, height: NODE_HEIGHT })
  for (const e of visibleEdges) g.setEdge(e.source, e.target)
  dagre.layout(g)

  const flowNodes: Node[] = visibleNodes.map((nd) => {
    const pos = g.node(nd.id) ?? { x: 0, y: 0 }
    const w = nodeWidths.get(nd.id)!
    return {
      id: nd.id,
      type: nd.kind === 'leaf' ? 'nipype_leaf' : 'nipype_workflow',
      data: { ...nd, _kind: nd.kind, _allocatedWidth: w },
      position: { x: pos.x - w / 2, y: pos.y - NODE_HEIGHT / 2 },
      width: w,
      height: NODE_HEIGHT,
    }
  })

  const flowEdges: Edge[] = visibleEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
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


function _laneChipStyle(active: boolean): CSSProperties {
  return {
    padding: '4px 10px',
    fontSize: 11,
    fontWeight: active ? 700 : 500,
    border: active ? '1px solid var(--accent-cyan)' : '1px solid var(--border)',
    background: active ? 'rgba(0, 229, 255, 0.12)' : 'var(--bg-secondary)',
    color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
    borderRadius: 999,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'background 0.12s ease, color 0.12s ease, border-color 0.12s ease',
  }
}


function LaneSelector({
  lanes,
  selected,
  onSelect,
}: {
  lanes: NipypeLane[]
  selected: string
  onSelect: (id: string) => void
}) {
  if (lanes.length <= 1) return null
  return (
    <div
      role="tablist"
      aria-label="Lane selector"
      style={{
        display: 'flex', gap: 6, flexWrap: 'wrap',
        padding: '6px 0',
        borderBottom: '1px solid var(--border)',
        marginBottom: 6,
      }}
    >
      <button
        role="tab"
        aria-selected={selected === SHOW_ALL_LANES}
        style={_laneChipStyle(selected === SHOW_ALL_LANES)}
        onClick={() => onSelect(SHOW_ALL_LANES)}
        title="Show every lane in one canvas"
      >
        All lanes
      </button>
      {lanes.map((l) => (
        <button
          key={l.id}
          role="tab"
          aria-selected={selected === l.id}
          style={_laneChipStyle(selected === l.id)}
          onClick={() => onSelect(l.id)}
          title={`Focus on ${l.title}`}
        >
          {l.title}
          {l.counts.total > 0 && (
            <span style={{
              marginLeft: 6,
              fontSize: 9,
              opacity: 0.7,
              fontWeight: 600,
            }}>
              {l.counts.total}
            </span>
          )}
        </button>
      ))}
    </div>
  )
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

export interface NipypeDagPanelProps {
  runId: string
  isRunning: boolean
  /** Restrict to one outer pipeline node's inner subtree (its `<workflow>.<nodeId>.` prefix
   *  is stripped, so the app's own top-level workflow is the root). Absent = the whole run. */
  nodePath?: { workflow: string | null; nodeId: string }
  /** Friendly-label family for inner nodes; null/undefined = raw names, no docs links. */
  labelFamily?: string | null
  /** Label-map version (fmriprep major), default '25'. */
  labelVersion?: string
  /** Rendered as a Close button when given. */
  onClose?: () => void
}


/** The whole-run DAG in a modal (the Workflows view). */
export function NipypeGraphModal({ runId, isRunning, onClose }: Props) {
  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <ReactFlowProvider>
          <Inner runId={runId} isRunning={isRunning} onClose={onClose} labelFamily="fmriprep" />
        </ReactFlowProvider>
      </div>
    </div>
  )
}

/** The DAG as an embeddable panel (fills its parent; the node popup's Inner DAG tab). */
export function NipypeDagPanel(props: NipypeDagPanelProps) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  )
}


// Conceptual-view depth: at this depth the visible nodes are fmriprep_wf,
// single_subject_*_wf, and the major named sub-workflows
// (anat_preproc_wf, func_preproc_*_wf, sdc_estimate_wf, ...). User can
// expand individual workflow nodes deeper.
const DEFAULT_VISIBLE_DEPTH = 3


function Inner({ runId, isRunning, onClose, nodePath, labelFamily, labelVersion }: NipypeDagPanelProps) {
  // Per-node view: events and work-tree leaves are filtered to this prefix server-side.
  const prefix = nodePath ? `${nodePath.workflow ? `${nodePath.workflow}.` : ''}${nodePath.nodeId}.` : null
  const hasDocs = labelFamily === 'fmriprep'
  const [block, setBlock] = useState<NipypeStatusBlock | null>(null)
  const [cachedLeaves, setCachedLeaves] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [openNode, setOpenNode] = useState<string | null>(null)
  // Workflow ids the user has explicitly expanded beyond
  // DEFAULT_VISIBLE_DEPTH. Click on a workflow node toggles
  // membership.
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [storedLabelMode, setLabelMode] = useLabelMode()
  const labelMode: LabelMode = labelFamily ? storedLabelMode : 'raw'
  // Lane focus: SHOW_ALL_LANES = render every lane (the default
  // overview), else a specific lane id (e.g. 'lane:run-1') filters
  // the canvas to that lane + the ancestor chain.
  const [selectedLane, setSelectedLane] = useState<string>(SHOW_ALL_LANES)
  const [sidebarWidth, setSidebarWidth] = useState(280)
  const rf = useReactFlow()

  const handlePanTo = (nodeId: string) => {
    setTimeout(() => {
      try {
        const node = rf.getNode(nodeId)
        if (!node) return
        const zoom = rf.getZoom()
        rf.setCenter(
          node.position.x + (node.measured?.width ?? node.width ?? 150) / 2,
          node.position.y + (node.measured?.height ?? node.height ?? 56) / 2,
          { zoom, duration: 300 },
        )
      } catch { /* ignore */ }
    }, 60)
  }

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = sidebarWidth
    const onMove = (ev: MouseEvent) => {
      setSidebarWidth(Math.max(160, Math.min(600, startW + ev.clientX - startX)))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  // When the user selects a leaf (via list or graph click), pan to
  // centre that node without changing zoom.
  useEffect(() => {
    if (!openNode) return
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

  // When a workflow node is expanded/collapsed, keep the viewport
  // centred on the node the user clicked instead of refitting.
  const lastExpandToggle = useRef<string | null>(null)
  useEffect(() => {
    const target = lastExpandToggle.current
    if (!target) return
    lastExpandToggle.current = null
    const t = setTimeout(() => {
      try {
        const node = rf.getNode(target)
        if (!node) return
        const zoom = rf.getZoom()
        rf.setCenter(
          node.position.x + (node.measured?.width ?? 150) / 2,
          node.position.y + (node.measured?.height ?? 56) / 2,
          { zoom, duration: 200 },
        )
      } catch { /* ignore */ }
    }, 50)
    return () => clearTimeout(t)
  }, [expanded, rf])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const status = prefix
          ? (await fetchRunNodeInner(runId, nodePath!.nodeId, 500)).nipype_status
          : (await fetchPreprocRunLive(runId, 500)).nipype_status
        if (!cancelled) {
          setBlock(status)
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
  }, [runId, isRunning, prefix])  // eslint-disable-line react-hooks/exhaustive-deps

  // One-shot work_dir walk so cached nodes (no events emitted) still
  // show up in the tree.
  useEffect(() => {
    let cancelled = false
    fetchWorkTree(runId, prefix ?? undefined)
      .then((t) => { if (!cancelled) setCachedLeaves(t.leaves) })
      .catch(() => { /* non-fatal */ })
    return () => { cancelled = true }
  }, [runId, prefix])

  // Load the version-specific label map from the backend so friendly
  // names stay correct across fmriprep upgrades. Falls back to the
  // embedded v25 map on failure.
  useEffect(() => {
    if (!hasDocs) return
    fetchLabelMap(labelVersion ?? '25')
      .then((r) => setRuntimeMap(r.labels))
      .catch(() => { /* non-fatal — embedded fallback */ })
  }, [hasDocs, labelVersion])

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

  // Compute lanes once per filtered-tree change. The selector pulls
  // its options from this list, and `_layout` filters by the active
  // lane id.
  const filterResult = useMemo(() => {
    if (!fullTree) return null
    return filterVisible(fullTree, DEFAULT_VISIBLE_DEPTH, expanded)
  }, [fullTree, expanded])

  const lanes = useMemo<NipypeLane[]>(() => {
    if (!filterResult) return []
    return partitionLanes(filterResult.tree)
  }, [filterResult])

  // If the currently-selected lane no longer exists (e.g. expansion
  // changed which lanes are populated, or we switched runs and the
  // stored id is stale), reset to the overview.
  useEffect(() => {
    if (selectedLane === SHOW_ALL_LANES) return
    if (!lanes.some((l) => l.id === selectedLane)) setSelectedLane(SHOW_ALL_LANES)
  }, [lanes, selectedLane])

  const prevPositions = useRef<Map<string, { x: number; y: number }>>(new Map())

  const flow = useMemo(() => {
    if (!filterResult) return { nodes: [] as Node[], edges: [] as Edge[] }
    const laid = _layout(filterResult.tree, lanes, selectedLane)

    // Stabilize: nodes that existed in the previous layout keep their
    // x-position within the same rank so expanding a single workflow
    // doesn't rearrange unrelated siblings.
    const prev = prevPositions.current
    if (prev.size > 0) {
      // Group new layout nodes by rank (y)
      const byRank = new Map<number, typeof laid.nodes>()
      for (const n of laid.nodes) {
        const list = byRank.get(n.position.y) ?? []
        list.push(n)
        byRank.set(n.position.y, list)
      }
      for (const [, rankNodes] of byRank) {
        // Only stabilize ranks where every node existed before.
        // Ranks with new nodes get dagre's layout as-is to avoid
        // swapping a returning node into a position that overlaps
        // with a newly inserted child.
        const hasNewNodes = rankNodes.some((n) => !prev.has(n.id))
        if (hasNewNodes) continue
        const returning = rankNodes
        if (returning.length < 2) continue
        const newXs = returning.map((n) => n.position.x).sort((a, b) => a - b)
        returning.sort((a, b) => prev.get(a.id)!.x - prev.get(b.id)!.x)
        for (let i = 0; i < returning.length; i++) {
          returning[i].position.x = newXs[i]
        }
      }
    }

    // Resolve any overlaps introduced by stabilization or dagre.
    _resolveCollisions(laid.nodes)

    // Save positions for next render
    const next = new Map<string, { x: number; y: number }>()
    for (const n of laid.nodes) next.set(n.id, { x: n.position.x, y: n.position.y })
    prevPositions.current = next

    // Inject hasHidden + isExpanded into the workflow nodes' data
    // payload so the WorkflowNode renderer can show the +/− glyph
    // without re-deriving the state.
    const nodes = laid.nodes.map((n) => {
      if (n.type !== 'nipype_workflow') return { ...n, data: { ...(n.data as object), showDocs: hasDocs } }
      return {
        ...n,
        data: {
          ...(n.data as object),
          hasHidden: filterResult.hasHidden.get(n.id) ?? false,
          isExpanded: expanded.has(n.id),
          labelMode,
          showDocs: hasDocs,
        },
      }
    })
    return { nodes, edges: laid.edges }
  }, [filterResult, lanes, selectedLane, expanded, labelMode, hasDocs])

  // useNodesState makes dragging work — it tracks position changes
  // from user drags while still accepting layout-computed positions
  // when the graph changes (expand/collapse/new data).
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState(flow.nodes)
  useEffect(() => { setRfNodes(flow.nodes) }, [flow.nodes, setRfNodes])

  // Initial fit: fit the whole graph once when nodes first appear,
  // but not on subsequent layout changes (expand/collapse).
  const didInitialFit = useRef(false)
  useEffect(() => {
    if (rfNodes.length === 0 || didInitialFit.current) return
    didInitialFit.current = true
    const t = setTimeout(() => {
      try { rf.fitView({ duration: 300, padding: 0.2 }) }
      catch { /* ignore */ }
    }, 50)
    return () => clearTimeout(t)
  }, [flow.nodes.length, rf])

  return (
    <>
      <div style={header}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>nipype DAG</div>
        <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{nodePath ? nodePath.nodeId : runId}</code>
        {block && (
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            {block.counts.running} running · {block.counts.ok} done · {block.counts.failed} failed{block.counts.completed_assumed ? ` · ${block.counts.completed_assumed} assumed` : ''} · {block.counts.total_seen} seen
          </span>
        )}
        {isRunning && (
          <span style={{
            fontSize: 10, color: STATUS().running, fontWeight: 700,
            padding: '2px 6px', borderRadius: 8,
            background: `${STATUS().running}22`,
            border: `1px solid ${STATUS().running}55`,
          }}>
            LIVE
          </span>
        )}
        {fullTree && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            {labelFamily && <LabelModeToggle mode={labelMode} onChange={setLabelMode} />}
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
        {onClose && <button style={closeBtn} onClick={onClose}>Close</button>}
      </div>
      <LaneSelector lanes={lanes} selected={selectedLane} onSelect={setSelectedLane} />
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
          onPanTo={handlePanTo}
          labelMode={labelMode}
          width={sidebarWidth}
          onResizeStart={handleResizeStart}
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
        {rfNodes.length > 0 && (
          <ReactFlow
            nodes={rfNodes}
            edges={flow.edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onNodeDragStop={() => {
              setRfNodes((prev) => {
                const copy = prev.map((n) => ({ ...n, position: { ...n.position } }))
                _resolveCollisions(copy)
                return copy
              })
            }}
            nodesDraggable={true}
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
                lastExpandToggle.current = n.id
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
            node={prefix ? `${prefix}${openNode}` : openNode}
            onClose={() => setOpenNode(null)}
          />
        )}
      </div>
    </>
  )
}
