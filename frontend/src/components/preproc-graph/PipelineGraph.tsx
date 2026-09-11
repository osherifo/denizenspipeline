/** A preprocessing pipeline on the shared graph canvas.
 *
 *  - ``editable``: drag nodes, connect ports (one feed per input), delete with
 *    Backspace; changes flow back through the callbacks.
 *  - ``statusByNode`` / ``checkpointsByNode``: colour the nodes of a run.
 *
 *  Used by the Build tab (editable), the Runs tab and the Workflows view.
 */
import { useMemo } from 'react'
import type { PipelineDoc, PreprocNodeInfo } from '../../api/types'
import { GraphCanvas, type GraphCanvasProps, type GraphDocNode } from '../graph/GraphCanvas'
import type { GraphBadge, GraphNodeCardData, NodeRunStatus } from '../graph/GraphNodeCard'
import { KIND_COLORS, KIND_LABELS } from './PipelineNodeCard'

export type { NodeRunStatus } from '../graph/GraphNodeCard'

export interface NodeCheckpointStatus {
  worst: 'ok' | 'suspicious' | 'bad' | 'unknown'
  count: number
}

const VERDICT_COLORS: Record<NodeCheckpointStatus['worst'], string> = {
  ok: '#10b981', suspicious: '#f59e0b', bad: '#ef4444', unknown: '#9ca3af',
}

interface Props extends Omit<GraphCanvasProps, 'doc' | 'describeNode' | 'defaultSourceHandle' | 'defaultTargetHandle'> {
  pipeline: PipelineDoc
  library: PreprocNodeInfo[]
  statusByNode?: Record<string, NodeRunStatus>
  checkpointsByNode?: Record<string, NodeCheckpointStatus>
}

export function describePipelineNode(
  pipeline: PipelineDoc,
  library: PreprocNodeInfo[],
  statusByNode?: Record<string, NodeRunStatus>,
  checkpointsByNode?: Record<string, NodeCheckpointStatus>,
): (node: GraphDocNode) => GraphNodeCardData {
  const byName = new Map(library.map((n) => [n.name, n]))
  const docs = new Map(pipeline.nodes.map((n) => [n.id, n]))
  return (node) => {
    const info = byName.get(node.type)
    const kind = docs.get(node.id)?.kind ?? info?.kind ?? 'interface'
    const color = KIND_COLORS[kind] ?? KIND_COLORS.interface
    const st = statusByNode?.[node.id]
    const cp = checkpointsByNode?.[node.id]
    const badges: GraphBadge[] = []
    if (pipeline.manifest?.backend_node === node.id) badges.push({ key: 'backend', content: '★', title: 'manifest backend node', color })
    if (st?.status === 'cached') badges.push({ key: 'cached', content: '⟲', title: 'cache hit' })
    if (cp) {
      badges.push({
        key: 'checkpoint',
        title: `${cp.count} checkpoint(s), worst: ${cp.worst}`,
        content: <span style={{ width: 9, height: 9, borderRadius: 999, background: VERDICT_COLORS[cp.worst], display: 'inline-block' }} />,
      })
    }
    return {
      label: node.id,
      title: node.type,
      tag: KIND_LABELS[kind] ?? kind,
      tagColor: color,
      inputs: Object.entries(info?.inputs ?? {}).map(([name, spec]) => ({ name, title: `${spec.kind}${spec.required ? ' · required' : ''}` })),
      outputs: Object.entries(info?.outputs ?? {}).map(([name, spec]) => ({ name, title: spec.kind })),
      status: st?.status ?? null,
      durationS: st?.durationS ?? null,
      badges,
    }
  }
}

export function PipelineGraph({ pipeline, library, statusByNode, checkpointsByNode, ...rest }: Props) {
  const describeNode = useMemo(
    () => describePipelineNode(pipeline, library, statusByNode, checkpointsByNode),
    [pipeline, library, statusByNode, checkpointsByNode],
  )
  return <GraphCanvas doc={pipeline} describeNode={describeNode} defaultSourceHandle="out_file" defaultTargetHandle="in_file" {...rest} />
}
