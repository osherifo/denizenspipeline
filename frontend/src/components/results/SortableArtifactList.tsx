/** Drag-and-drop reorderable list of artifact viewers.
 *
 * Order is persisted per-run in localStorage (key: artifactOrder:<runId>).
 * Artifacts that aren't in the saved order get appended at the end in
 * their original order (useful when new artifacts appear after a re-run).
 */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import type { ArtifactInfo } from '../../api/types'
import { ArtifactViewer } from './ArtifactViewer'

interface Props {
  artifacts: ArtifactInfo[]
  runId: string
}

const STORAGE_PREFIX = 'artifactOrder:'

function loadOrder(runId: string): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + runId)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((s) => typeof s === 'string') : []
  } catch {
    return []
  }
}

function saveOrder(runId: string, order: string[]): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + runId, JSON.stringify(order))
  } catch {
    // Quota exceeded or storage unavailable — fail silently.
  }
}

/** Reconcile the saved order with the current set of artifacts:
 *  saved entries first (filtered to ones still present), then any new
 *  artifacts in their original order. */
function reconcileOrder(saved: string[], available: string[]): string[] {
  const set = new Set(available)
  const ordered = saved.filter((name) => set.has(name))
  const seen = new Set(ordered)
  for (const name of available) {
    if (!seen.has(name)) ordered.push(name)
  }
  return ordered
}

const wrapper: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
}

const itemRow = (dragging: boolean): CSSProperties => ({
  display: 'flex',
  alignItems: 'stretch',
  gap: 6,
  opacity: dragging ? 0.5 : 1,
})

const handle: CSSProperties = {
  width: 16,
  flexShrink: 0,
  cursor: 'grab',
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'center',
  alignItems: 'center',
  fontSize: 14,
  lineHeight: 1,
  color: 'var(--text-secondary)',
  userSelect: 'none',
  borderRadius: 4,
}

const handleDragging: CSSProperties = {
  ...handle,
  cursor: 'grabbing',
  color: 'var(--accent-cyan)',
}

const content: CSSProperties = {
  flex: 1,
  minWidth: 0,
}

interface ItemProps {
  artifact: ArtifactInfo
  runId: string
}

function SortableItem({ artifact, runId }: ItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: artifact.name })

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    ...itemRow(isDragging),
  }

  return (
    <div ref={setNodeRef} style={style}>
      <div
        ref={setActivatorNodeRef}
        style={isDragging ? handleDragging : handle}
        title="Drag to reorder"
        {...attributes}
        {...listeners}
      >
        {'\u22EE\u22EE'}
      </div>
      <div style={content}>
        <ArtifactViewer artifact={artifact} runId={runId} />
      </div>
    </div>
  )
}

export function SortableArtifactList({ artifacts, runId }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const available = useMemo(() => artifacts.map((a) => a.name), [artifacts])
  const [order, setOrder] = useState<string[]>(() =>
    reconcileOrder(loadOrder(runId), available),
  )

  // Reconcile when the run or its artifact set changes.
  useEffect(() => {
    setOrder(reconcileOrder(loadOrder(runId), available))
  }, [runId, available.join('|')])

  const ordered = useMemo(() => {
    const byName = new Map(artifacts.map((a) => [a.name, a]))
    return order.map((name) => byName.get(name)).filter(Boolean) as ArtifactInfo[]
  }, [order, artifacts])

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = order.indexOf(String(active.id))
    const newIndex = order.indexOf(String(over.id))
    if (oldIndex < 0 || newIndex < 0) return
    const next = arrayMove(order, oldIndex, newIndex)
    setOrder(next)
    saveOrder(runId, next)
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={order} strategy={verticalListSortingStrategy}>
        <div style={wrapper}>
          {ordered.map((art) => (
            <SortableItem key={art.name} artifact={art} runId={runId} />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  )
}
