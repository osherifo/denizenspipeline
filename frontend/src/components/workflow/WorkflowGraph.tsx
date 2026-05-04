/** ReactFlow graph for a single workflow run — one node per stage. */
import { memo, useMemo } from 'react'
import type { CSSProperties } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
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

const STATUS_COLORS: Record<string, string> = {
  pending:   '#6b7280',
  running:   '#00e5ff',
  done:      '#00e676',
  ok:        '#00e676',
  warning:   '#ffd600',
  failed:    '#ff1744',
  cancelled: '#ff1744',
  lost:      '#ff1744',
}

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
}

const nodeBase: CSSProperties = {
  borderRadius: 8,
  padding: '12px 16px',
  minWidth: 230,
  fontSize: 11,
  fontFamily: 'inherit',
  backgroundColor: '#14181f',
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

const statusBadge = (color: string): CSSProperties => ({
  fontSize: 10,
  fontWeight: 700,
  padding: '2px 8px',
  borderRadius: 4,
  backgroundColor: `${color}22`,
  color,
  border: `1px solid ${color}66`,
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
  border: '2px solid #0a0a1a',
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
  const meta = STAGE_META[data.stage] ?? { color: '#8888aa', icon: '\u{25CF}', label: data.stage }
  const statusColor = STATUS_COLORS[data.status] ?? STATUS_COLORS.pending
  const isRunning = data.status === 'running'

  const clickable = !!data.run_id
  const style: CSSProperties = {
    ...nodeBase,
    border: `1px solid ${isRunning ? statusColor : meta.color + '55'}`,
    boxShadow: isRunning
      ? `0 0 18px ${statusColor}66, 0 0 4px ${statusColor}`
      : `0 1px 3px rgba(0,0,0,0.3)`,
    animation: isRunning ? 'workflow-pulse 2s ease-in-out infinite' : undefined,
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
        <span style={statusBadge(statusColor)}>{data.status}</span>
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
          <InnerNodesStrip block={data.nipype_status} />
        )}

      {clickable && (
        <div style={{
          fontSize: 9, color: meta.color, marginTop: 6,
          letterSpacing: 0.5, fontWeight: 600,
        }}>
          click for log →
          {data.stage === 'preproc' && data.nipype_status &&
            data.nipype_status.counts.total_seen > 0 && (
              <span style={{ marginLeft: 8, opacity: 0.8 }}>
                · double-click for DAG
              </span>
            )}
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
        const color = STATUS_COLORS[status] ?? STATUS_COLORS.pending
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

const NODE_SPACING_X = 280
const NODE_Y = 40

function buildGraph(stages: WorkflowStageStatus[]): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = stages.map((s, i) => ({
    id: `stage-${i}-${s.stage}`,
    type: 'workflowStage',
    position: { x: i * NODE_SPACING_X, y: NODE_Y },
    data: {
      ...s,
      index: i,
      isFirst: i === 0,
      isLast: i === stages.length - 1,
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

    let stroke = '#2a2a4a'
    if (fromFailed) stroke = STATUS_COLORS.failed
    else if (fromDone && toActive) stroke = STATUS_COLORS.running
    else if (fromDone && to.status === 'done') stroke = STATUS_COLORS.done
    else if (fromDone) stroke = STATUS_COLORS.done

    edges.push({
      id: `edge-${i}`,
      source: `stage-${i}-${from.stage}`,
      target: `stage-${i + 1}-${to.stage}`,
      type: 'smoothstep',
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
}

export function WorkflowGraph(
  { stages, height = 220, onStageClick, onStageDoubleClick }: WorkflowGraphProps,
) {
  const { nodes, edges } = useMemo(() => buildGraph(stages), [stages])
  if (!stages.length) return null

  return (
    <div style={{ ...GRAPH_STYLE, height }}>
      <style>{`
        @keyframes workflow-pulse {
          0%, 100% { box-shadow: 0 0 14px ${STATUS_COLORS.running}55; }
          50%      { box-shadow: 0 0 26px ${STATUS_COLORS.running}aa, 0 0 6px ${STATUS_COLORS.running}; }
        }
      `}</style>
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
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
        />
      </ReactFlowProvider>
    </div>
  )
}
