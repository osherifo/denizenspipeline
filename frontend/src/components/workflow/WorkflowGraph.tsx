/** ReactFlow graph for a single workflow run — one node per stage. */
import { statusPalette, identityColor, nodeColors, runningNodeStyle } from '../../utils/status-colors'
import { memo, useEffect, useMemo, useRef } from 'react'
import type { CSSProperties } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Controls,
  Handle,
  Position,
  useNodesState,
  useReactFlow,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useThemeStore } from '../../stores/theme-store'
import type { WorkflowStageStatus } from '../../api/types'
import { InnerNodesStrip } from './InnerNodesStrip'

// ── Stage metadata ──────────────────────────────────────────────────────

const STAGE_META: Record<string, { color: string; icon: string; label: string }> = {
  convert:     { color: '#3b82f6', icon: '\u{1F504}', label: 'Convert' },
  preproc:     { color: '#10b981', icon: '\u{2699}',  label: 'Preproc' },
  autoflatten: { color: '#14b8a6', icon: '\u{1F9E0}', label: 'Autoflatten' },
  post_preproc:{ color: '#10b981', icon: '\u{1F300}', label: 'Post-preproc' },
  analysis:    { color: '#ef4444', icon: '\u{1F4CA}', label: 'Analysis' },
}

// Status colours come from the shared theme-aware palette so light mode
// gets legible equivalents; called per paint to track theme switches.
const STATUS = () => statusPalette()

// Canonical order of analysis inner stages — used to stub out pending
// rows when the events file doesn't list them yet.
const ANALYSIS_INNER_STAGES: readonly string[] = [
  'stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report',
] as const

// ── Node component ──────────────────────────────────────────────────────

type StageNodeData = WorkflowStageStatus & {
  index: number
  isFirst: boolean
  isLast: boolean
  onOpenNipypeDag?: () => void
  onOpenBackendNode?: () => void
  onOpenConvertDecisions?: () => void
}

/** Drill-in button on a finished stage node. */
const stageActionButton = (color: string): CSSProperties => ({
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 0.5,
  borderRadius: 4,
  background: `${color}33`,
  color,
  border: `1px solid ${color}88`,
  cursor: 'pointer',
  textTransform: 'uppercase',
})

const nodeBase: CSSProperties = {
  borderRadius: 8,
  padding: '12px 16px',
  minWidth: 230,
  fontSize: 11,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-card)',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginBottom: 8,
}

const labelStyle: CSSProperties = {
  fontWeight: 700,
  fontSize: 12,
  flex: 1,
  letterSpacing: 0.5,
  textTransform: 'uppercase',
}

const statusBadge = (color: string, running = false): CSSProperties => ({
  fontSize: 10,
  fontWeight: 700,
  padding: '2px 8px',
  borderRadius: 4,
  // A running node's badge is filled rather than tinted, so the state is
  // legible even at the zoom levels where the glow washes out.
  backgroundColor: running ? color : `${color}22`,
  color: running ? 'var(--on-accent)' : color,
  border: `1px solid ${running ? color : `${color}66`}`,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
})

