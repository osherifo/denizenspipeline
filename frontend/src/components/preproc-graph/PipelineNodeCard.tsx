/** Preprocessing node kinds: colours and labels for the shared graph node card. */
import type { PreprocNodeKind } from '../../api/types'

export { GraphNodeCard as PipelineNodeCard } from '../graph/GraphNodeCard'

export const KIND_COLORS: Record<PreprocNodeKind, string> = {
  source: '#f59e0b',
  interface: '#10b981',
  container_app: '#3b82f6',
  composite: '#a855f7',
}

export const KIND_LABELS: Record<PreprocNodeKind, string> = {
  source: 'source',
  interface: 'node',
  container_app: 'app',
  composite: 'workflow',
}
