/** Read-only ReactFlow strip showing the seven analysis stages.
 *
 * The composer's "ghost graph". Each node mirrors the fill status
 * of its corresponding StageCard:
 *  - filled  → cyan, stage colour glow
 *  - empty   → muted grey
 *  - error   → red border + red glow
 *
 * Clicking a node scrolls the matching card into view via
 * ``onNodeClick``. The strip is decorative — there is no
 * drag, connect, or edit. Wiring is hard-coded to mirror the
 * actual data flow of the pipeline.
 */

import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import { ReactFlow, Background, BackgroundVariant } from '@xyflow/react'
import type { Node, Edge } from '@xyflow/react'

import type { StageStatus } from './StageCard'

export interface PreviewStage {
  key: string
  label: string
  num: number
  color: string
  status: StageStatus
  /** Optional small text shown under the stage name (e.g. "(3)" for features). */
  badge?: string
  /** DOM id of the corresponding StageCard for scroll-to. */
  anchorId?: string
}

interface StageStripPreviewProps {
  stages: PreviewStage[]
  onNodeClick?: (key: string, anchorId?: string) => void
  height?: number
}

const wrapperStyle = (height: number): CSSProperties => ({
  height,
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
  backgroundColor: 'var(--bg-card)',
})

// Hard-coded edges. Mirrors the orchestrator data flow:
//   stimuli ──┐
//   responses ┼─→ prepare ─→ model ─→ analyze ─→ report
//   features ─┘
const EDGES: Array<[string, string]> = [
  ['stimulus', 'preparation'],
  ['response', 'preparation'],
  ['features', 'preparation'],
  ['preparation', 'model'],
  ['model', 'analysis'],
  ['analysis', 'reporting'],
]

// Node x-positions chosen so the diamond fan-in to "preparation"
// is visible without overlap. y-positions stagger the three
// inputs vertically so the merge looks clean.
const NODE_LAYOUT: Record<string, { x: number; y: number }> = {
  stimulus:    { x: 0,   y: 0 },
  response:    { x: 0,   y: 70 },
  features:    { x: 0,   y: 140 },
  preparation: { x: 200, y: 70 },
  model:       { x: 380, y: 70 },
  analysis:    { x: 560, y: 70 },
  reporting:   { x: 740, y: 70 },
}

function nodeStyle(stage: PreviewStage): CSSProperties {
  const fillBg =
    stage.status === 'filled'
      ? `${stage.color}1a`
      : stage.status === 'error'
        ? 'rgba(239, 83, 80, 0.10)'
        : 'var(--bg-input)'
  const borderColor =
    stage.status === 'filled'
      ? stage.color
      : stage.status === 'error'
        ? 'var(--accent-red, #ef5350)'
        : 'var(--border)'
  const glow =
    stage.status === 'filled' ? `0 0 6px ${stage.color}66` :
    stage.status === 'error' ? '0 0 6px rgba(239,83,80,0.5)' :
    'none'
  return {
    background: fillBg,
    border: `1px solid ${borderColor}`,
    borderRadius: 6,
    padding: '6px 10px',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.5,
    color: stage.status === 'filled' ? stage.color : 'var(--text-secondary)',
    minWidth: 110,
    textAlign: 'center',
    boxShadow: glow,
    cursor: 'pointer',
  }
}

export function StageStripPreview({
  stages,
  onNodeClick,
  height = 240,
}: StageStripPreviewProps) {
  const nodes: Node[] = useMemo(() => {
    return stages.map((stage) => {
      const pos = NODE_LAYOUT[stage.key] ?? { x: 0, y: 0 }
      return {
        id: stage.key,
        position: pos,
        type: 'default',
        data: {
          label: (
            <div>
              <div>{stage.label}</div>
              {stage.badge && (
                <div style={{ fontSize: 10, marginTop: 2, fontWeight: 500 }}>
                  {stage.badge}
                </div>
              )}
            </div>
          ),
        },
        style: nodeStyle(stage),
        draggable: false,
        connectable: false,
        selectable: true,
      }
    })
  }, [stages])

  const edges: Edge[] = useMemo(
    () =>
      EDGES.map(([source, target]) => ({
        id: `${source}->${target}`,
        source,
        target,
        type: 'smoothstep',
        animated: false,
        style: { stroke: 'var(--border)', strokeWidth: 1 },
        focusable: false,
      })),
    [],
  )

  return (
    <div style={wrapperStyle(height)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        zoomOnScroll={false}
        panOnDrag
        onNodeClick={(_, node) => {
          const stage = stages.find((s) => s.key === node.id)
          if (stage) onNodeClick?.(stage.key, stage.anchorId)
        }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
      </ReactFlow>
    </div>
  )
}