const metaLine: CSSProperties = {
  color: 'var(--text-secondary)',
  fontFamily: 'monospace',
  fontSize: 10,
  lineHeight: 1.5,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const errorLine: CSSProperties = {
  color: 'var(--accent-red)',
  fontFamily: 'monospace',
  fontSize: 10,
  marginTop: 6,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  maxHeight: 60,
  overflow: 'auto',
}

const handleStyle = (color: string): CSSProperties => ({
  width: 8,
  height: 8,
  backgroundColor: color,
  border: '2px solid var(--bg-primary)',
  borderRadius: '50%',
})

function fmtElapsed(s: WorkflowStageStatus): string {
  if (!s.started_at) return ''
  const end = s.status === 'running' ? Date.now() / 1000 : s.finished_at
  const sec = Math.max(0, end - s.started_at)
  if (sec < 60) return `${Math.round(sec)}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
  return `${Math.floor(sec / 3600)}h ${Math.round((sec % 3600) / 60)}m`
}

function WorkflowStageNodeInner({ data }: NodeProps & { data: StageNodeData }) {
  // `mode` doubles as the theme subscription that repaints this memoised node.
  const mode = useThemeStore((s) => s.mode)
  const rawMeta = STAGE_META[data.stage] ?? { color: 'var(--text-secondary)', icon: '\u{25CF}', label: data.stage }
  // Stage hues are identity, not decoration — darken (not replace) them for light.
  const meta = { ...rawMeta, color: identityColor(rawMeta.color) }
  const statusColor = STATUS()[data.status] ?? STATUS().pending
  const isRunning = data.status === 'running'

  const clickable = !!data.run_id
  const themed = nodeColors(mode, data.status)
  const style: CSSProperties = {
    ...nodeBase,
    border: isRunning
      ? `${themed.borderWidth}px solid ${statusColor}`
      : `1px solid ${meta.color}55`,
    boxShadow: isRunning ? themed.glow : `0 1px 3px rgba(0,0,0,0.3)`,
    // Running nodes also get the shared pulse; the old bespoke keyframes baked
    // in a dark-mode colour and washed out on a light canvas.
    ...runningNodeStyle(themed),
    cursor: clickable ? 'pointer' : 'default',
  }

  const elapsed = fmtElapsed(data)
  const configFile = data.config.split('/').pop() || data.config

  return (
    <div style={style}>
      {!data.isFirst && (
        <Handle
          type="target"
          position={Position.Left}
          style={handleStyle(meta.color)}
        />
      )}

      <div style={headerStyle}>
        <span style={{ fontSize: 14 }}>{meta.icon}</span>
        <span style={{ ...labelStyle, color: meta.color }}>{meta.label}</span>
        <span style={statusBadge(statusColor, isRunning)}>{data.status}</span>
      </div>

      <div style={metaLine} title={data.config}>
        {configFile}
      </div>
      {elapsed && (
        <div style={metaLine}>
          {isRunning ? '⏱' : '✓'} {elapsed}
        </div>
      )}
      {data.run_id && (
        <div style={metaLine} title={data.run_id}>
          {data.run_id}
        </div>
      )}
      {data.error && <div style={errorLine}>{data.error}</div>}

      {data.stage === 'analysis' && data.inner_stages && data.inner_stages.length > 0 && (
        <InnerStagesStrip inner={data.inner_stages} />
      )}

      {data.stage === 'preproc' && data.nipype_status &&
        data.nipype_status.counts.total_seen > 0 && (
          <InnerNodesStrip
            block={data.nipype_status}
            onOpenDag={data.onOpenNipypeDag}
          />
        )}

      {data.stage === 'convert' && data.status === 'done' &&
        data.onOpenConvertDecisions && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                data.onOpenConvertDecisions?.()
              }}
              style={stageActionButton(meta.color)}
            >
              DICOM decisions →
            </button>
          </div>
        )}

      {data.stage === 'preproc' && (data.status === 'done' || data.status === 'running' || data.status === 'failed') &&
        data.onOpenBackendNode && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                data.onOpenBackendNode?.()
              }}
              style={stageActionButton(meta.color)}
            >
              Backend node →
            </button>
          </div>
        )}

      {clickable && (
        <div style={{
          fontSize: 9, color: meta.color, marginTop: 6,
          letterSpacing: 0.5, fontWeight: 600,
        }}>
          click for log →
        </div>
      )}

      {!data.isLast && (
        <Handle
          type="source"
          position={Position.Right}
          style={handleStyle(meta.color)}
        />
      )}
    </div>
  )
}

const WorkflowStageNode = memo(WorkflowStageNodeInner)
const nodeTypes = { workflowStage: WorkflowStageNode }

// ── Inner-stage strip (for the analysis node) ──────────────────────────

import type { AnalysisInnerStage } from '../../api/types'

const innerStripContainer: CSSProperties = {
  marginTop: 8,
  padding: '6px 8px',
  borderRadius: 5,
  border: '1px solid rgba(255,255,255,0.05)',
  backgroundColor: 'rgba(0,0,0,0.25)',
  display: 'grid',
  gridTemplateColumns: 'repeat(7, 1fr)',
  gap: 3,
}

const innerPill = (color: string, isRunning: boolean): CSSProperties => ({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  padding: '3px 2px',
  borderRadius: 3,
  backgroundColor: isRunning ? `${color}22` : 'transparent',
  border: `1px solid ${color}55`,
})

const innerPillLabel: CSSProperties = {
  fontSize: 8,
  letterSpacing: 0.3,
  fontWeight: 700,
  textTransform: 'uppercase',
  lineHeight: 1.2,
}

const innerPillDot = (color: string): CSSProperties => ({
  width: 6, height: 6, borderRadius: '50%', backgroundColor: color,
  marginTop: 2,
})

function InnerStagesStrip({ inner }: { inner: AnalysisInnerStage[] }) {
  // Subscribe to the theme so a toggle repaints the status colours read
  // via STATUS() below (this component is memoised).
  useThemeStore((s) => s.mode)
  // Build a map from parsed events, then project onto the canonical
  // 7-stage layout so pending stages show up as ghost pills.
  const byName = new Map<string, AnalysisInnerStage>()
  for (const s of inner) byName.set(s.stage, s)

  // The last 'running' stage in pipeline order is the truly active
  // one (orchestrator runs strictly sequentially; an earlier 'running'
  // without a matching stage_done means a lost write, so we downgrade
  // to 'ok' visually since the pipeline has moved past it).
  let activeIdx = -1
  ANALYSIS_INNER_STAGES.forEach((name, i) => {
    const s = byName.get(name)
    if (s && s.status === 'running') activeIdx = i
  })

  return (
    <div style={innerStripContainer} title="Pipeline sub-stages">
      {ANALYSIS_INNER_STAGES.map((name, i) => {
        const s = byName.get(name)
        const rawStatus = s?.status ?? 'pending'
        const status =
          rawStatus === 'running' && i < activeIdx ? 'ok' : rawStatus
        const color = STATUS()[status] ?? STATUS().pending
        return (
          <div key={name} style={innerPill(color, status === 'running')}>
            <span style={{ ...innerPillLabel, color }}>{name.slice(0, 4)}</span>
            <span style={innerPillDot(color)} />
          </div>
        )
      })}
    </div>
  )
}

// ── Main graph component ───────────────────────────────────────────────

const GRAPH_STYLE: CSSProperties = {
  width: '100%',
  height: 220,
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  border: '1px solid var(--border)',
}

// Both, so the modifier is whatever the platform's users reach for:
// Control on Windows/Linux, Meta (Cmd) on macOS.
const ZOOM_KEYS = ['Control', 'Meta']

const NODE_SPACING_X = 280
const NODE_GAP_X = 60
const NODE_Y = 40

function buildGraph(
  stages: WorkflowStageStatus[],
  onOpenNipypeDag?: (stage: WorkflowStageStatus) => void,
  onOpenBackendNode?: (stage: WorkflowStageStatus) => void,
  onOpenConvertDecisions?: (stage: WorkflowStageStatus) => void,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = stages.map((s, i) => ({
    id: `stage-${i}-${s.stage}`,
    type: 'workflowStage',
    position: { x: i * NODE_SPACING_X, y: NODE_Y },
    data: {
      ...s,
      index: i,
      isFirst: i === 0,
      isLast: i === stages.length - 1,
      onOpenNipypeDag:
        s.stage === 'preproc' && onOpenNipypeDag
          ? () => onOpenNipypeDag(s)
          : undefined,
      onOpenBackendNode:
        s.stage === 'preproc' && onOpenBackendNode
          ? () => onOpenBackendNode(s)
          : undefined,
      onOpenConvertDecisions:
        s.stage === 'convert' && onOpenConvertDecisions
          ? () => onOpenConvertDecisions(s)
          : undefined,
    },
    draggable: false,
    selectable: false,
  }))

  const edges: Edge[] = []
  for (let i = 0; i < stages.length - 1; i++) {
    const from = stages[i]
    const to = stages[i + 1]
    const fromDone = from.status === 'done'
    const toActive = to.status === 'running'
    const fromFailed = ['failed', 'cancelled', 'lost'].includes(from.status)

    let stroke = 'var(--border)'
    if (fromFailed) stroke = STATUS().failed
    else if (fromDone && toActive) stroke = STATUS().running
    else if (fromDone && to.status === 'done') stroke = STATUS().done
    else if (fromDone) stroke = STATUS().done

    edges.push({
      id: `edge-${i}`,
      source: `stage-${i}-${from.stage}`,
      target: `stage-${i + 1}-${to.stage}`,
      type: 'straight',
      animated: fromDone && toActive,
      style: { stroke, strokeWidth: fromDone ? 2 : 1.5 },
    })
  }
  return { nodes, edges }
}

interface WorkflowGraphProps {
  stages: WorkflowStageStatus[]
  height?: number
  onStageClick?: (stage: WorkflowStageStatus) => void
  onStageDoubleClick?: (stage: WorkflowStageStatus) => void
  onOpenNipypeDag?: (stage: WorkflowStageStatus) => void
  onOpenBackendNode?: (stage: WorkflowStageStatus) => void
  onOpenConvertDecisions?: (stage: WorkflowStageStatus) => void
}

export function WorkflowGraph(
  {
    stages,
    height = 220,
    onStageClick,
    onStageDoubleClick,
    onOpenNipypeDag,
    onOpenBackendNode,
    onOpenConvertDecisions,
  }: WorkflowGraphProps,
) {
  // Subscribe to the theme so a toggle repaints the status colours read
  // via STATUS() below (this component is memoised).
  useThemeStore((s) => s.mode)
  const { nodes, edges } = useMemo(
    () => buildGraph(stages, onOpenNipypeDag, onOpenBackendNode, onOpenConvertDecisions),
    [stages, onOpenNipypeDag, onOpenBackendNode, onOpenConvertDecisions],
  )
  if (!stages.length) return null

  return (
    <div style={{ ...GRAPH_STYLE, height }}>
      <ReactFlowProvider>
        <_WorkflowGraphInner
          initialNodes={nodes}
          edges={edges}
          onStageClick={onStageClick}
          onStageDoubleClick={onStageDoubleClick}
        />
      </ReactFlowProvider>
    </div>
  )
}


function _WorkflowGraphInner({
  initialNodes,
  edges,
  onStageClick,
  onStageDoubleClick,
}: {
  initialNodes: Node[]
  edges: Edge[]
  onStageClick?: (stage: WorkflowStageStatus) => void
  onStageDoubleClick?: (stage: WorkflowStageStatus) => void
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const lastSig = useRef('')

  // Resync when parent rebuilds the graph (live status updates).
  useEffect(() => {
    setNodes(initialNodes)
    lastSig.current = ''
  }, [initialNodes, setNodes])

  // After xyflow measures each card, recompute x AND y from the
  // measured sizes:
  //   • x packs cards left-to-right with a constant gap, so wider
  //     cards push the next one over and never overlap.
  //   • y centers each card on a shared horizontal axis so their
  //     handles line up → edges draw as straight horizontal lines.
  useEffect(() => {
    if (nodes.length === 0) return
    const dims = nodes.map((n) => {
      const m = (n as Node & {
        measured?: { width?: number; height?: number }
      }).measured
      return {
        w: m?.width && m.width > 0 ? m.width : 0,
        h: m?.height && m.height > 0 ? m.height : 0,
      }
    })
    if (dims.some((d) => d.w === 0 || d.h === 0)) return
    const sig = dims.map((d) => `${d.w}x${d.h}`).join(',')
    if (sig === lastSig.current) return
    lastSig.current = sig

    const maxH = Math.max(...dims.map((d) => d.h))
    const centerY = NODE_Y + maxH / 2
    let cursor = 0
    const repositioned = nodes.map((n, i) => {
      const x = cursor
      const y = centerY - dims[i].h / 2
      cursor += dims[i].w + NODE_GAP_X
      if (n.position.x === x && n.position.y === y) return n
      return { ...n, position: { x, y } }
    })
    if (repositioned.some((n, i) => n !== nodes[i])) setNodes(repositioned)
  }, [nodes, setNodes])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      nodesConnectable={false}
      elementsSelectable={false}
      // Stages are laid out on a fixed grid by the effect below, so leave
      // them fixed and let the canvas move instead.
      nodesDraggable={false}
      panOnDrag
      zoomOnPinch
      zoomOnDoubleClick
      minZoom={0.2}
      maxZoom={4}
      // Wheel zooms only while Ctrl/Cmd is held. A bare scroll keeps
      // scrolling the page this graph is embedded in, so the panel is not a
      // scroll trap; the Controls buttons cover mouse users who would rather
      // click. preventScrolling must stay false or ReactFlow swallows the
      // unmodified wheel event too.
      zoomOnScroll
      zoomActivationKeyCode={ZOOM_KEYS}
      panOnScroll={false}
      preventScrolling={false}
      onNodeClick={(_e, node) => {
        if (!onStageClick) return
        const data = node.data as unknown as StageNodeData
        onStageClick(data)
      }}
      onNodeDoubleClick={(_e, node) => {
        if (!onStageDoubleClick) return
        const data = node.data as unknown as StageNodeData
        onStageDoubleClick(data)
      }}
      proOptions={{ hideAttribution: true }}
    >
      <Controls showInteractive={false} />
      <_RefitOnResize />
    </ReactFlow>
  )
}


/**
 * Re-fit the viewport when the container changes size.
 *
 * `fitView` only runs once at init, so a graph laid out for one width stays
 * at that zoom when the panel is resized — which reads as arbitrary cropping.
 */
function _RefitOnResize() {
  const { fitView } = useReactFlow()
  const anchor = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    // Walk up from our own node rather than querying the document: this view
    // can mount several ReactFlow instances (the nipype and analysis graph
    // modals), and a bare selector would observe whichever mounted first.
    const el = anchor.current?.closest('.react-flow')
    if (!el || typeof ResizeObserver === 'undefined') return
    let frame = 0
    const obs = new ResizeObserver(() => {
      cancelAnimationFrame(frame)
      // Coalesce: a drag-resize fires continuously.
      frame = requestAnimationFrame(() => fitView({ padding: 0.2, duration: 120 }))
    })
    obs.observe(el)
    return () => { cancelAnimationFrame(frame); obs.disconnect() }
  }, [fitView])

  return <div ref={anchor} style={{ display: 'none' }} />
}
